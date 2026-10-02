"""TTS voice generation module.

Automates Google AI Studio and Gemini web interface for neural text-to-speech synthesis,
chapter slicing, clipboard automation, and profile rotation.
"""

import ctypes
import difflib
import glob
import hashlib
import json
import os
import random
import re
import sys
import time
import wave
from contextlib import ExitStack

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from youtube_automation.core.utils import (
    get_config_value,
    get_runtime_state,
    kill_cdp_chrome,
    launch_browser_with_profile,
    rotate_profile_index,
)
from youtube_automation.prompts import loader

# Selector constants for the standard Gemini Web App
RESPONSE_SELECTOR = "model-response div.markdown"
MANIFEST_FILE_NAME = "voice_generation_manifest.json"
AUDIO_MANIFEST_FILE_NAME = "audio_manifest.json"
DEFAULT_SILENCE_PADDING_SEC = 0.300

# Global tracker for human mouse emulation coordinates
current_mouse_pos = [100, 100]

# Windows API Constants for native clipboard manipulation using ctypes
GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Declare types to support 64-bit Windows memory pointer structures
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = ctypes.c_void_p

kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p

kernel32.GlobalUnlock.argtypes = [ctypes.c_bool]
kernel32.GlobalUnlock.restype = ctypes.c_bool

user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p

user32.GetClipboardData.argtypes = [ctypes.c_uint]
user32.GetClipboardData.restype = ctypes.c_void_p


def set_clipboard_text(text):
    """Sets Unicode text directly to the Windows system clipboard using native ctypes with retries."""
    from youtube_automation.production.ledger import leased_resource, resource_database

    with leased_resource(resource_database(), "clipboard"):
        return _set_clipboard_text(text)


def _set_clipboard_text(text):
    """Own the already-leased Windows clipboard for one bounded write."""
    opened = False
    for _i in range(10):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.1)
    if not opened:
        return False
    try:
        user32.EmptyClipboard()
        encoded_text = text.encode("utf-16le") + b"\x00\x00"
        h_global_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded_text))
        if not h_global_mem:
            return False
        p_global_mem = kernel32.GlobalLock(h_global_mem)
        if not p_global_mem:
            return False
        ctypes.memmove(p_global_mem, encoded_text, len(encoded_text))
        kernel32.GlobalUnlock(h_global_mem)
        user32.SetClipboardData(CF_UNICODETEXT, h_global_mem)
    finally:
        user32.CloseClipboard()
    return True


# Preset Configuration File Parser
def read_voice_options():
    preset_path = "voice_option_notes.txt"
    options = {
        "model": get_config_value("TTS_MODEL", "gemini-2.5-pro-preview-tts"),
        "temperature": get_config_value("TTS_TEMPERATURE", "1.1"),
        "voice": get_config_value("TTS_VOICE_NAME", "Achird"),
    }
    if os.path.exists(preset_path):
        try:
            with open(preset_path, encoding="utf-8") as f:
                for line in f:
                    if ":" in line:
                        key, val = line.split(":", 1)
                        key = key.strip().lower()
                        val = val.strip()
                        if key in options:
                            options[key] = val
            print(f"Loaded voice configurations from '{preset_path}': {options}")
        except Exception as e:
            print(f"Warning: Could not parse preset file ({e}). Using default settings.")
    else:
        try:
            with open(preset_path, "w", encoding="utf-8") as f:
                f.write("Model: gemini-2.5-pro-preview-tts\n")
                f.write("Temperature: 1.1\n")
                f.write("Voice: Achird\n")
            print(f"Created default preset file at '{preset_path}'")
        except Exception as e:
            print(f"Warning: Could not create default preset file ({e})")
    return options


# Manifest Checkpoint Persistence Helpers
def get_manifest_path(latest_run):
    return os.path.join(latest_run, MANIFEST_FILE_NAME)


def load_or_create_manifest(latest_run, voice_options):
    manifest_path = get_manifest_path(latest_run)
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
                print(f"[MANIFEST] Loaded active manifest checkpoint from '{manifest_path}'.")
                if "voice_config" not in data or not data["voice_config"]:
                    data["voice_config"] = voice_options
                return data
        except Exception as e:
            print(f"[MANIFEST WARNING] Could not parse manifest ({e}). Creating fresh manifest.")

    initial_manifest = {
        "voice_config": voice_options,
        "archetype_plan": "",
        "gemini_completed": False,
        "chapters": [],
    }
    save_manifest(latest_run, initial_manifest)
    return initial_manifest


def save_manifest(latest_run, manifest_data):
    manifest_path = get_manifest_path(latest_run)
    tmp_path = manifest_path + ".tmp"
    try:
        # Atomic commit: a crash mid-write must never leave a zero-byte or
        # truncated manifest behind (resume depends on parsing this file).
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, manifest_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise OSError(f"Failed to write manifest checkpoint: {manifest_path}") from e


def probe_audio_file(file_path):
    """Extracts exact physical duration and audio format parameters via wave header inspection.

    Returns dict with keys: duration, framerate, channels, sampwidth, nframes, or None on error.
    """
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        with wave.open(file_path, "rb") as wf:
            framerate = wf.getframerate()
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            nframes = wf.getnframes()
            if framerate <= 0 or nframes < 0:
                return None
            duration = round(nframes / float(framerate), 3)
            return {
                "duration": duration,
                "framerate": framerate,
                "channels": nchannels,
                "sampwidth": sampwidth,
                "nframes": nframes,
            }
    except Exception:
        return None


def sync_audio_manifest(latest_run, manifest, silence_padding_sec=DEFAULT_SILENCE_PADDING_SEC):
    """Enforces monotonic timeline progression and exports audio_manifest.json with exact 7-field schema.

    Schema per segment:
      id, index, audio_file, text_arabic, start_time, end_time, duration, visual_keyframe_id.
    """
    cfg_padding = get_config_value("SILENCE_PADDING_SEC", "")
    try:
        padding = float(cfg_padding) if cfg_padding else float(silence_padding_sec)
    except (ValueError, TypeError):
        padding = float(silence_padding_sec)

    chapters = manifest.get("chapters", [])
    current_time = 0.0
    segments = []
    total_words = 0
    ref_format = None

    for idx, chap in enumerate(chapters, 1):
        chap_num = chap.get("chapter_num", idx)
        raw_audio_file = chap.get("audio_file", "")
        if raw_audio_file and os.path.exists(raw_audio_file):
            abs_audio_file = os.path.abspath(raw_audio_file)
        elif raw_audio_file and os.path.exists(os.path.join(latest_run, raw_audio_file)):
            abs_audio_file = os.path.abspath(os.path.join(latest_run, raw_audio_file))
        elif raw_audio_file and os.path.isabs(raw_audio_file):
            abs_audio_file = raw_audio_file
        else:
            abs_audio_file = os.path.abspath(
                os.path.join(latest_run, "voice_chapters", f"Chapter_{chap_num}.wav")
            )

        rel_audio_file = os.path.relpath(abs_audio_file, latest_run).replace("\\", "/")

        raw_text = chap.get("text_arabic") or chap.get("text", "")
        script_block_match = re.search(
            r'(?:Expressive Script Block|2\.\s*Expressive Script Block)\s*[\r\n]+["“]?(.*?)["”]?$',
            raw_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if script_block_match:
            spoken_text = script_block_match.group(1).strip().strip('"').strip("“").strip("”")
        else:
            quote_match = re.search(r'["“]([\u0600-\u06FF\[].*?)["”]', raw_text, flags=re.DOTALL)
            if quote_match:
                spoken_text = quote_match.group(1).strip()
            else:
                spoken_text = raw_text.strip()

        clean_words_text = re.sub(r"\[[^\]]+\]", "", spoken_text)
        words = len(clean_words_text.split())
        total_words += words

        probe = probe_audio_file(abs_audio_file)
        if probe:
            duration = probe["duration"]
            if ref_format is None:
                ref_format = {
                    "sample_rate": probe["framerate"],
                    "channels": probe["channels"],
                    "bit_depth": probe["sampwidth"] * 8,
                    "encoding": "PCM_S16LE" if probe["sampwidth"] == 2 else f"PCM_{probe['sampwidth']*8}BIT",
                }
        else:
            duration = float(chap.get("duration", 0.0))

        start_time = round(current_time, 3)
        end_time = round(start_time + duration, 3)
        wpm = round(words / (duration / 60.0), 1) if duration > 0 else 0.0

        segment_entry = {
            "id": f"{chap_num:03d}",
            "index": chap_num,
            "audio_file": rel_audio_file,
            "text_arabic": spoken_text,
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration,
            "visual_keyframe_id": f"scene_{chap_num:03d}",
            "status": chap.get("status", "PENDING"),
            "words_count": words,
            "words_per_minute": wpm,
        }
        if chap.get("md5"):
            segment_entry["md5"] = chap["md5"]

        # In-place enrichment of manifest["chapters"]
        chap["id"] = f"{chap_num:03d}"
        chap["index"] = chap_num
        chap["audio_file"] = rel_audio_file
        chap["text_arabic"] = spoken_text
        chap["start_time"] = start_time
        chap["end_time"] = end_time
        chap["duration"] = duration
        chap["visual_keyframe_id"] = f"scene_{chap_num:03d}"
        if probe:
            chap["sample_rate"] = probe["framerate"]
            chap["channels"] = probe["channels"]
            chap["bit_depth"] = probe["sampwidth"] * 8

        segments.append(segment_entry)

        # Monotonic advance with breath gap
        if chap.get("status") == "COMPLETED" and duration > 0:
            current_time = end_time + padding
        else:
            current_time = end_time

    audio_manifest_path = os.path.join(latest_run, AUDIO_MANIFEST_FILE_NAME)
    manifest_payload = {
        "project_id": os.path.basename(os.path.normpath(latest_run)),
        "schema_version": "1.0.0",
        "voice_target": manifest.get("voice_config", {}).get("voice", "Achird"),
        "model": manifest.get("voice_config", {}).get("model", "gemini-2.5-pro-preview-tts"),
        "temperature": float(manifest.get("voice_config", {}).get("temperature", 0.8)),
        "silence_padding_sec": padding,
        "total_segments": len(segments),
        "completed_segments": sum(1 for s in segments if s["status"] == "COMPLETED"),
        "cumulative_duration_sec": round(current_time, 3),
        "total_words": total_words,
        "format": ref_format or {
            "sample_rate": 24000,
            "channels": 1,
            "bit_depth": 16,
            "encoding": "PCM_S16LE",
        },
        "segments": segments,
    }

    tmp_path = audio_manifest_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(manifest_payload, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, audio_manifest_path)
    except Exception as e:
        raise OSError(f"Could not atomically write {AUDIO_MANIFEST_FILE_NAME}") from e

    return manifest_payload


def extract_total_blocks_count(text):
    """Extracts (current_idx, total_idx) from headers like 'TTS BLOCK 1 of 8'.

    Scans ALL header occurrences and returns the highest current index found,
    so a response that echoes the full plan ('BLOCK 1 of 8 ... BLOCK 2 of 8')
    still resolves to the most recent block instead of the first mention.
    """
    if not text:
        return None, None
    matches = re.findall(
        r"(?:TTS\s*BLOCK|BLOCK|CHAPTER|ط§ظ„ط¬ط²ط،)\s*\[?(\d+)\]?\s*(?:of|OF|ظ…ظ†|\/)\s*\[?(\d+)\]?",
        text,
        flags=re.IGNORECASE,
    )
    if not matches:
        return None, None
    best_curr, best_total = None, None
    for curr_s, total_s in matches:
        try:
            curr, total = int(curr_s), int(total_s)
        except ValueError:
            continue
        if total <= 0:
            continue
        if best_curr is None or curr > best_curr:
            best_curr, best_total = curr, total
    return best_curr, best_total


def check_is_gemini_complete(manifest, transcript_text, last_raw_response=""):
    """Determines if Gemini text generation is complete based on block headers.

    Header-driven only: the char-ratio/ending-keyword heuristics were removed
    because speech-tag markup bloat inflated the coverage ratio past 80% and
    words like 'ط³ظ„ط§ظ…'/'ط§ظ„ظ…طµط§ط¯ط±' inside body text triggered premature exits
    mid-script. A run is complete only when the newest 'TTS BLOCK N of M'
    header reports N == M (or all M chapters are already harvested).
    """
    if manifest.get("gemini_completed"):
        return True

    chapters = manifest.get("chapters", [])
    if not chapters:
        return False

    # Newest evidence first: the raw response just received, then saved
    # chapter texts in reverse order (headers survive sanitization, which
    # makes this fallback work on resume where last_raw_response is empty).
    texts_to_check = [last_raw_response] + [c.get("text", "") for c in reversed(chapters)]
    for txt in texts_to_check:
        curr, total = extract_total_blocks_count(txt)
        if curr is not None and total is not None:
            if len(chapters) >= total or curr >= total:
                return True
            break  # Header present but remaining blocks outstanding -> fall through to ceiling

    # Safety net: hard runaway ceiling for instruction drift (Gemini dropping
    # 'TTS BLOCK N of M' headers after several turns). Block size varies per the
    # prompt's word-count targets, so the default is generous and env-overridable.
    max_allowed_cfg = str(get_config_value("MAX_HARVEST_BLOCKS", "") or "").strip()
    if max_allowed_cfg.isdigit():
        max_blocks = int(max_allowed_cfg)
    else:
        max_blocks = max(len(transcript_text or "") // 700 + 4, 8)
    if len(chapters) >= max_blocks:
        print(
            f"[GUARDRAIL] Runaway block ceiling reached ({len(chapters)} >= {max_blocks}). Forcing Phase 1 completion."
        )
        return True

    return False


# Human-like Mouse Emulation functions
def simulate_human_mouse_move(page, target_locator, steps=25):
    """Moves the mouse from current position to target element using organic Bezier curves."""
    global current_mouse_pos
    try:
        box = target_locator.bounding_box()
        if not box:
            return

        target_x = (
            box["x"] + box["width"] / 2 + random.uniform(-box["width"] * 0.08, box["width"] * 0.08)
        )
        target_y = (
            box["y"]
            + box["height"] / 2
            + random.uniform(-box["height"] * 0.08, box["height"] * 0.08)
        )
    except Exception:
        return

    start_x, start_y = current_mouse_pos

    ctrl_x = start_x + (target_x - start_x) * random.uniform(0.2, 0.8) + random.uniform(-60, 60)
    ctrl_y = start_y + (target_y - start_y) * random.uniform(0.2, 0.8) + random.uniform(-60, 60)

    for i in range(steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * ctrl_x + t**2 * target_x
        y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * ctrl_y + t**2 * target_y

        page.mouse.move(x, y)
        time.sleep(random.uniform(0.004, 0.012))

    current_mouse_pos = [target_x, target_y]
    time.sleep(random.uniform(0.12, 0.28))


def human_click(page, target_locator):
    """Performs an organic click containing scrolling, path curves, and down/up click pauses."""
    try:
        target_locator.scroll_into_view_if_needed()
    except Exception:
        pass

    box = None
    try:
        box = target_locator.bounding_box()
    except Exception:
        pass

    if not box:
        try:
            target_locator.click(timeout=3000)
        except Exception:
            pass
        return

    try:
        simulate_human_mouse_move(page, target_locator)
        page.mouse.down()
        time.sleep(random.uniform(0.06, 0.14))
        page.mouse.up()
        time.sleep(random.uniform(0.1, 0.22))
    except Exception:
        try:
            target_locator.click(timeout=3000)
        except Exception:
            pass


def human_hover_and_click(page, locator):
    """Simulates organic mouse movement, hovers, pauses, then clicks the element."""
    try:
        locator.scroll_into_view_if_needed()
        simulate_human_mouse_move(page, locator)
        time.sleep(random.uniform(0.4, 0.9))

        page.mouse.down()
        time.sleep(random.uniform(0.08, 0.15))
        page.mouse.up()
        time.sleep(random.uniform(0.2, 0.4))
        return True
    except Exception:
        try:
            locator.click(timeout=3000)
            return True
        except Exception:
            return False


def humanize_text_input(page, textbox, text):
    """Clicks, inputs the text, and triggers native event listeners with micro-edits."""
    try:
        textbox.click()
        textbox.fill(text)
        time.sleep(random.uniform(1.2, 2.5))

        page.keyboard.press("End")
        time.sleep(0.1)
        page.keyboard.type(" ")
        time.sleep(random.uniform(0.1, 0.3))
        page.keyboard.press("Backspace")
        time.sleep(random.uniform(0.4, 0.8))
        return True
    except Exception as e:
        print(f"Warning: Humanized fill failed. Falling back to native: {e}")
        try:
            textbox.fill(text)
            return True
        except Exception:
            return False


def sanitize_script_text(text):
    """
    Cleans up raw markdown code fences, strips casting reports, breakdown headers,
    voice profile anchors, and control keywords, leaving only the pure expressive script text.
    Enforces strict lowercase formatting on all TTS tags ([tone:...], [pace:...], [pause:...])
    to prevent AI Studio from reading English letters out loud.
    """
    if not text:
        return ""

    # 1. Strip Markdown code blocks
    text = re.sub(r"```[a-zA-Z0-9_-]*\n(.*?)\n```", r"\1", text, flags=re.DOTALL)
    text = text.replace("```", "")

    # 2. Extract expressive script block if embedded inside casting/structure reports
    script_block_match = re.search(
        r'(?:Expressive Script Block|2\.\s*Expressive Script Block)\s*[\r\n]+["“]?(.*?)["”]?$',
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if script_block_match:
        text = script_block_match.group(1)
    else:
        # Check quotes containing Arabic
        quote_match = re.search(r'["“]([\u0600-\u06FF\[].*?)["”]', text, flags=re.DOTALL)
        if quote_match and len(quote_match.group(1)) > 50:
            text = quote_match.group(1)

    # 3. Strip metadata headers that might leak into TTS prompt
    metadata_patterns = [
        r"#+\s+.*",
        r"(?i)markdown\s*",
        r"(?i)TTS\s*BLOCK\s*\d+\s*of\s*\d+.*",
        r"(?i)Target\s*Word\s*Count:.*",
        r"(?i)Pacing:.*",
        r"(?i)Voice\s*Persona:.*",
        r"(?i)Age\s*/\s*Gender:.*",
        r"(?i)Voice\s*Archetype:.*",
        r"(?i)Active\s*Register:.*",
        r"(?i)Acoustic\s*Space:.*",
        r"(?i)Casting\s*Report.*",
        r"(?i)Breakdown\s*Structure.*",
        r"(?i)1\.\s*Voice\s*Profile\s*Anchor.*",
        r"(?i)2\.\s*Expressive\s*Script\s*Block.*",
    ]
    for pat in metadata_patterns:
        text = re.sub(pat, "", text)

    # 4. Enforce Speech Tag Armor (Force lowercase on all bracket tags)
    def lowercase_tts_tags(match):
        return match.group(0).lower()

    text = re.sub(r"\[(tone|pace|pause)\s*:[^\]]+\]", lowercase_tts_tags, text, flags=re.IGNORECASE)

    # 5. Strip control triggers
    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        trimmed = line.strip()
        if trimmed.upper() in ["COMPLETE", "FINISHED", "READY", "PROCEED"]:
            continue
        cleaned_lines.append(line)

    clean_res = "\n".join(cleaned_lines).strip().strip('"').strip("“").strip("”")
    return clean_res


def clean_text_for_speech(raw_text: str) -> str:
    """Convenience alias for sanitize_script_text with speech tag stripping option."""
    return sanitize_script_text(raw_text)


def calculate_script_coverage(manifest, transcript_text: str) -> float:
    """Calculates word-level coverage of manifest chapters against the reference script."""
    if not transcript_text or not manifest.get("chapters"):
        return 0.0
    script_words = len(re.findall(r"[\u0600-\u06FF]{2,}", transcript_text))
    if script_words == 0:
        return 1.0
    all_chap_text = " ".join(c.get("text", "") for c in manifest["chapters"])
    clean_text = sanitize_script_text(all_chap_text)
    chap_words = len(re.findall(r"[\u0600-\u06FF]{2,}", clean_text))
    return chap_words / float(script_words)


def partition_script_to_chapters(latest_run: str, transcript_text: str, max_words_per_chapter: int = 220) -> list:
    """Deterministically partitions the refined script or tts_payload into balanced chapters.
    Guarantees 100% script coverage and eliminates chat truncation / meta-talk risks.
    """
    payload_path = os.path.join(latest_run, "tts_payload.json")
    paragraphs = []
    if os.path.exists(payload_path):
        try:
            with open(payload_path, encoding="utf-8") as f:
                data = json.load(f)
            raw_paras = data.get("paragraphs", [])
            for p in raw_paras:
                t = p.get("tts_text") or p.get("text", "")
                if t.strip():
                    paragraphs.append(t.strip())
        except Exception:
            pass

    if not paragraphs:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", transcript_text) if p.strip()]

    chapters = []
    current_paras = []
    current_words = 0
    voice_folder = os.path.join(latest_run, "voice_chapters")
    os.makedirs(voice_folder, exist_ok=True)

    for p in paragraphs:
        p_words = len(p.split())
        if current_words + p_words > max_words_per_chapter and current_paras:
            chap_num = len(chapters) + 1
            chap_text = "\n\n".join(current_paras)
            audio_path = os.path.join(voice_folder, f"Chapter_{chap_num}.wav")
            chapters.append({
                "chapter_num": chap_num,
                "text": chap_text,
                "audio_file": audio_path,
                "status": "PENDING",
            })
            current_paras = [p]
            current_words = p_words
        else:
            current_paras.append(p)
            current_words += p_words

    if current_paras:
        chap_num = len(chapters) + 1
        chap_text = "\n\n".join(current_paras)
        audio_path = os.path.join(voice_folder, f"Chapter_{chap_num}.wav")
        chapters.append({
            "chapter_num": chap_num,
            "text": chap_text,
            "audio_file": audio_path,
            "status": "PENDING",
        })

    return chapters


def get_latest_run_folder(runs_path="youtube_runs"):
    if not os.path.exists(runs_path):
        print(f"Error: Directory '{runs_path}' does not exist.")
        return None
    folders = glob.glob(os.path.join(runs_path, "*/"))
    if not folders:
        return None
    latest_folder = max(folders, key=os.path.getmtime)
    return latest_folder


def find_input_box(page):
    selectors = [
        "rich-textarea div[contenteditable='true']",
        "rich-textarea [contenteditable='true']",
        "div[contenteditable='true'][role='textbox']",
        "[role='textbox']",
        "rich-textarea",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = loc.count()
            for i in range(count):
                el = loc.nth(i)
                if el.is_visible() and el.is_enabled():
                    return el
        except Exception:
            continue
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=1000)
            box = page.locator(sel).first
            if box:
                return box
        except Exception:
            continue
    return None


def find_send_button(page):
    selectors = [
        "button.send-button",
        "button[aria-label*='Send message' i]",
        "button[aria-label*='Send' i]",
        "button[aria-label*='Submit' i]",
        "div.send-button-container button",
        "div[class*='send-button-container'] button",
        "button:has(mat-icon[fonticon*='send'])",
        "button[id*='send']",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = loc.count()
            for i in range(count - 1, -1, -1):
                el = loc.nth(i)
                if el.is_visible() and el.is_enabled():
                    return el
        except Exception:
            continue
    return None


def send_gemini_prompt(page, text):
    """Pastes text into the Gemini chat input, ensures DOM state sync, and guarantees dispatch.

    Root cause this guards against: clicking Send / pressing Ctrl+Enter before the rich
    textarea re-renders leaves the prompt sitting unsent in the box, and the caller then
    blocks forever waiting for a response that was never initiated.
    """
    chat_box = find_input_box(page)
    if not chat_box:
        raise Exception("Could not find Gemini Chat input box. Ensure you are signed in.")

    # 1. Focus and select-clear any residual text
    chat_box.focus()
    human_click(page, chat_box)
    time.sleep(0.3)

    # 2. Paste via Windows system clipboard
    set_clipboard_text(text)
    page.keyboard.press("Control+a")
    time.sleep(0.1)
    page.keyboard.press("Control+v")
    time.sleep(1.0)

    # 3. Micro-edit (space + backspace) to fire Gemini's Angular input-change listener
    #    so framework state acknowledges the pasted content and enables the Send button.
    page.keyboard.press("End")
    time.sleep(0.1)
    page.keyboard.type(" ")
    time.sleep(0.1)
    page.keyboard.press("Backspace")
    time.sleep(1.0)

    # 4. Submit: click the Send button when available, else plain Enter
    submit_btn = find_send_button(page)
    if submit_btn and submit_btn.is_visible() and submit_btn.is_enabled():
        try:
            submit_btn.click(force=True)
        except Exception:
            human_click(page, submit_btn)
    else:
        page.keyboard.press("Enter")

    time.sleep(1.5)

    # 5. Guardrail: if text still sits in the box, force one more Enter
    def _input_still_full():
        try:
            return len(chat_box.inner_text().strip()) > 10
        except Exception:
            return False

    if _input_still_full():
        print(
            "[SEND GUARDRAIL] Text still in input box after first submit attempt. Forcing Enter..."
        )
        chat_box.focus()
        page.keyboard.press("Enter")
        time.sleep(1.5)

        if _input_still_full():
            raise Exception(
                "Gemini prompt could not be dispatched: input box still contains text "
                "after click + two Enter attempts. Triggering recovery."
            )


def get_last_response(page):
    try:
        elements = page.locator(RESPONSE_SELECTOR)
        count = elements.count()
        if count > 0:
            last_el = elements.nth(count - 1)
            text = last_el.evaluate("el => el.innerText").strip()
            if text.startswith("Gemini said"):
                text = text[len("Gemini said") :].strip()
            return text
    except Exception as e:
        print(f"Error reading last response: {e}")
    return ""


def start_clean_gemini_chat(page):
    print("Requesting a clean chat session...")
    new_chat_selectors = [
        "[aria-label='New chat']",
        "[aria-label='Start a new chat']",
        "a[href='/app']",
        "a[href*='/app']",
        "div.new-chat-button",
        "button:has-text('New chat')",
    ]

    clicked_new_chat = False
    for sel in new_chat_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible() and btn.is_enabled():
                human_click(page, btn)
                clicked_new_chat = True
                print(f"Successfully started new chat using selector: '{sel}'")
                break
        except Exception:
            continue

    if not clicked_new_chat:
        print(
            "Direct click failed. Injecting keyboard shortcut Control+Shift+O for a clean chat..."
        )
        try:
            page.locator("body").first.click(timeout=1000)
            page.keyboard.press("Control+Shift+O")
            time.sleep(2)
        except Exception as e:
            print(f"Warning: Keyboard shortcut call returned an exception: {e}")

    print("Waiting for chat session to initialize and clear...")
    clear_start = time.time()
    while time.time() - clear_start < 10:
        try:
            count = page.locator(RESPONSE_SELECTOR).count()
            if count == 0:
                break
        except Exception:
            pass
        time.sleep(0.5)
    time.sleep(2)


def prepare_gemini_chat_session(page, manifest):
    """Resumes an ongoing chat session if present in DOM or sidebar, avoiding new chat generation when resuming."""
    try:
        last_resp = get_last_response(page)
        if last_resp and (
            "Option A" in last_resp or "Chapter" in last_resp or "Rules Confirmation" in last_resp
        ):
            print("[CHAT RESUME] Active Gemini chat session detected in current tab. Continuing...")
            return True
    except Exception:
        pass

    try:
        sidebar_selectors = [
            "a[aria-label*='TTS Orchestrator']",
            "a[aria-label*='Al-Daheeh']",
            "a[aria-label*='Daheeh']",
            "a[aria-label*='Script Segmentation']",
            "nav a:has-text('TTS')",
            "nav a:has-text('Daheeh')",
        ]
        for sel in sidebar_selectors:
            recent_btn = page.locator(sel).first
            if recent_btn.is_visible():
                human_click(page, recent_btn)
                time.sleep(2)
                print(
                    f"[CHAT RESUME] Successfully resumed existing chat session from sidebar ('{sel}')."
                )
                return True
    except Exception as e:
        print(f"[CHAT RESUME] Sidebar check note: {e}")

    start_clean_gemini_chat(page)
    return False


def ensure_speech_playground_tab(
    context, target_tts_model="gemini-2.5-pro-preview-tts", *, owned_page=None
):
    """Finds or opens the Google AI Studio Speech Playground tab and guarantees Playwright is on the correct UI."""
    tab1_speech = owned_page

    # 1. Search existing tabs for generate-speech
    if tab1_speech is None:
        for page in context.pages:
            if "generate-speech" in page.url:
                tab1_speech = page
                break

    # 2. If not found, pick a non-Gemini page or open a new tab
    if tab1_speech is None:
        for page in context.pages:
            if "gemini.google.com" not in page.url:
                tab1_speech = page
                break
        if not tab1_speech:
            print("Opening Google AI Studio Speech Playground Tab...")
            tab1_speech = context.new_page()

    tab1_speech.bring_to_front()

    clean_speech_url = f"https://aistudio.google.com/generate-speech?model={target_tts_model}"

    if "generate-speech" not in tab1_speech.url or f"model={target_tts_model}" not in tab1_speech.url:
        print(f"Navigating to Speech Playground: {clean_speech_url}")
        try:
            tab1_speech.goto(clean_speech_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"[NOTICE] Initial navigation notice: {e}")
        time.sleep(4)

    # 3. Guardrail: If AI Studio redirected away to /prompts/..., force direct navigation
    if "generate-speech" not in tab1_speech.url or f"model={target_tts_model}" not in tab1_speech.url:
        print(
            "[WARNING] AI Studio redirected away from Speech Playground. Retrying direct navigation..."
        )
        try:
            tab1_speech.goto(clean_speech_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"[NOTICE] Guardrail navigation notice: {e}")
        time.sleep(4)

    return tab1_speech


def wait_for_gemini_response(page, step_name="AI Response", max_wait_sec=120):
    print(f"Waiting for {step_name} to generate and stabilize...")
    last_length = 0
    stable_cycles = 0
    start_time = time.time()

    initial_count = page.locator(RESPONSE_SELECTOR).count()

    new_response_started = False
    while time.time() - start_time < 30:
        try:
            current_count = page.locator(RESPONSE_SELECTOR).count()
            if current_count > initial_count:
                new_response_started = True
                break
        except Exception:
            pass
        time.sleep(0.5)

    if not new_response_started:
        print(f"Warning: Timeout waiting for response to start rendering for {step_name}.")
        return get_last_response(page)

    while time.time() - start_time < max_wait_sec:
        try:
            current_count = page.locator(RESPONSE_SELECTOR).count()
            if current_count > 0:
                last_el = page.locator(RESPONSE_SELECTOR).nth(current_count - 1)
                current_text = last_el.evaluate("el => el.innerText").strip()
                if current_text.startswith("Gemini said"):
                    current_text = current_text[len("Gemini said") :].strip()

                if (
                    "something went wrong" in current_text.lower()
                    or "try reloading" in current_text.lower()
                ):
                    print(
                        "Warning: Gemini Web App reported an execution block or crash. Retrying..."
                    )
                    time.sleep(2)
                    continue

                if current_text and len(current_text) == last_length:
                    stable_cycles += 1
                else:
                    stable_cycles = 0
                    last_length = len(current_text)

                if current_text and stable_cycles >= 3:
                    return current_text
        except Exception:
            pass
        time.sleep(0.5)

    return get_last_response(page)


def select_gemini_model(page, model_name):
    print(f"[SYSTEM] Attempting to select Gemini model: {model_name}")
    trigger_selectors = [
        "button[aria-haspopup='menu']:has-text('Flash')",
        "button[aria-haspopup='menu']:has-text('Pro')",
        "button:has-text('Flash')",
        "button:has-text('Pro')",
        "button:has-text('Gemini')",
        "button[aria-label*='model' i]",
        "button[aria-label*='Model' i]",
    ]

    btn = None
    for sel in trigger_selectors:
        try:
            elements = page.locator(sel)
            for i in range(elements.count()):
                if elements.nth(i).is_visible():
                    btn = elements.nth(i)
                    break
            if btn:
                break
        except Exception:
            continue

    if not btn:
        print("[WARNING] Could not find Gemini model dropdown trigger button in UI.")
        return False

    try:
        current_text = btn.inner_text().strip() if btn.inner_text() else ""
        if model_name.lower() in current_text.lower():
            print(f"[SYSTEM] Model '{model_name}' is already active.")
            return True

        btn.click()
        time.sleep(1.5)

        opt = (
            page.locator("[role='menuitem'], [role='option'], li")
            .filter(has_text=re.compile(model_name, re.IGNORECASE))
            .first
        )

        if not opt.is_visible():
            opt = page.locator(f'text="{model_name}"').filter(visible=True).last

        if opt.is_visible():
            opt.click()
            print(f"[SYSTEM] Successfully switched model to {model_name}")
            time.sleep(1)
            return True
        else:
            print(f"[WARNING] Target model '{model_name}' not visible in dropdown menu.")

    except Exception as e:
        print(f"[WARNING] Model selection process failed: {e}")

    return False


def select_ai_studio_tts_model(page, target_model):
    """Selects the target TTS model (e.g., gemini-2.5-pro-preview-tts) inside Google AI Studio Speech Playground UI."""
    if not target_model:
        return True

    print(f"[SYSTEM] Verifying AI Studio TTS model: '{target_model}'...")

    # 1. Check if active model card in sidebar already matches target model
    try:
        model_card = page.locator(
            "ms-run-settings .model-card, ms-run-settings mat-card, ms-run-settings div:has-text('TTS')"
        ).first
        if model_card.is_visible():
            card_text = model_card.inner_text().lower()
            short_target = (
                target_model.lower().replace("-preview-tts", "").replace("gemini-", "").strip()
            )
            if short_target in card_text or target_model.lower() in card_text:
                print(f"[SYSTEM] TTS Model '{target_model}' is already active in UI.")
                return True
    except Exception:
        pass

    print(f"[SYSTEM] Switching active TTS Model to '{target_model}' via Model selection modal...")

    # 2. Open Model selection modal dialog
    card_clicked = False
    card_selectors = [
        "ms-run-settings .model-card",
        "ms-run-settings mat-card",
        "ms-run-settings button:has-text('TTS')",
        "ms-run-settings [aria-label*='Model' i]",
        "ms-run-settings div:has-text('Gemini')",
    ]
    for sel in card_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                human_click(page, loc)
                card_clicked = True
                time.sleep(1.5)
                break
        except Exception:
            continue

    if not card_clicked:
        print("[WARNING] Could not locate AI Studio model card trigger in sidebar.")
        return False

    # 3. Filter and select target model option in the modal dialog
    try:
        audio_chip = page.locator(
            "mat-dialog-container button:has-text('Audio'), [role='dialog'] button:has-text('Audio')"
        ).first
        if audio_chip.is_visible():
            human_click(page, audio_chip)
            time.sleep(0.8)

        # Flexible text matching for target TTS model
        short_target = (
            target_model.lower().replace("-preview-tts", "").replace("gemini-", "").strip()
        )

        target_option = None
        dialog_loc = page.locator("mat-dialog-container, [role='dialog']").first
        if dialog_loc.is_visible():
            options = dialog_loc.locator("div, button, mat-card").all()
            for opt in options:
                try:
                    txt = opt.inner_text().lower() if opt.is_visible() else ""
                    if "tts" in txt and (target_model.lower() in txt or short_target in txt):
                        target_option = opt
                        break
                except Exception:
                    continue

        if target_option and target_option.is_visible():
            human_click(page, target_option)
            print(f"[SYSTEM] Successfully assigned TTS Model to '{target_model}'")
            time.sleep(1.2)

            close_btn = page.locator(
                "mat-dialog-container button[aria-label*='Close' i], mat-dialog-container button:has-text('Close')"
            ).first
            if close_btn.is_visible():
                human_click(page, close_btn)
                time.sleep(0.8)
            return True
        else:
            print(
                f"[WARNING] Target model option '{target_model}' not found in modal dialog. Escaping..."
            )
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"[WARNING] Model selection dialog error: {e}")
        page.keyboard.press("Escape")
        return False


def reapply_speech_settings(page, options):
    """Re-applies preset voice model settings from voice_option_notes.txt directly into the Speech Playground."""
    target_model = options.get("model", "gemini-2.5-pro-preview-tts")
    temp_val = options.get("temperature", "1.1")
    voice_name = options.get("voice", "Achird")

    print(
        f"Re-applying Speech Playground settings (Model {target_model}, Temperature {temp_val}, speaker {voice_name})..."
    )

    # 0. Bypass Splash screen
    splash_selector = "text='Turn text into natural-sounding speech...'"
    try:
        if page.locator(splash_selector).is_visible():
            human_click(page, page.locator(splash_selector).first)
            time.sleep(2)
    except Exception:
        pass

    # 1. Ensure Model settings sidebar panel is expanded
    try:
        settings_btn = page.locator("ms-run-settings button[aria-label*='Model settings']").first
        if settings_btn.is_visible():
            human_click(page, settings_btn)
            time.sleep(1.2)
    except Exception as e:
        print(f"Model settings dropdown click: {e}")

    # 2. Select Target TTS Model
    select_ai_studio_tts_model(page, target_model)

    # 3. Ensure Text mode
    try:
        text_btn = page.locator("button:has-text('Text')").first
        if text_btn.is_visible():
            human_click(page, text_btn)
            time.sleep(1.2)
    except Exception as e:
        print(f"Text mode option check: {e}")

    # 4. Temperature slider adjustment
    try:
        temp_input = None
        temp_selectors = [
            "ms-run-settings input[type='number']",
            "ms-run-settings input.slider-number-input",
            "input[type='number']",
            "ms-run-settings input",
        ]
        for sel in temp_selectors:
            loc = page.locator(sel).first
            if loc.is_visible():
                temp_input = loc
                break

        if temp_input:
            human_click(page, temp_input)
            page.keyboard.press("Control+a")
            time.sleep(0.1)
            page.keyboard.press("Backspace")
            time.sleep(0.1)
            page.keyboard.type(temp_val)
            page.keyboard.press("Enter")
            print(f"Successfully set Temperature slider to: {temp_val}")
            time.sleep(1.2)
        else:
            print("Warning: Could not find Temperature input box.")
    except Exception as e:
        print(f"Could not adjust temperature slider input: {e}")

    # 5. Speaker configuration (Voice Selection)
    try:
        speaker_card = None
        card_selectors = [
            "ms-run-settings .active-voice-card",
            "ms-run-settings mat-card",
            "ms-run-settings .voice-card",
            "ms-run-settings [aria-label*='Speaker' i]",
            "ms-run-settings :text('Speaker 1')",
        ]
        for sel in card_selectors:
            loc = page.locator(sel).first
            if loc.is_visible():
                speaker_card = loc
                break

        if speaker_card:
            human_click(page, speaker_card)
            time.sleep(2.0)

            voice_option = page.locator(
                f"mat-dialog-container :text('{voice_name}'), mat-dialog-container button:has-text('{voice_name}'), :text('{voice_name}')"
            ).first
            if voice_option.is_visible():
                human_click(page, voice_option)
                print(f"Successfully assigned speaker to: {voice_name}")
                time.sleep(1.2)

                close_btn = page.locator(
                    "mat-dialog-container button:has-text('Close'), mat-dialog-container button:has-text('OK'), mat-dialog-container button[aria-label*='Close' i]"
                ).first
                if close_btn.is_visible():
                    human_click(page, close_btn)
                    time.sleep(1.2)
            else:
                print(f"Warning: Could not find voice '{voice_name}' in selection modal dialog.")
        else:
            print("Warning: Could not locate active speaker card button.")
    except Exception as e:
        print(f"Could not set speaker config: {e}")

    # 6. Collapse settings sidebar to make editing field fully open
    try:
        close_sidebar_btn = page.locator("button[aria-label*='Close run settings panel']").first
        if close_sidebar_btn.is_visible():
            human_click(page, close_sidebar_btn)
            print("Successfully closed sidebar settings panel.")
            time.sleep(1.2)
    except Exception as e:
        print(f"Could not collapse sidebar setting: {e}")


def get_file_md5(file_path):
    if not os.path.exists(file_path):
        return None
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"Warning: Could not calculate MD5 for {file_path}: {e}")
        return None


def is_valid_wav_file(file_path, min_frames=1000):
    """Verifies the file is a readable, non-truncated WAV containing actual audio frames.

    Guards against AI Studio serving silent failures: quota-limited or 500-errored
    downloads often land as a bare ~44-byte RIFF header or a truncated stream that
    passes a naive getsize() check but poisons stitch/whisper far downstream.
    """
    try:
        if not os.path.exists(file_path) or os.path.getsize(file_path) < 500:
            return False
        with wave.open(file_path, "rb") as wf:
            return wf.getnchannels() > 0 and wf.getframerate() > 0 and wf.getnframes() >= min_frames
    except Exception:
        return False


def is_ai_studio_quota_error(text: str) -> bool:
    """Detects whether an AI Studio error text or modal signifies quota saturation or account restriction."""
    if not text:
        return False
    t = text.lower()
    quota_keywords = [
        "403",
        "link a paid api key",
        "link a paid project",
        "paid api key",
        "quota exceeded",
        "quota",
        "resource has been exhausted",
        "resource exhausted",
        "rate limit",
        "too many requests",
        "billing",
    ]
    return any(k in t for k in quota_keywords)


def check_ai_studio_errors(page):
    error_selectors = [
        "text='Link a paid API key'",
        "text='Paid API key'",
        "text='Link a paid project'",
        "text='Http response'",
        "text='status code: 403'",
        "text='status code'",
        "text='500 Internal Server Error'",
        "text='Quota Exceeded'",
        "text='quota exceeded'",
        "text='Resource has been exhausted'",
        "mat-dialog-container:has-text('paid')",
        "mat-dialog-container:has-text('API key')",
        "mat-dialog-container:has-text('quota')",
        "[role='dialog']:has-text('paid')",
        "[role='dialog']:has-text('API key')",
        "mat-snack-bar-container",
        ".error-container",
    ]
    for sel in error_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                error_text = loc.inner_text().strip()
                print(f"[ALERT] Detected AI Studio Error Banner: '{error_text}'")
                dismiss_btn = page.locator(
                    "button:has-text('Close'), button:has-text('Cancel'), button:has-text('Dismiss'), mat-snack-bar-container button"
                ).first
                if dismiss_btn.is_visible():
                    try:
                        dismiss_btn.click()
                    except Exception:
                        pass
                return True, error_text
        except Exception:
            continue
    return False, ""


def main():
    """Lease the shared browser before any TTS run can touch CDP."""
    latest_run = sys.argv[1] if len(sys.argv) > 1 else get_latest_run_folder()
    if latest_run and os.path.isfile(os.path.join(latest_run, "episode_brief.json")):
        if len(sys.argv) <= 1:
            raise ValueError("Adaptive voice generation requires an explicit run directory")
    from youtube_automation.production.ledger import leased_resource, resource_database

    with leased_resource(resource_database(), "browser"):
        return _run_voice_generation()


class AdaptiveBrowserOwnershipError(RuntimeError):
    """Adaptive TTS cannot take over or terminate an unowned browser process."""


def connect_tts_browser(playwright, *, adaptive, browser_type, profile_index, port):
    """Attach to CDP; only the legacy path may launch a replacement process."""
    endpoint = f"http://127.0.0.1:{port}"
    try:
        browser = playwright.chromium.connect_over_cdp(endpoint)
        print(f"Successfully connected to existing {browser_type.capitalize()} session.")
        return browser
    except Exception as exc:
        if adaptive:
            raise AdaptiveBrowserOwnershipError(
                "Adaptive TTS requires an existing CDP browser session"
            ) from exc
    print("Debugging browser is closed or unreachable. Launching framework...")
    if not launch_browser_with_profile(browser_type, profile_index):
        sys.exit(1)
    return playwright.chromium.connect_over_cdp(endpoint)


def _run_voice_generation():
    print("=============================================")
    print("Starting Voice Generation Automation (Manifest Upgraded)")
    print("=============================================")

    # Parse initial preset configuration choices (voice_option_notes.txt)
    voice_options = read_voice_options()

    # Fetch target LLM model for Tab 2
    target_llm_model = get_config_value("VOICE_GENERATOR_MODEL", "Flash-Lite")

    latest_run = sys.argv[1] if len(sys.argv) > 1 else get_latest_run_folder()
    if not latest_run:
        print("Error: No active run folders found in 'youtube_runs/'.")
        sys.exit(1)

    adaptive_brief = None
    if os.path.isfile(os.path.join(latest_run, "episode_brief.json")):
        if len(sys.argv) <= 1:
            raise ValueError("Adaptive voice generation requires an explicit run directory")
        from youtube_automation.production.contracts import load_brief
        from youtube_automation.production.narration import require_unpolished_run
        from youtube_automation.production.writing import verify_written_episode
        verify_written_episode(latest_run)
        adaptive_brief = load_brief(latest_run)
        if adaptive_brief.channel.voice is None or os.path.isfile(
            os.path.join(latest_run, "source_audio_receipt.json")
        ):
            raise ValueError("This adaptive run has no synthesis voice or preserves source narration")
        require_unpolished_run(latest_run)
        voice_options["voice"] = adaptive_brief.channel.voice

    # File selection logic for transcript input
    refined_primary = os.path.join(latest_run, "refined_script.txt")
    refined_secondary = os.path.join(latest_run, "refine_script.txt")
    raw_final_output = os.path.join(latest_run, "final_output.txt")

    if os.path.exists(refined_primary):
        transcript_path = refined_primary
        print(f"[INPUT SOURCE] Active script file selected: '{transcript_path}'")
    elif os.path.exists(refined_secondary):
        transcript_path = refined_secondary
        print(f"[INPUT SOURCE] Active script file selected: '{transcript_path}'")
    elif os.path.exists(raw_final_output):
        transcript_path = raw_final_output
        print(
            f"[INPUT SOURCE] Refined script not found. Falling back to raw transcript: '{transcript_path}'"
        )
    else:
        print(
            f"Error: No valid script file ('refined_script.txt' or 'final_output.txt') found in '{latest_run}'"
        )
        sys.exit(1)

    # Dedicated folder for downloaded audio tracks
    voice_folder = os.path.join(latest_run, "voice_chapters")
    os.makedirs(voice_folder, exist_ok=True)
    print(f"[OUTPUT] Voice chapters will be saved inside: '{voice_folder}'")

    # Invalid adaptive checkpoints must never be reset to an empty manifest.
    if adaptive_brief and os.path.isfile(get_manifest_path(latest_run)):
        with open(get_manifest_path(latest_run), encoding="utf-8") as handle:
            json.load(handle)
    manifest = load_or_create_manifest(latest_run, voice_options)
    if not adaptive_brief:
        sync_audio_manifest(latest_run, manifest)
    voice_config = manifest.get("voice_config", voice_options)
    target_tts_model = voice_config.get("model", "gemini-2.5-pro-preview-tts")

    if adaptive_brief:
        if voice_config.get("voice") != adaptive_brief.channel.voice:
            raise ValueError("Cached voice manifest conflicts with selected channel voice")
        # The validated refined script itself is the voice source. A second Gemini
        # rewriting pass would change facts and impose the legacy channel persona.
        tts_prompt = ""
    else:
        tts_prompt = loader.render("tts")

    with open(transcript_path, encoding="utf-8") as f:
        transcript_text = f.read().strip()

    if adaptive_brief:
        from youtube_automation.production.narration import prepare_manifest

        manifest = prepare_manifest(latest_run, manifest, adaptive_brief, transcript_text)
        save_manifest(latest_run, manifest)
        sync_audio_manifest(latest_run, manifest)

    # Legacy Gemini harvesting still uses its own coverage and fallback policy.
    payload_path = os.path.join(latest_run, "tts_payload.json")
    coverage = 1.0 if adaptive_brief else calculate_script_coverage(manifest, transcript_text)

    # If manifest chapters are truncated (< 85% script coverage) or empty, fall back to deterministic partitioning
    if manifest.get("chapters") and coverage < 0.85:
        print(
            f"[COVERAGE ALERT] Existing manifest chapters only cover {coverage:.1%} of script (<85%). "
            f"Invalidating truncated chapters and falling back to deterministic partitioning..."
        )
        manifest["chapters"] = partition_script_to_chapters(latest_run, transcript_text)
        manifest["gemini_completed"] = True
        save_manifest(latest_run, manifest)
        sync_audio_manifest(latest_run, manifest)
    elif not manifest.get("chapters"):
        if os.path.exists(payload_path):
            print("[AUTONOMOUS PARTITION] Slicing script deterministically from tts_payload.json (100% coverage)...")
            manifest["chapters"] = partition_script_to_chapters(latest_run, transcript_text)
            manifest["gemini_completed"] = True
            save_manifest(latest_run, manifest)
            sync_audio_manifest(latest_run, manifest)
        else:
            is_gemini_ready = check_is_gemini_complete(manifest, transcript_text)
            if is_gemini_ready and not manifest.get("gemini_completed"):
                manifest["gemini_completed"] = True
                save_manifest(latest_run, manifest)

    print(f"Target Video Folder: {latest_run}")
    print("Verified input files. Connecting to Browser debugging session...")

    # Main Playwright Outer Recovery Loop
    outer_cycle_count = 0
    MAX_OUTER_CYCLES = 10
    while True:
        outer_cycle_count += 1
        if outer_cycle_count > MAX_OUTER_CYCLES:
            raise RuntimeError(
                f"[DEADLOCK CIRCUIT BREAKER] Exceeded maximum outer recovery cycles ({MAX_OUTER_CYCLES}). "
                "Halting to prevent infinite loop. Check network and UI selectors."
            )
        failover_triggered = False

        try:
            with sync_playwright() as p, ExitStack() as owned_tabs:
                switch_enabled_str = (
                    get_runtime_state(
                        "SWITCH_ACCOUNTS_ENABLED",
                        get_config_value("SWITCH_ACCOUNTS_ENABLED", "true"),
                    )
                    .strip()
                    .lower()
                )
                accounts_enabled = switch_enabled_str in ("true", "1", "yes")
                if adaptive_brief:
                    # Legacy failover terminates the process on the CDP port.
                    # Until browser ownership is tracked, adaptive runs must
                    # leave that process and the global account index alone.
                    accounts_enabled = False
                current_profile_idx = get_runtime_state(
                    "ACTIVE_PROFILE_INDEX",
                    get_config_value("ACTIVE_PROFILE_INDEX", "1"),
                )
                browser_type = get_config_value("BROWSER_TYPE", "chrome")
                cdp_port = int(get_config_value("CDP_PORT", "9222"))

                browser = connect_tts_browser(
                    p, adaptive=bool(adaptive_brief), browser_type=browser_type,
                    profile_index=current_profile_idx, port=cdp_port,
                )

                context = browser.contexts[0]
                owned_speech_page = None
                if adaptive_brief:
                    owned_speech_page = context.new_page()
                    owned_tabs.callback(owned_speech_page.close)
                    owned_speech_page.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                    )
                else:
                    context.grant_permissions(["clipboard-read", "clipboard-write"])
                    context.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                    )

                # =========================================================
                # PHASE 1: GEMINI APP SCRIPT ORCHESTRATION (ALL TEXT FIRST)
                # =========================================================
                if manifest.get("gemini_completed") and len(manifest.get("chapters", [])) > 0:
                    print("\n=========================================================")
                    print("[MANIFEST VERIFIED] Gemini script generation is 100% complete!")
                    print(f"Total stored chapters ready for synthesis: {len(manifest['chapters'])}")
                    print("=========================================================\n")
                else:
                    print("\n=========================================================")
                    print("--- PHASE 1: GENERATING ALL VOICE SCRIPT PROMPTS IN GEMINI ---")
                    print("=========================================================")

                    tab2_chat = None
                    for page in context.pages:
                        if "gemini.google.com" in page.url:
                            tab2_chat = page
                            break
                    if not tab2_chat:
                        print("Opening Gemini Web App Tab...")
                        tab2_chat = context.new_page()
                        tab2_chat.goto(
                            "https://gemini.google.com/app", wait_until="domcontentloaded"
                        )
                        time.sleep(3)

                    tab2_chat.bring_to_front()
                    is_resumed = prepare_gemini_chat_session(tab2_chat, manifest)
                    select_gemini_model(tab2_chat, target_llm_model)

                    if not is_resumed:
                        # 1. Send TTS_PROMPT payload
                        print("Pasting guidelines payload (TTS_PROMPT) to Gemini...")
                        send_gemini_prompt(tab2_chat, tts_prompt)
                        wait_for_gemini_response(tab2_chat, step_name="Rules Confirmation")

                        # 2. Upload transcript script to Chat
                        print("Submitting the raw transcript script to Gemini...")
                        send_gemini_prompt(
                            tab2_chat, f"This is My Transcript script:\n\n{transcript_text}"
                        )

                        # Capture breakdown structure & voice recommendation options
                        breakdown_response = wait_for_gemini_response(
                            tab2_chat, step_name="Breakdown Structure & Voice Recommendations"
                        )
                        manifest["archetype_plan"] = breakdown_response
                        save_manifest(latest_run, manifest)
                        print("[MANIFEST] Saved voice recommendation options and breakdown plan.")

                        # 3. Trigger run flow with Option A selection
                        print(
                            "Triggering run flow with 'Choose the Option A and proceed.' command..."
                        )
                        send_gemini_prompt(tab2_chat, "Choose the Option A and proceed.")
                        wait_for_gemini_response(tab2_chat, step_name="Chapter 1 Text Setup")

                        # 4. Confirmation check
                        confirmation_text = get_last_response(tab2_chat)
                        if (
                            "confirm" in confirmation_text.lower()
                            or "ready with the first" in confirmation_text.lower()
                        ):
                            print(
                                "Gemini is waiting for voice confirmation. Sending 'proceed' to trigger Section 1 script generation..."
                            )
                            send_gemini_prompt(tab2_chat, "proceed")
                            wait_for_gemini_response(
                                tab2_chat, step_name="Actual Section 1 Script Text"
                            )

                    # Harvest remaining script chapters from Gemini
                    existing_chapters_count = len(manifest.get("chapters", []))
                    current_chap_idx = existing_chapters_count + 1

                    # Harvest reliability counters: empty/unparsable responses must
                    # never loop forever. After FAILOVER_RETRY_LIMIT stalls we nudge
                    # the chat (max MAX_HARVEST_NUDGES per run), then escalate via
                    # profile rotation when enabled, mirroring the audio-side path.
                    harvest_attempts = 0
                    nudges_sent = 0
                    consecutive_repeats = 0
                    max_harvest_retries = int(get_config_value("FAILOVER_RETRY_LIMIT", "3"))
                    max_nudges = int(get_config_value("MAX_HARVEST_NUDGES", "2"))

                    def _escalate_harvest_failure(chap_idx, reason, switching_enabled):
                        """Rotates profile when account switching is on, else hard-stops."""
                        nonlocal failover_triggered
                        if switching_enabled:
                            print(
                                f"\n[FAILOVER ALERT] Text harvest stalled on Chapter {chap_idx}: {reason}. Rotating Account Profile..."
                            )
                            rotate_profile_index()
                            kill_cdp_chrome()
                            failover_triggered = True
                            raise Exception(
                                f"Text harvest failed for Chapter {chap_idx} ({reason}). Triggering profile rotation."
                            )
                        raise Exception(
                            f"[FATAL ERROR] Text harvest failed for Chapter {chap_idx} after repeated attempts ({reason}). Halting."
                        )

                    while True:
                        print(f"\nHarvesting Chapter {current_chap_idx} script from Gemini...")
                        raw_content = get_last_response(tab2_chat)

                        if not raw_content or len(raw_content.strip()) < 10:
                            harvest_attempts += 1
                            print(
                                f"[RETRY {harvest_attempts}/{max_harvest_retries}] Empty response for Chapter {current_chap_idx}. Waiting..."
                            )
                            if harvest_attempts >= max_harvest_retries:
                                if nudges_sent >= max_nudges:
                                    _escalate_harvest_failure(
                                        current_chap_idx,
                                        "persistent empty responses",
                                        accounts_enabled,
                                    )
                                print(
                                    f"[NUDGE {nudges_sent + 1}/{max_nudges}] Chat appears stalled. Sending recovery nudge..."
                                )
                                send_gemini_prompt(tab2_chat, "proceed")
                                wait_for_gemini_response(
                                    tab2_chat, step_name=f"Chapter {current_chap_idx} Recovery"
                                )
                                nudges_sent += 1
                                harvest_attempts = 0
                            time.sleep(3)
                            continue

                        # Check completion signal
                        has_arabic = bool(re.search(r"[\u0600-\u06FF]", raw_content))
                        is_complete = check_is_gemini_complete(
                            manifest, transcript_text, raw_content
                        )

                        if not has_arabic:
                            print(
                                "[COMPLETED] Detected final non-Arabic/completion signal from Gemini."
                            )
                            manifest["gemini_completed"] = True
                            save_manifest(latest_run, manifest)
                            print(
                                f"[MANIFEST] Gemini script extraction complete. Total chapters saved: {len(manifest['chapters'])}"
                            )
                            break

                        markdown_content = sanitize_script_text(raw_content)
                        if not markdown_content:
                            harvest_attempts += 1
                            print(
                                f"[RETRY {harvest_attempts}/{max_harvest_retries}] Sanitized content empty. Retrying..."
                            )
                            if harvest_attempts >= max_harvest_retries:
                                if nudges_sent >= max_nudges:
                                    _escalate_harvest_failure(
                                        current_chap_idx,
                                        "sanitizer produced no usable text",
                                        accounts_enabled,
                                    )
                                print(
                                    f"[NUDGE {nudges_sent + 1}/{max_nudges}] Chat appears stalled. Sending recovery nudge..."
                                )
                                send_gemini_prompt(tab2_chat, "proceed")
                                wait_for_gemini_response(
                                    tab2_chat, step_name=f"Chapter {current_chap_idx} Recovery"
                                )
                                nudges_sent += 1
                                harvest_attempts = 0
                            time.sleep(3)
                            continue

                        # Anti-drift guard: Gemini re-generating the previous chapter on
                        # repeated "proceed" is the classic end-of-context loop. Two
                        # consecutive strikes (>0.90 similarity) => wrap up; a single
                        # strike just discards and re-requests (avoids false positives
                        # from shared outro boilerplate between legitimate chapters).
                        prev_chapter_text = (
                            manifest["chapters"][-1].get("text", "")
                            if manifest.get("chapters")
                            else ""
                        )
                        if prev_chapter_text:
                            repetition_ratio = difflib.SequenceMatcher(
                                None, markdown_content, prev_chapter_text
                            ).ratio()
                            if repetition_ratio > 0.90:
                                consecutive_repeats += 1
                                if consecutive_repeats >= 2:
                                    print(
                                        f"[COMPLETED] Repetition loop confirmed ({repetition_ratio:.0%} match, twice consecutively). Wrapping up."
                                    )
                                    manifest["gemini_completed"] = True
                                    save_manifest(latest_run, manifest)
                                    break
                                print(
                                    f"[DRIFT GUARD] Chapter {current_chap_idx} repeats previous chapter ({repetition_ratio:.0%}). Strike {consecutive_repeats}/2. Re-requesting..."
                                )
                                send_gemini_prompt(tab2_chat, "proceed")
                                wait_for_gemini_response(
                                    tab2_chat, step_name=f"Chapter {current_chap_idx} Drift Retry"
                                )
                                continue
                        consecutive_repeats = 0

                        audio_dest_path = os.path.join(
                            voice_folder, f"Chapter_{current_chap_idx}.wav"
                        )

                        existing_chap_entry = next(
                            (
                                c
                                for c in manifest["chapters"]
                                if c["chapter_num"] == current_chap_idx
                            ),
                            None,
                        )
                        if existing_chap_entry:
                            existing_chap_entry["text"] = markdown_content
                            existing_chap_entry["audio_file"] = audio_dest_path
                        else:
                            manifest["chapters"].append(
                                {
                                    "chapter_num": current_chap_idx,
                                    "text": markdown_content,
                                    "audio_file": audio_dest_path,
                                    "status": "PENDING",
                                }
                            )

                        save_manifest(latest_run, manifest)
                        print(
                            f"[MANIFEST] Saved Chapter {current_chap_idx} text ({len(markdown_content)} chars)."
                        )

                        # Re-verify completeness after saving this chapter
                        if is_complete or check_is_gemini_complete(
                            manifest, transcript_text, raw_content
                        ):
                            print(
                                "[COMPLETED] Manifest verification confirmed all blocks collected."
                            )
                            manifest["gemini_completed"] = True
                            save_manifest(latest_run, manifest)
                            break

                        # Request next chapter from Gemini
                        print(f"Requesting Chapter {current_chap_idx + 1} script...")
                        send_gemini_prompt(tab2_chat, "proceed")
                        wait_for_gemini_response(
                            tab2_chat, step_name=f"Chapter {current_chap_idx + 1} Text"
                        )
                        current_chap_idx += 1

                # =========================================================
                # PHASE 2: GOOGLE AI STUDIO VOICE SYNTHESIS (ALL AUDIO SECOND)
                # =========================================================
                print("\n=========================================================")
                print("--- PHASE 2: GENERATING VOICE AUDIO TRACKS IN GOOGLE AI STUDIO ---")
                print("=========================================================")

                # Guarantee Playwright is focused on the genuine Speech Playground tab with target model URL
                tab1_speech = ensure_speech_playground_tab(
                    context, target_tts_model, owned_page=owned_speech_page
                )
                reapply_speech_settings(tab1_speech, voice_config)

                latest_alkali_state = {"status": None, "url": None, "is_403": False}

                def _on_speech_response(response, state=latest_alkali_state):
                    if "alkalimakersuite" in response.url and response.status == 403:
                        state["is_403"] = True
                        state["status"] = 403
                        state["url"] = response.url
                        print(f"\n[NETWORK AUDIT] Captured HTTP 403 from alkalimakersuite: {response.url}")

                tab1_speech.on("response", _on_speech_response)

                main.attempt_count = 0
                chapters_since_reload = 0

                # Iterate through all saved chapters from manifest
                for chap_entry in manifest.get("chapters", []):
                    chap_num = chap_entry["chapter_num"]
                    chap_text = chap_entry["text"]
                    target_dest = chap_entry.get("audio_file") or os.path.join(
                        voice_folder, f"Chapter_{chap_num}.wav"
                    )
                    if not os.path.isabs(target_dest):
                        target_dest = os.path.abspath(os.path.join(latest_run, target_dest))

                    # Check if audio file is already completed and verified
                    if chap_entry.get("status") == "COMPLETED" and is_valid_wav_file(target_dest):
                        print(
                            f"[SKIP] Chapter {chap_num} audio already generated and verified at '{target_dest}'."
                        )
                        continue

                    while True:
                        latest_alkali_state["is_403"] = False
                        print(
                            f"\nSynthesizing Audio for Chapter {chap_num} (Attempt {getattr(main, 'attempt_count', 0) + 1})..."
                        )

                        # URL Guardrail check to prevent typing into standard AI Studio prompt tabs
                        if "generate-speech" not in tab1_speech.url:
                            print(
                                "[SAFETY CHECK] Correcting tab navigation to Speech Playground..."
                            )
                            try:
                                tab1_speech.goto(
                                    f"https://aistudio.google.com/generate-speech?model={target_tts_model}",
                                    wait_until="domcontentloaded",
                                    timeout=30000,
                                )
                                time.sleep(3)
                                reapply_speech_settings(tab1_speech, voice_config)
                            except Exception as nav_err:
                                print(f"[WARNING] Speech Playground navigation warning: {nav_err}")
                                time.sleep(2)

                        reload_limit = int(get_config_value("TTS_PROACTIVE_RELOAD_INTERVAL", "40"))
                        if chapters_since_reload >= reload_limit:
                            print(
                                "\n[MAINTENANCE] Proactively refreshing Speech Playground session..."
                            )
                            tab1_speech.bring_to_front()
                            try:
                                tab1_speech.locator("body").first.click(timeout=1000)
                                time.sleep(0.5)
                            except Exception:
                                pass
                            tab1_speech.reload(wait_until="domcontentloaded")
                            time.sleep(5)
                            reapply_speech_settings(tab1_speech, voice_config)
                            chapters_since_reload = 0

                        # Recovery reload if prior attempt failed
                        if getattr(main, "attempt_count", 0) > 0:
                            print(
                                "[RECOVER] Reloading Speech Playground Tab to refresh credentials..."
                            )
                            tab1_speech.bring_to_front()
                            try:
                                tab1_speech.locator("body").first.click(timeout=1000)
                                time.sleep(0.5)
                            except Exception:
                                pass
                            tab1_speech.reload(wait_until="domcontentloaded")
                            time.sleep(5)
                            reapply_speech_settings(tab1_speech, voice_config)
                            chapters_since_reload = 0

                        tab1_speech.bring_to_front()
                        try:
                            tab1_speech.locator("body").first.click(timeout=1000)
                            time.sleep(0.5)
                        except Exception:
                            pass

                        speech_input = tab1_speech.locator(
                            "textarea[aria-label='Enter a prompt']"
                        ).first
                        if not speech_input.is_visible():
                            print("Speech Playground input box was hidden. Re-applying speech settings to dismiss splash...")
                            reapply_speech_settings(tab1_speech, voice_config)
                            time.sleep(2)
                            speech_input = tab1_speech.locator(
                                "textarea[aria-label='Enter a prompt']"
                            ).first
                            if not speech_input.is_visible():
                                main.attempt_count = getattr(main, "attempt_count", 0) + 1
                                time.sleep(2)
                                continue

                        clean_text = sanitize_script_text(chap_text)
                        print(f"Entering Chapter {chap_num} script text into AI Studio ({len(clean_text)} chars)...")
                        humanize_text_input(tab1_speech, speech_input, clean_text)

                        # Dynamic delay scaled to text length
                        text_length = len(chap_text)
                        base_delay = 3.0
                        scaled_delay = (text_length / 500.0) * random.uniform(1.2, 2.8)
                        cooldown_time = base_delay + scaled_delay

                        print(
                            f"Applying dynamic safety cooldown of {cooldown_time:.2f}s for {text_length} characters..."
                        )
                        time.sleep(cooldown_time)

                        # Click Run to synthesize audio
                        run_btn = tab1_speech.locator(
                            "button[type='submit'], button:has-text('Run')"
                        ).first
                        try:
                            human_hover_and_click(tab1_speech, run_btn)
                        except Exception:
                            tab1_speech.keyboard.press("Control+Enter")

                        print("Synthesis started. Waiting dynamically for rendering to complete...")
                        started_rendering = False
                        has_error = False
                        err_msg = ""
                        try:
                            tab1_speech.wait_for_selector("button:has-text('Stop')", timeout=8000)
                            print("Synthesis processing confirmed...")
                            started_rendering = True
                        except Exception:
                            has_error, err_msg = check_ai_studio_errors(tab1_speech)
                            if has_error:
                                print(f"Synthesis failed due to AI Studio error: {err_msg}")
                            else:
                                print("Warning: Synthesis 'Stop' button did not appear within 8s.")

                        # Immediate Quota / 403 Failover Gate (Directive: HTTP 403 / "Link a paid API key")
                        is_quota = (
                            latest_alkali_state.get("is_403")
                            or (has_error and is_ai_studio_quota_error(err_msg))
                        )
                        if is_quota:
                            if accounts_enabled:
                                print(
                                    f"\n[FAILOVER ALERT] Quota saturated / HTTP 403 detected on active profile "
                                    f"(Banner: '{err_msg}', Network 403: {latest_alkali_state.get('is_403')}). "
                                    f"Switching immediately to next active account profile..."
                                )
                                rotate_profile_index()
                                kill_cdp_chrome()
                                failover_triggered = True
                                break
                            else:
                                print(
                                    "\n[FATAL ERROR] Quota saturated (HTTP 403 / 'Link a paid API key') and SWITCH_ACCOUNTS_ENABLED is false. Halting."
                                )
                                sys.exit(1)

                        if not started_rendering:
                            print("[RETRY TRIGGER] Synthesis failed to start. Reloading session...")
                            if os.path.exists(target_dest):
                                try:
                                    os.remove(target_dest)
                                except Exception:
                                    pass
                            main.attempt_count = getattr(main, "attempt_count", 0) + 1
                            retry_limit = int(get_config_value("FAILOVER_RETRY_LIMIT", "3"))
                            if getattr(main, "attempt_count", 0) >= retry_limit:
                                if accounts_enabled:
                                    print(
                                        f"\n[FAILOVER ALERT] Chapter {chap_num} failed {retry_limit} times to start. Rotating Account Profile..."
                                    )
                                    rotate_profile_index()
                                    kill_cdp_chrome()
                                    failover_triggered = True
                                    break
                                else:
                                    print(
                                        f"\n[FATAL ERROR] Chapter {chap_num} failed after {retry_limit} attempts. Halting."
                                    )
                                    sys.exit(1)
                            continue

                        synth_timeout_ms = (
                            int(get_config_value("TTS_SYNTHESIS_TIMEOUT", "300")) * 1000
                        )
                        try:
                            tab1_speech.wait_for_selector(
                                "button:has-text('Run')", timeout=synth_timeout_ms
                            )
                            print("Audio synthesis complete!")
                        except Exception as e:
                            print(f"Warning: Timeout or error waiting for synthesis: {e}")

                        time.sleep(2.0)

                        # Download synthesized audio file
                        download_btn = tab1_speech.locator(
                            "button[aria-label*='Download' i], button:has-text('Download')"
                        ).first
                        try:
                            download_btn.wait_for(state="visible", timeout=10000)
                        except Exception:
                            pass

                        download_success = False
                        if download_btn.is_visible():
                            try:
                                with tab1_speech.expect_download(timeout=15000) as download_info:
                                    human_hover_and_click(tab1_speech, download_btn)
                                download = download_info.value
                                download.save_as(target_dest)
                                print(f"Audio file downloaded and saved: {target_dest}")
                                download_success = True
                            except PlaywrightTimeoutError:
                                print(
                                    "\n[TIMEOUT] Playwright timed out waiting for download event."
                                )
                            except Exception as e:
                                print(f"\n[ERROR] Error downloading audio file: {e}")

                        # Frame-level validation: a "successful" download can still be a
                        # bare RIFF header or truncated stream (quota/500 failures).
                        # Treat invalid audio exactly like a failed download.
                        if download_success and not is_valid_wav_file(target_dest):
                            print(
                                f"[ALERT] Downloaded WAV for Chapter {chap_num} failed frame validation (corrupt/truncated). Treating as failure."
                            )
                            try:
                                os.remove(target_dest)
                            except Exception:
                                pass
                            download_success = False

                        if download_success:
                            current_md5 = get_file_md5(target_dest)

                            # Global MD5 dedup: compare against every prior COMPLETED
                            # chapter's stored hash, with disk fallback for the immediate
                            # predecessor when legacy manifests lack the md5 field.
                            prior_md5s = {
                                c.get("md5") for c in manifest.get("chapters", []) if c.get("md5")
                            }
                            if chap_num > 1 and current_md5:
                                previous_dest = os.path.join(
                                    voice_folder, f"Chapter_{chap_num - 1}.wav"
                                )
                                if os.path.exists(previous_dest):
                                    prior_md5s.add(get_file_md5(previous_dest))
                            prior_md5s.discard(None)

                            if current_md5 and current_md5 in prior_md5s:
                                print(
                                    f"\n[ALERT] Duplicate audio detected for Chapter {chap_num} (MD5 match with a prior chapter). Discarding stale file."
                                )
                                try:
                                    os.remove(target_dest)
                                except Exception:
                                    pass
                                # If HTTP 403 was detected from alkalimakersuite, trigger account rotation immediately
                                if latest_alkali_state.get("is_403"):
                                    if accounts_enabled:
                                        print(
                                            f"\n[FAILOVER ALERT] Quota saturated / HTTP 403 confirmed by duplicate download on Chapter {chap_num}. "
                                            "Switching immediately to next active account profile..."
                                        )
                                        rotate_profile_index()
                                        kill_cdp_chrome()
                                        failover_triggered = True
                                        break
                                    else:
                                        print(
                                            "\n[FATAL ERROR] Quota saturated (HTTP 403) and SWITCH_ACCOUNTS_ENABLED is false. Halting."
                                        )
                                        sys.exit(1)

                                main.attempt_count = getattr(main, "attempt_count", 0) + 1
                                continue

                            # Update manifest chapter status to COMPLETED
                            chap_entry["status"] = "COMPLETED"
                            if current_md5:
                                chap_entry["md5"] = current_md5
                            audio_manifest_data = sync_audio_manifest(latest_run, manifest)
                            save_manifest(latest_run, manifest)
                            print(
                                f"[MANIFEST] Chapter {chap_num} marked COMPLETED (MD5: {(current_md5 or 'n/a')[:8]})."
                            )

                            # Real-Time Lead Audio Engineer Telemetry Commentary
                            chap_probe = probe_audio_file(target_dest)
                            wpm = chap_entry.get("words_per_minute", 0)
                            dur = chap_entry.get("duration", 0.0)
                            start_t = chap_entry.get("start_time", 0.0)
                            end_t = chap_entry.get("end_time", 0.0)
                            words = chap_entry.get("words_count", 0)
                            total_dur = audio_manifest_data.get("cumulative_duration_sec", 0.0)
                            mins = int(total_dur // 60)
                            secs = total_dur % 60
                            print("\n" + "=" * 80)
                            print(f"[AUDIO LEAD TELEMETRY] Chunk {chap_num:03d} / Chapter {chap_num}")
                            print(f"- File:                voice_chapters/Chapter_{chap_num}.wav")
                            if chap_probe:
                                print(
                                    f"- Physical Duration:   {dur:.3f}s ({chap_probe['nframes']} frames @ {chap_probe['framerate']} Hz)"
                                )
                                print(
                                    f"- Format:              {chap_probe['framerate']} Hz | {chap_probe['channels']}-Ch | {chap_probe['sampwidth']*8}-bit PCM (PASS)"
                                )
                            print(f"- Timing Span:         {start_t:.3f}s  ==>  {end_t:.3f}s")
                            print(f"- Word Count:          {words} words | Speech Rate: {wpm} WPM")
                            print("- Inter-Chunk Gap:     +0.300s breath interval scheduled for next start")
                            print(f"- MD5 Checksum:        {(current_md5 or 'n/a')[:8]}... (Unique)")
                            print(f"- Cumulative Runtime:  {mins}m {secs:.2f}s")
                            print("=" * 80 + "\n")

                            chapters_since_reload += 1
                            main.attempt_count = 0
                            break
                        else:
                            has_err, err_msg = check_ai_studio_errors(tab1_speech)
                            if (latest_alkali_state.get("is_403") or (has_err and is_ai_studio_quota_error(err_msg))) and accounts_enabled:
                                print(
                                    "\n[FAILOVER ALERT] Quota saturation observed during synthesis/download (HTTP 403 / 'Link a paid API key'). "
                                    "Switching immediately to next active account profile..."
                                )
                                rotate_profile_index()
                                kill_cdp_chrome()
                                failover_triggered = True
                                break

                            main.attempt_count = getattr(main, "attempt_count", 0) + 1
                            retry_limit = int(get_config_value("FAILOVER_RETRY_LIMIT", "3"))

                            if getattr(main, "attempt_count", 0) >= retry_limit:
                                if accounts_enabled:
                                    print(
                                        f"\n[FAILOVER ALERT] Chapter {chap_num} failed {retry_limit} times. Rotating Account Profile..."
                                    )
                                    rotate_profile_index()
                                    kill_cdp_chrome()
                                    failover_triggered = True
                                    break
                                else:
                                    print(
                                        f"\n[FATAL ERROR] Chapter {chap_num} failed after {retry_limit} attempts. Halting."
                                    )
                                    sys.exit(1)

                            backoff_delay = 5.0 * (2.0 ** (getattr(main, "attempt_count", 0) - 1))
                            print(
                                f"Applying exponential backoff of {backoff_delay:.2f}s before retry..."
                            )
                            time.sleep(backoff_delay)

                    if failover_triggered:
                        break

                if failover_triggered:
                    pass
                else:
                    # Exit outer loop when all chapters are successfully synthesized
                    all_done = all(
                        c.get("status") == "COMPLETED" for c in manifest.get("chapters", [])
                    )
                    if all_done:
                        print("\n=============================================")
                        print("ALL VOICE CHAPTERS SUCCESSFULLY GENERATED & SAVED!")
                        print("=============================================")
                        break

        except AdaptiveBrowserOwnershipError:
            raise
        except Exception as e:
            print(f"[RECOVERY] Playwright context closed or browser crashed: {e}")
            time.sleep(3)

        if failover_triggered:
            print(
                "\n[SYSTEM] Reinitializing Playwright environment with new profile. Fast-forwarding...\n"
            )
            main.attempt_count = 0
            time.sleep(2)
            continue

        all_done = all(
            c.get("status") == "COMPLETED" for c in manifest.get("chapters", [])
        )
        if all_done:
            print("\n=============================================")
            print("ALL VOICE CHAPTERS SUCCESSFULLY GENERATED & SAVED!")
            print("=============================================")
            break
        else:
            print("[RECOVERY] Incomplete chapters detected after recovery cycle. Resuming...")
            time.sleep(2)
            continue




__all__ = [
    "AUDIO_MANIFEST_FILE_NAME",
    "CF_UNICODETEXT",
    "DEFAULT_SILENCE_PADDING_SEC",
    "GMEM_MOVEABLE",
    "MANIFEST_FILE_NAME",
    "RESPONSE_SELECTOR",
    "calculate_script_coverage",
    "check_ai_studio_errors",
    "check_is_gemini_complete",
    "clean_text_for_speech",
    "current_mouse_pos",
    "ensure_speech_playground_tab",
    "extract_total_blocks_count",
    "find_input_box",
    "find_send_button",
    "get_file_md5",
    "get_latest_run_folder",
    "get_manifest_path",
    "human_click",
    "human_hover_and_click",
    "humanize_text_input",
    "is_ai_studio_quota_error",
    "is_valid_wav_file",
    "kernel32",
    "load_or_create_manifest",
    "main",
    "partition_script_to_chapters",
    "probe_audio_file",
    "read_voice_options",
    "reapply_speech_settings",
    "sanitize_script_text",
    "save_manifest",
    "select_ai_studio_tts_model",
    "select_gemini_model",
    "send_gemini_prompt",
    "set_clipboard_text",
    "simulate_human_mouse_move",
    "start_clean_gemini_chat",
    "sync_audio_manifest",
    "user32",
    "wait_for_gemini_response",
]


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(
            "\n[SYSTEM] Automation execution interrupted by user (Ctrl+C). Progress checkpoint saved."
        )
        sys.exit(0)
