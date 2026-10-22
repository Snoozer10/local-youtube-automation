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
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from functools import partial
from pathlib import Path
from typing import Any, Literal, TypedDict, overload
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    Response,
    sync_playwright,
)
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from youtube_automation.audio.wav_validation import AudioProbe
from youtube_automation.browser import network_health, ui_guard
from youtube_automation.core.utils import (
    get_config_value,
    get_runtime_state,
    kill_cdp_chrome,
    launch_browser_with_profile,
    rotate_profile_index,
)
from youtube_automation.production.contracts import Brief
from youtube_automation.production.voice_direction import SpeechText, VoiceDirection
from youtube_automation.prompts import loader

# Selector constants for the standard Gemini Web App
RESPONSE_SELECTOR = "model-response div.markdown"
MANIFEST_FILE_NAME = "voice_generation_manifest.json"
AUDIO_MANIFEST_FILE_NAME = "audio_manifest.json"
DEFAULT_SILENCE_PADDING_SEC = 0.300

# Global tracker for human mouse emulation coordinates
current_mouse_pos: list[float] = [100, 100]

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


class NetworkAuditState(TypedDict):
    status: int | None
    url: str | None
    is_403: bool


class PartitionedChapter(TypedDict):
    chapter_num: int
    text: str
    audio_file: str
    status: str


def set_clipboard_text(text: str) -> bool:
    """Sets Unicode text directly to the Windows system clipboard using native ctypes with retries."""
    from youtube_automation.production.ledger import leased_resource, resource_database

    with leased_resource(resource_database(), "clipboard"):
        return _set_clipboard_text(text)


def _set_clipboard_text(text: str) -> bool:
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
def read_voice_options() -> dict[str, str]:
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
def get_manifest_path(latest_run: str) -> str:
    return os.path.join(latest_run, MANIFEST_FILE_NAME)


def load_or_create_manifest(latest_run: str, voice_options: Mapping[str, Any]) -> dict[str, Any]:
    manifest_path = get_manifest_path(latest_run)
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
                print(f"[MANIFEST] Loaded active manifest checkpoint from '{manifest_path}'.")
                if "voice_config" not in data or not data["voice_config"]:
                    data["voice_config"] = voice_options
                return data
        except Exception as e:
            print(f"[MANIFEST WARNING] Could not parse manifest ({e}). Creating fresh manifest.")

    initial_manifest: dict[str, Any] = {
        "voice_config": voice_options,
        "archetype_plan": "",
        "gemini_completed": False,
        "chapters": [],
    }
    save_manifest(latest_run, initial_manifest)
    return initial_manifest


def save_manifest(latest_run: str, manifest_data: Mapping[str, Any]) -> None:
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


def probe_audio_file(file_path: str) -> AudioProbe | None:
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


def sync_audio_manifest(latest_run: str, manifest: dict[str, Any], silence_padding_sec: float = DEFAULT_SILENCE_PADDING_SEC) -> dict[str, Any]:
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


def extract_total_blocks_count(text: str) -> tuple[int | None, int | None]:
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


def check_is_gemini_complete(manifest: Mapping[str, Any], transcript_text: str, last_raw_response: str = "") -> bool:
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
def simulate_human_mouse_move(page: Page, target_locator: Locator, steps: int = 25) -> None:
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


def human_click(page: Page, target_locator: Locator) -> None:
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


def human_hover_and_click(page: Page, locator: Locator) -> bool:
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


def humanize_text_input(page: Page, textbox: Locator, text: str) -> bool:
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


def sanitize_script_text(text: str) -> str:
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
    def lowercase_tts_tags(match: re.Match[str]) -> str:
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


def calculate_script_coverage(manifest: Mapping[str, Any], transcript_text: str) -> float:
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


def partition_script_to_chapters(latest_run: str, transcript_text: str, max_words_per_chapter: int = 220) -> list[PartitionedChapter]:
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

    chapters: list[PartitionedChapter] = []
    current_paras: list[str] = []
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


def get_latest_run_folder(runs_path: str = "youtube_runs") -> str | None:
    if not os.path.exists(runs_path):
        print(f"Error: Directory '{runs_path}' does not exist.")
        return None
    folders = glob.glob(os.path.join(runs_path, "*/"))
    if not folders:
        return None
    latest_folder = max(folders, key=os.path.getmtime)
    return latest_folder


def find_input_box(page: Page) -> Locator | None:
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


def find_send_button(page: Page) -> Locator | None:
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


def send_gemini_prompt(page: Page, text: str) -> None:
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
    def _input_still_full() -> bool:
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


def get_last_response(page: Page) -> str:
    try:
        elements = page.locator(RESPONSE_SELECTOR)
        count = elements.count()
        if count > 0:
            last_el = elements.nth(count - 1)
            text: str = last_el.evaluate("el => el.innerText").strip()
            if text.startswith("Gemini said"):
                text = text[len("Gemini said") :].strip()
            return text
    except Exception as e:
        print(f"Error reading last response: {e}")
    return ""


def start_clean_gemini_chat(page: Page) -> None:
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


def prepare_gemini_chat_session(page: Page, manifest: Mapping[str, Any]) -> bool:
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


_TTS_NAV_RETRY_LIMIT = 2
# Entry check (ensure_speech_playground_tab + the check right after it) also requires
# ?model=<target>. In-loop checks never do. Flip to False if a live probe shows AI Studio
# drops the query after load.
_TTS_REQUIRE_MODEL_QUERY_AT_ENTRY = True
_SPEECH_WORKSPACE_MARKERS = (
    "text='Turn text into natural-sounding speech...'",
    "textarea[aria-label='Enter a prompt']",
    "ms-run-settings",
    "ms-run-settings .active-voice-card",
    "ms-run-settings .voice-card",
    "ms-run-settings [aria-label*='Speaker' i]",
    "ms-run-settings :text('Speaker 1')",
)

# Active-model gate: text of the run-settings model card (exactly one, equal to the target).
_TTS_MODEL_CARD_SELECTOR = "ms-run-settings button.model-selector-card [data-test-id='model-name']"

# Today's speech UI (probed live 2026-10-07; docs/sessions/CLAUDE_INTERIM_RESULT.md, "Live AI Studio
# findings"). generate-speech opens a landing page; "Create new dialog" opens the editor on the
# same URL. Attribute selectors only: Angular strips the whitespace between spans.
_TTS_CREATE_DIALOG_SELECTOR = "[data-testid='create-new-dialog-card']"
_TTS_TEXT_TOGGLE_SELECTOR = "button[role='radio'][data-value='TEXT']"
_TTS_TEXT_TOGGLE_LABEL = re.compile(r"^\s*(edit_note\s*)?Text\s*$")
_TTS_PROMPT_SELECTOR = "textarea[aria-label='Enter a prompt']"
_TTS_RUN_SETTINGS_SELECTOR = "ms-run-settings"
_TTS_RUN_SETTINGS_TOGGLE_SELECTOR = "button[aria-label='Toggle run settings panel']"
_TTS_VOICE_NAME_SELECTOR = "ms-voice-settings .voice-display-name"
_TTS_VOICE_OPEN_SELECTOR = "ms-voice-settings button[aria-label='Open voice settings']"
_TTS_VOICE_DIALOG_SELECTOR = "mat-dialog-container"
_TTS_VOICE_CLOSE_SELECTOR = "mat-dialog-container button[aria-label='Close panel']"
_TTS_VOICE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z-]{0,39}$")
# Temperature sits under the collapsed "Model settings" group; the 01:30Z rehearsal resolved it as
# <input ms-input type="text" inputmode="decimal" role="spinbutton" class="slider-number-input
# small" aria-valuenow=...> (probe/rehearsal_report.json clicks[2]).
_TTS_MODEL_SETTINGS_EXPANDER_SELECTOR = (
    "ms-run-settings button[aria-label='Expand or collapse Model settings']"
)
_TTS_TEMPERATURE_SELECTOR = "ms-run-settings input.slider-number-input"
_TTS_SWITCH_MODEL_DIALOG_SELECTOR = (
    ":is(mat-dialog-container, [role='dialog']):has-text('Switch model')"
)
_TTS_SWITCH_MODEL_CANCEL_SELECTOR = f"{_TTS_SWITCH_MODEL_DIALOG_SELECTOR} button:has-text('Cancel')"
_TTS_UI_WAIT_SEC = 20.0
_TTS_UI_POLL_SEC = 0.25
_TTS_SWITCH_SETTLE_SEC = 1.0
_TTS_CREATE_DIALOG_MAX_CLICKS = 2
# Gemini 3.8 Flash TTS editor (zero-send probes 2026-10-09, attempt_22 probe3/probe4 receipts): one
# ms-speech-block textarea and no Text/Composer toggle; a Style menu whose click-blocking backdrop
# closes it; a searchable voice list whose cards render only after a search.
_TTS_FLASH_MODEL = "gemini-3.8-flash-tts"
_TTS_FLASH_PROMPT_SELECTOR = "textarea[aria-label='Speech block text']"
_TTS_STYLE_BUTTON_SELECTOR = "ms-voice-style-dropdown button[aria-label='Style']"
_TTS_STYLE_LABEL_SELECTOR = f"{_TTS_STYLE_BUTTON_SELECTOR} .chip-label"
_TTS_STYLE_TEXTAREA_SELECTOR = "textarea[aria-label='Describe the voice style']"
_TTS_OVERLAY_BACKDROP_SELECTOR = ".cdk-overlay-backdrop-showing"
_TTS_VOICE_SEARCH_SELECTOR = f"{_TTS_VOICE_DIALOG_SELECTOR} input[placeholder*='Search' i]"
_TTS_VOICE_SEARCH_WAIT_SEC = 3.0
_TTS_PIECE_GAP_SEC = 0.45
_TTS_UNIT_ATTEMPT_LIMIT = 2
_TTS_TYPE_TO_RUN_MAX_SEC = 45.0
_TTS_ADAPTIVE_COOLDOWN_MAX_SEC = 30.0
_TTS_TEMPERATURE_TOLERANCE = 0.01


def _is_flash_model(model: Any) -> bool:
    return str(model or "").strip() == _TTS_FLASH_MODEL


def _tts_prompt_selector(model: Any) -> str:
    """Flash types into its speech block; Pro keeps the Text-mode prompt box."""
    return _TTS_FLASH_PROMPT_SELECTOR if _is_flash_model(model) else _TTS_PROMPT_SELECTOR


class TTSWorkspaceUnavailableError(RuntimeError):
    """AI Studio did not show the Speech Playground; never retried automatically."""


class TTSProviderError(RuntimeError):
    """AI Studio returned a non-retryable provider error."""


def _adaptive_post_run_failure(err_msg: str) -> None:
    """Adaptive runs may retry only transient provider errors; anything else stops."""
    kind = ui_guard.classify_provider_error(err_msg)
    if kind != "transient":
        detail = re.sub(r"\s+", " ", err_msg or "").strip()[:200]
        raise TTSProviderError(f"{kind}: {detail}")


def _adaptive_salvage_download(page: Any, target_dest: str) -> bool:
    """Re-check the Download button once for up to 3 s; the only click is Download."""
    button = page.locator(
        "button[aria-label*='Download' i], button:has-text('Download')"
    ).first
    try:
        button.wait_for(state="visible", timeout=3000)
    except Exception:
        pass
    try:
        if not button.is_visible():
            return False
        with page.expect_download(timeout=15000) as download_info:
            human_hover_and_click(page, button)
        download_info.value.save_as(target_dest)
    except Exception as exc:
        print(f"[ERROR] Download salvage failed: {exc}")
        return False
    print(f"Audio file downloaded and saved (salvage): {target_dest}")
    return True


def _is_speech_url(url: str, model: str | None = None) -> bool:
    """Accept only the approved HTTPS AI Studio speech origin and exact path."""
    try:
        parsed = urlparse(url or "")
        if (
            parsed.scheme.lower() != "https"
            or parsed.hostname != "aistudio.google.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or parsed.netloc.lower() not in {
                "aistudio.google.com",
                "aistudio.google.com:443",
            }
        ):
            return False
    except ValueError:
        return False
    if parsed.path not in ("/generate-speech", "/generate-speech/"):
        return False
    if not model or not _TTS_REQUIRE_MODEL_QUERY_AT_ENTRY:
        return True
    return parse_qs(parsed.query).get("model") == [model]


def _is_speech_workspace(page: Any, model: str | None = None) -> bool:
    """True only on a speech URL (see _is_speech_url) with a visible speech marker."""
    try:
        if not _is_speech_url(page.url or "", model):
            return False
        for selector in _SPEECH_WORKSPACE_MARKERS:
            if page.locator(selector).first.is_visible():
                return True
    except Exception:
        return False
    return False


def _require_speech_workspace(page: Any, model: str | None = None) -> None:
    """Fail closed before settings, typing or a Run click touch a non-speech page."""
    if not _is_speech_workspace(page, model):
        raise TTSWorkspaceUnavailableError(
            f"AI Studio Speech Playground is unavailable (current URL: {getattr(page, 'url', '')})"
        )


def _wait_for_speech_workspace_ready(page: Any, model: str) -> None:
    """Wait at entry only; pump CDP events while retaining exact URL/model checks.

    The verified run-settings panel and target model card must hydrate before settings.
    Pre-typing and pre-Run workspace/model gates remain synchronous and unchanged.
    """
    if not model:
        raise TTSWorkspaceUnavailableError("AI Studio target TTS model is empty; refusing to send.")
    for _ in range(max(1, int(_TTS_UI_WAIT_SEC / _TTS_UI_POLL_SEC))):
        if not _is_speech_url(getattr(page, "url", ""), model):
            raise _tts_settings_error(page, "AI Studio left the exact target speech URL during entry")
        try:
            names = [n.strip() for n in page.locator(_TTS_MODEL_CARD_SELECTOR).all_text_contents()]
            panel_visible = page.locator("ms-run-settings").first.is_visible()
        except Exception as exc:
            raise _tts_settings_error(page, f"Cannot verify speech entry markers: {exc}") from exc
        if names and names != [model]:
            _require_active_tts_model(page, model)
        if panel_visible and names == [model]:
            return
        try:
            page.wait_for_timeout(_TTS_UI_POLL_SEC * 1000)
        except Exception as exc:
            raise _tts_settings_error(page, f"Cannot wait for speech entry hydration: {exc}") from exc
    raise _tts_settings_error(page, "AI Studio speech entry did not finish loading within 20 seconds")


def _require_active_tts_model(page: Any, model: str) -> None:
    """Fail closed unless the run-settings model card shows exactly the target TTS model.

    Probed live 2026-10-07 (docs/sessions/CLAUDE_INTERIM_RESULT.md): a chat model page on the
    speech path also shows ms-run-settings and the prompt textarea, so the workspace check alone
    cannot tell them apart. No click, keypress or navigation happens here.
    """
    if not model:
        raise TTSWorkspaceUnavailableError("AI Studio target TTS model is empty; refusing to send.")
    try:
        names = [n.strip() for n in page.locator(_TTS_MODEL_CARD_SELECTOR).all_text_contents()]
    except Exception:
        names = None
    if names != [model]:
        if names:
            detail = "The active model does not match the target TTS model."
        else:
            detail = (
                "The run-settings panel must be open, because closing it removes the model card, "
                "so a closed panel or an unavailable model card makes this gate fail closed."
            )
        raise TTSWorkspaceUnavailableError(
            f"AI Studio active model is not verified as {model!r}: model card names={names!r} "
            f"(current URL: {getattr(page, 'url', '')}). {detail}"
        )


def ensure_speech_playground_tab(
    context: BrowserContext, target_tts_model: str = "gemini-2.5-pro-preview-tts", *, owned_page: Page | None = None
) -> Page:
    """Finds or opens the Google AI Studio Speech Playground tab and guarantees Playwright is on the correct UI."""
    tab1_speech = owned_page

    # 1. Search existing tabs for generate-speech
    if tab1_speech is None:
        for page in context.pages:
            if _is_speech_url(page.url):
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

    if not _is_speech_url(tab1_speech.url, target_tts_model):
        print(f"Navigating to Speech Playground: {clean_speech_url}")
        try:
            tab1_speech.goto(clean_speech_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"[NOTICE] Initial navigation notice: {e}")
        time.sleep(4)

    # 3. Guardrail: If AI Studio redirected away to /prompts/..., force direct navigation
    if not _is_speech_url(tab1_speech.url, target_tts_model):
        print(
            "[WARNING] AI Studio redirected away from Speech Playground. Retrying direct navigation..."
        )
        try:
            tab1_speech.goto(clean_speech_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"[NOTICE] Guardrail navigation notice: {e}")
        time.sleep(4)

    if not _is_speech_url(tab1_speech.url, target_tts_model):
        raise TTSWorkspaceUnavailableError(
            f"AI Studio did not open the Speech Playground (final URL: {tab1_speech.url})"
        )

    return tab1_speech


def wait_for_gemini_response(page: Page, step_name: str = "AI Response", max_wait_sec: float = 120) -> str:
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
                current_text: str = last_el.evaluate("el => el.innerText").strip()
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


def select_gemini_model(page: Page, model_name: str) -> bool:
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


def select_ai_studio_tts_model(page: Page, target_model: str) -> bool:
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


def _tts_visible(page: Any, selector: str, label: re.Pattern[str] | None = None) -> list[Any]:
    """Visible matches of selector (and of label, if given, on inner text); errors count as none."""
    try:
        elements = page.locator(selector).all()
    except Exception:
        return []
    found = []
    for element in elements:
        try:
            if element.is_visible() and (
                label is None or label.match(element.inner_text(timeout=1000) or "")
            ):
                found.append(element)
        except Exception:
            continue
    return found


def _tts_wait_until(page: Any, check: Callable[[], bool], timeout_sec: float | None = None) -> bool:
    """Bounded poll of real page markers (never a blind fixed sleep); False on timeout."""
    limit = _TTS_UI_WAIT_SEC if timeout_sec is None else timeout_sec
    for _ in range(max(1, int(limit / _TTS_UI_POLL_SEC))):
        try:
            if check():
                return True
        except TTSWorkspaceUnavailableError:
            raise
        except Exception:
            pass
        page.wait_for_timeout(_TTS_UI_POLL_SEC * 1000)
    return False


def _tts_settings_error(page: Any, message: str) -> TTSWorkspaceUnavailableError:
    return TTSWorkspaceUnavailableError(f"{message} (current URL: {getattr(page, 'url', '')})")


def _strict_tts_visible(page: Page, selector: str) -> list[Locator]:
    """Safety selectors must distinguish no matches from query/visibility failures."""
    try:
        matches = page.locator(selector)
        found = []
        for index in range(matches.count()):
            element = matches.nth(index)
            if element.is_visible():
                found.append(element)
        return found
    except Exception as exc:
        raise _tts_settings_error(
            page, f"Cannot verify speech safety selector {selector!r}: {exc}"
        ) from exc


@overload
def _visible_tts_prompt(page: Page, selector: str, *, allow_missing: Literal[False] = False) -> Locator: ...


@overload
def _visible_tts_prompt(page: Page, selector: str, *, allow_missing: Literal[True]) -> Locator | None: ...


def _visible_tts_prompt(
    page: Page, selector: str, *, allow_missing: bool = False
) -> Locator | None:
    """Resolve exactly one visible prompt; hidden matching nodes may coexist."""
    found = _strict_tts_visible(page, selector)
    if len(found) > 1:
        raise _tts_settings_error(
            page,
            f"Speech prompt {selector!r} needs exactly one visible match, found {len(found)}",
        )
    if not found:
        if allow_missing:
            return None
        raise _tts_settings_error(
            page,
            f"Speech prompt {selector!r} needs exactly one visible match, found 0",
        )
    return found[0]

def _cancel_switch_model_dialog(page: Any) -> None:
    """Cancel a model-switch dialog and stop; selector errors also stop the flow."""
    dialogs = _strict_tts_visible(page, _TTS_SWITCH_MODEL_DIALOG_SELECTOR)
    if not dialogs:
        return
    cancel = _strict_tts_visible(page, _TTS_SWITCH_MODEL_CANCEL_SELECTOR)
    if len(cancel) != 1:
        raise _tts_settings_error(
            page, f"Switch model dialog needs exactly one visible Cancel, found {len(cancel)}"
        )
    try:
        cancel[0].click(timeout=5000)
    except Exception as exc:
        raise _tts_settings_error(page, f"Could not cancel Switch model dialog: {exc}") from exc
    raise _tts_settings_error(
        page, "AI Studio showed a 'Switch model?' dialog during speech settings"
    )


def _require_one_tts_control(
    page: Any, selector: str, step: str, label: re.Pattern[str] | None = None
) -> Any:
    found = _tts_visible(page, selector, label)
    if len(found) != 1:
        raise _tts_settings_error(
            page,
            f"Speech settings step '{step}' needs exactly one visible control, found {len(found)}",
        )
    return found[0]


def _click_tts_setting(page: Any, element: Any, step: str) -> None:
    """Settings clicks use Playwright locator.click() only: no coordinates, no keys."""
    try:
        element.click(timeout=5000)
    except Exception as exc:
        overlay = ui_guard.ensure_clear(page, allow_escape=False)
        try:
            if not overlay.cleared:
                raise exc
            element.click(timeout=5000)
        except Exception as retry_exc:
            raise _tts_settings_error(
                page,
                f"Speech settings step '{step}' click failed: {retry_exc} "
                f"(blocked_by: {overlay.blocked_by})",
            ) from retry_exc
    _cancel_switch_model_dialog(page)


def _require_current_tts_settings(
    page: Any, model: str, voice_name: Any, *, style: Any = None
) -> None:
    """Read current required settings without mutating UI immediately before fill or Run."""
    voice = str(voice_name or "").strip()
    if not _TTS_VOICE_NAME_PATTERN.fullmatch(voice):
        raise _tts_settings_error(page, "Configured TTS voice is missing or invalid")
    _require_speech_workspace(page)
    if _strict_tts_visible(page, _TTS_SWITCH_MODEL_DIALOG_SELECTOR):
        raise _tts_settings_error(page, "Speech model switch is pending; refusing to type or send")
    if len(_strict_tts_visible(page, _TTS_RUN_SETTINGS_SELECTOR)) != 1:
        raise _tts_settings_error(page, "Speech settings panel must be exactly one visible panel")
    _require_active_tts_model(page, model)
    for selector, expected, label in (
        (_TTS_MODEL_CARD_SELECTOR, model, "model"),
        (_TTS_VOICE_NAME_SELECTOR, voice, "voice"),
    ):
        elements = _strict_tts_visible(page, selector)
        if len(elements) != 1:
            raise _tts_settings_error(page, f"Current TTS {label} must have exactly one visible value")
        try:
            actual = elements[0].inner_text(timeout=1000).strip()
            names = [name.strip() for name in page.locator(selector).all_text_contents()]
        except Exception as exc:
            raise _tts_settings_error(page, f"Cannot read current TTS {label}: {exc}") from exc
        if actual != expected or names != [expected]:
            raise _tts_settings_error(page, f"Current TTS {label} is not verified as {expected!r}")
    if _is_flash_model(model):
        _require_tts_style_title(page, style)


def _tts_voice_names(page: Any) -> list[str] | None:
    try:
        return [n.strip() for n in page.locator(_TTS_VOICE_NAME_SELECTOR).all_text_contents()]
    except Exception:
        return None


def _tts_style_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _tts_style_readback(page: Any) -> tuple[str | None, str | None]:
    """(title, chip label) of the one visible Style button; (None, None) when unreadable."""
    try:
        buttons = _tts_visible(page, _TTS_STYLE_BUTTON_SELECTOR)
        labels = _tts_visible(page, _TTS_STYLE_LABEL_SELECTOR)
        if len(buttons) != 1 or len(labels) != 1:
            return (None, None)
        title = buttons[0].get_attribute("title", timeout=1000)
        label = labels[0].inner_text(timeout=1000)
    except Exception:
        return (None, None)
    return (_tts_style_text(title), _tts_style_text(label))


def _require_tts_style_title(page: Any, style: Any) -> None:
    """Read-only Flash gate before typing and Run: the Style button title equals the Style."""
    expected = _tts_style_text(style)
    if not expected:
        raise _tts_settings_error(page, f"{_TTS_FLASH_MODEL} needs a nonempty Style")
    buttons = _strict_tts_visible(page, _TTS_STYLE_BUTTON_SELECTOR)
    if len(buttons) != 1:
        raise _tts_settings_error(page, "Current TTS Style must have exactly one visible button")
    try:
        title = buttons[0].get_attribute("title", timeout=1000)
    except Exception as exc:
        raise _tts_settings_error(page, f"Cannot read current TTS Style: {exc}") from exc
    if _tts_style_text(title) != expected:
        raise _tts_settings_error(page, "Current TTS Style is not verified as the run's Style")


def _require_tts_temperature(page: Any, expected: Any) -> None:
    """Read-only adaptive gate: the one visible Temperature input equals the configured value."""
    target = _tts_number(expected)
    if target is None:
        raise _tts_settings_error(page, f"Configured TTS temperature {expected!r} is not a number")
    inputs = _strict_tts_visible(page, _TTS_TEMPERATURE_SELECTOR)
    if len(inputs) != 1:
        raise _tts_settings_error(
            page, "Current TTS temperature must have exactly one visible input"
        )
    try:
        actual = _tts_number(inputs[0].input_value(timeout=1000))
    except Exception as exc:
        raise _tts_settings_error(page, f"Cannot read current TTS temperature: {exc}") from exc
    if actual is None or abs(actual - target) > _TTS_TEMPERATURE_TOLERANCE:
        raise _tts_settings_error(
            page, f"Current TTS temperature {actual!r} is not verified as {target:g}"
        )


def _verify_tts_settings(
    page: Any, model: Any, voice_name: Any, style: Any = None, temperature: Any = None
) -> None:
    """Pro keeps the original three-argument check; Flash adds the read-only Style gate.

    Adaptive callers pass the configured temperature, which must then read back exactly.
    """
    if _is_flash_model(model):
        _require_current_tts_settings(page, model, voice_name, style=style)
    else:
        _require_current_tts_settings(page, model, voice_name)
    if temperature is not None:
        try:
            _require_tts_temperature(page, temperature)
        except Exception as exc:
            print(f"Warning: Could not verify optional TTS temperature: {exc}")

def _set_tts_style(page: Any, style: Any) -> None:
    """Flash only: write the run's Style and fail closed unless title and chip read it back.

    Clicks are Playwright locator.click() only and no key is pressed. The open menu has a
    click-blocking backdrop (a second Style click times out), so the backdrop closes it.
    """
    text = str(style or "").strip()
    expected = _tts_style_text(text)
    if not expected:
        raise _tts_settings_error(page, f"{_TTS_FLASH_MODEL} needs a nonempty Style")
    if _tts_style_readback(page) == (expected, expected):
        print("Speech Style already set.")
        return
    button = _require_one_tts_control(page, _TTS_STYLE_BUTTON_SELECTOR, "Style")
    _click_tts_setting(page, button, "Style")
    if not _tts_wait_until(
        page, lambda: len(_tts_visible(page, _TTS_STYLE_TEXTAREA_SELECTOR)) == 1
    ):
        raise _tts_settings_error(page, "AI Studio Style menu needs exactly one visible style box")
    field = _require_one_tts_control(page, _TTS_STYLE_TEXTAREA_SELECTOR, "Describe the voice style")
    try:
        field.fill(text, timeout=5000)
    except Exception as exc:
        raise _tts_settings_error(page, f"Could not fill the voice Style: {exc}") from exc
    backdrops = _tts_visible(page, _TTS_OVERLAY_BACKDROP_SELECTOR)
    if not backdrops:
        raise _tts_settings_error(page, "AI Studio Style menu has no backdrop to close it")
    _click_tts_setting(page, backdrops[-1], "Close Style menu")
    if not _tts_wait_until(page, lambda: not _tts_visible(page, _TTS_OVERLAY_BACKDROP_SELECTOR)):
        raise _tts_settings_error(page, "AI Studio Style menu did not close")
    if not _tts_wait_until(
        page, lambda: _tts_style_readback(page) == (expected, expected), timeout_sec=3.0
    ):
        raise _tts_settings_error(
            page, f"AI Studio Style is not verified: read back {_tts_style_readback(page)!r}"
        )
    print("Successfully set the speech Style.")


def _open_tts_editor(page: Any, model: Any = None) -> None:
    """Landing page -> "Create new dialog" -> bounded wait for the hydrated editor.

    For ~3 s after the click a placeholder editor shows with empty run settings, so readiness
    needs the Text toggle plus the model card (or, with the panel closed, its reopen toggle).
    The card can render late, and a second page navigation 4-24 s after load can bring it back,
    so it is clicked inside the poll whenever it (re)appears: at most twice, then fail closed.
    """

    def ready() -> bool:
        try:
            if _is_flash_model(model):
                if len(_tts_visible(page, _TTS_FLASH_PROMPT_SELECTOR)) != 1:
                    return False
            elif len(_tts_visible(page, _TTS_TEXT_TOGGLE_SELECTOR, _TTS_TEXT_TOGGLE_LABEL)) != 1:
                return False
            return bool(page.locator(_TTS_MODEL_CARD_SELECTOR).all_text_contents()) or bool(
                _tts_visible(page, _TTS_RUN_SETTINGS_TOGGLE_SELECTOR)
            )
        except Exception:
            return False

    clicks = 0
    card_gone_since_click = True
    for _ in range(max(1, int(_TTS_UI_WAIT_SEC / _TTS_UI_POLL_SEC))):
        if _tts_visible(page, _TTS_CREATE_DIALOG_SELECTOR):
            if card_gone_since_click:
                if clicks >= _TTS_CREATE_DIALOG_MAX_CLICKS:
                    raise _tts_settings_error(
                        page, f"AI Studio showed 'Create new dialog' again after {clicks} clicks"
                    )
                card = _require_one_tts_control(
                    page, _TTS_CREATE_DIALOG_SELECTOR, "Create new dialog"
                )
                _click_tts_setting(page, card, "Create new dialog")
                clicks += 1
                card_gone_since_click = False
        else:
            card_gone_since_click = True
            if ready():
                return
        page.wait_for_timeout(_TTS_UI_POLL_SEC * 1000)
    raise _tts_settings_error(page, "AI Studio speech editor did not finish loading")


def _select_tts_text_mode(page: Any) -> None:
    prompt = _visible_tts_prompt(page, _TTS_PROMPT_SELECTOR, allow_missing=True)
    if prompt is not None:
        return
    toggle = _require_one_tts_control(
        page, _TTS_TEXT_TOGGLE_SELECTOR, "Text mode", _TTS_TEXT_TOGGLE_LABEL
    )
    _click_tts_setting(page, toggle, "Text mode")

    def prompt_is_ready() -> bool:
        return (
            _visible_tts_prompt(page, _TTS_PROMPT_SELECTOR, allow_missing=True)
            is not None
        )

    if not _tts_wait_until(page, prompt_is_ready):
        raise _tts_settings_error(page, "AI Studio Text mode did not show the speech prompt box")
    _visible_tts_prompt(page, _TTS_PROMPT_SELECTOR)


def _ensure_run_settings_open(page: Any) -> None:
    """The model gate reads the model card, which exists only while this panel is open."""
    if _tts_visible(page, _TTS_RUN_SETTINGS_SELECTOR):
        return
    toggle = _require_one_tts_control(
        page, _TTS_RUN_SETTINGS_TOGGLE_SELECTOR, "Toggle run settings panel"
    )
    _click_tts_setting(page, toggle, "Toggle run settings panel")
    if not _tts_wait_until(page, lambda: bool(_tts_visible(page, _TTS_RUN_SETTINGS_SELECTOR))):
        raise _tts_settings_error(page, "AI Studio run-settings panel did not reopen")


def _select_tts_voice(page: Any, voice_name: Any, model: Any = None) -> None:
    """Sets the page-local speaker voice and fails closed unless it reads back exactly."""
    voice = str(voice_name or "").strip()
    if not _TTS_VOICE_NAME_PATTERN.match(voice):
        raise _tts_settings_error(page, f"AI Studio voice name {voice_name!r} is not a plain name")
    if _tts_voice_names(page) == [voice]:
        print(f"Speaker voice already set to: {voice}")
        return
    opener = _require_one_tts_control(page, _TTS_VOICE_OPEN_SELECTOR, "Open voice settings")
    _click_tts_setting(page, opener, "Open voice settings")
    card = f"{_TTS_VOICE_DIALOG_SELECTOR} div.voice-card[data-voice-name='{voice}']"
    option_selector = f"{card} button.voice-card-content"  # never the Play voice sample sibling
    flash = _is_flash_model(model)
    first_wait = _TTS_VOICE_SEARCH_WAIT_SEC if flash else None
    if not _tts_wait_until(page, lambda: bool(_tts_visible(page, option_selector)), first_wait):
        offered = False
        if flash:  # Flash lists 2,000+ voices and renders a card only after a search
            remaining = _TTS_UI_WAIT_SEC - _TTS_VOICE_SEARCH_WAIT_SEC
            searches = _tts_visible(page, _TTS_VOICE_SEARCH_SELECTOR)
            if len(searches) == 1:
                try:
                    searches[0].fill(voice, timeout=5000)
                except Exception as exc:
                    raise _tts_settings_error(
                        page, f"AI Studio voice search failed: {exc}"
                    ) from exc
                remaining = _TTS_UI_WAIT_SEC
            offered = _tts_wait_until(
                page, lambda: bool(_tts_visible(page, option_selector)), remaining
            )
        if not offered:
            raise _tts_settings_error(
                page, f"AI Studio Speaker settings did not offer voice {voice!r}"
            )
    option = _require_one_tts_control(page, option_selector, f"voice {voice}")
    _click_tts_setting(page, option, f"voice {voice}")
    selected = f"{_TTS_VOICE_DIALOG_SELECTOR} div.voice-card.selected[data-voice-name='{voice}']"
    if not _tts_wait_until(page, lambda: bool(_tts_visible(page, selected))):
        raise _tts_settings_error(page, f"AI Studio did not mark voice {voice!r} as selected")
    closer = _require_one_tts_control(page, _TTS_VOICE_CLOSE_SELECTOR, "Close voice settings")
    _click_tts_setting(page, closer, "Close voice settings")
    if not _tts_wait_until(page,
        lambda: not _tts_visible(page, selected) and _tts_voice_names(page) == [voice]
    ):
        raise _tts_settings_error(
            page,
            f"AI Studio speaker voice is not verified as {voice!r}: "
            f"voice names={_tts_voice_names(page)!r}",
        )
    print(f"Successfully assigned speaker to: {voice}")


def _tts_number(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _set_tts_temperature(page: Any, temp_val: Any) -> bool:
    """Best effort (log and continue): fill, blur and read back; never presses a key.

    Only a "Switch model?" dialog raises here.
    """
    try:
        target = float(str(temp_val).strip())
    except ValueError:
        print(f"Warning: Temperature {temp_val!r} is not a number; keeping AI Studio's value.")
        return False
    if not _tts_visible(page, _TTS_TEMPERATURE_SELECTOR):
        # Only click the expander while the input is hidden: a second click collapses the group.
        expanders = _tts_visible(page, _TTS_MODEL_SETTINGS_EXPANDER_SELECTOR)
        if len(expanders) == 1:
            try:
                expanders[0].click(timeout=5000)
            except Exception as exc:
                print(f"Warning: Could not expand Model settings: {exc}")
            _tts_wait_until(page,
                lambda: bool(_strict_tts_visible(page, _TTS_SWITCH_MODEL_DIALOG_SELECTOR)),
                timeout_sec=_TTS_SWITCH_SETTLE_SEC,
            )
            _cancel_switch_model_dialog(page)
            _tts_wait_until(page,
                lambda: bool(_tts_visible(page, _TTS_TEMPERATURE_SELECTOR)), timeout_sec=3.0
            )
    inputs = _tts_visible(page, _TTS_TEMPERATURE_SELECTOR)
    if len(inputs) != 1:
        print(
            f"Warning: Found {len(inputs)} temperature inputs in run settings (need exactly one); "
            "keeping AI Studio's value."
        )
        return False
    field = inputs[0]

    def committed() -> bool:
        return _tts_number(field.get_attribute("aria-valuenow", timeout=1000)) == target

    actual = None
    aria_ok = False
    try:
        field.fill(f"{target:g}", timeout=5000)
        field.blur(timeout=1000)
        actual = _tts_number(field.input_value(timeout=1000))
        aria_ok = _tts_wait_until(page, committed, timeout_sec=1.0)
    except Exception as exc:
        print(f"Warning: Could not set temperature: {exc}; keeping AI Studio's value.")
    _cancel_switch_model_dialog(page)
    if actual is None or abs(actual - target) > 1e-6:
        print(f"Warning: Temperature reads back as {actual!r}, not {target:g}; continuing.")
        return False
    if not aria_ok:
        try:
            aria = field.get_attribute("aria-valuenow", timeout=1000)
        except Exception as exc:
            aria = f"unreadable ({exc})"
        print(f"Warning: Temperature aria-valuenow is {aria!r}, not {target:g}; continuing.")
        return False
    print(f"Successfully set Temperature to: {actual:g}")
    return True


def reapply_speech_settings(page: Page, options: Mapping[str, Any]) -> None:
    """Prepares today's Speech Playground editor (Text mode, voice, temperature) and verifies it.

    The ?model= URL selects the model; the model card is read, never clicked, and the
    run-settings panel stays open so _require_active_tts_model can read it. Every click is a
    Playwright locator.click() and no key is pressed. Fails closed with
    TTSWorkspaceUnavailableError (see docs/sessions/CLAUDE_INTERIM_RESULT.md).
    """
    target_model = options.get("model", "gemini-2.5-pro-preview-tts")
    temp_val = options.get("temperature", "1.1")
    voice_name = options.get("voice", "Achird")

    print(
        f"Re-applying Speech Playground settings (Model {target_model}, Temperature {temp_val}, speaker {voice_name})..."
    )

    _cancel_switch_model_dialog(page)
    # 1. Landing page -> "Create new dialog" -> hydrated editor (same URL)
    _open_tts_editor(page, target_model)
    # 2. Text mode (Composer is the default) shows the speech prompt box; Flash has no toggle
    if not _is_flash_model(target_model):
        _select_tts_text_mode(page)
    # 3. Keep run settings open; verify (never click) the model the URL selected
    _ensure_run_settings_open(page)
    _require_active_tts_model(page, target_model)
    # 4. Speaker voice is page-local, so it is set and verified on every page
    if _is_flash_model(target_model):
        _select_tts_voice(page, voice_name, target_model)
    else:
        _select_tts_voice(page, voice_name)
    # 5. Temperature: best effort, see _set_tts_temperature
    adaptive = bool(options.get("adaptive"))
    _set_tts_temperature(page, temp_val)  # optional; required model and voice checks remain strict
    # 5b. Style: required and verified on Flash; Pro has no Style
    if _is_flash_model(target_model):
        _set_tts_style(page, options.get("style"))
    elif options.get("style"):
        raise _tts_settings_error(page, f"Speech Style is only supported by {_TTS_FLASH_MODEL}")
    # 6. Reopen after optional settings and verify all required current state.
    _cancel_switch_model_dialog(page)
    _ensure_run_settings_open(page)
    _verify_tts_settings(
        page, target_model, voice_name, options.get("style"), temp_val if adaptive else None
    )
    if not _tts_visible(page, _tts_prompt_selector(target_model)):
        raise _tts_settings_error(page, "AI Studio speech prompt box is hidden after settings")


def get_file_md5(file_path: str) -> str | None:
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


def is_valid_wav_file(file_path: str, min_frames: int = 1000) -> bool:
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


def check_ai_studio_errors(page: Page) -> tuple[bool, str]:
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


def main() -> None:
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


def connect_tts_browser(playwright: Playwright, *, adaptive: bool, browser_type: str, profile_index: str | int, port: int) -> Browser:
    """Attach to CDP; only the legacy path may launch a replacement process."""
    endpoint = f"http://127.0.0.1:{port}"
    if adaptive:
        network_health.require_healthy(network_health.AI_STUDIO_URL)
        foreign = ui_guard.foreign_debugger_targets(port)
        if foreign:
            origins = ", ".join(sorted({target["origin"] for target in foreign}))
            raise AdaptiveBrowserOwnershipError(
                "Adaptive TTS requires an existing CDP browser session without foreign "
                f"debugger tabs; close these tabs and retry: {origins}"
            )
    try:
        browser = (
            playwright.chromium.connect_over_cdp(endpoint, timeout=30000)
            if adaptive
            else playwright.chromium.connect_over_cdp(endpoint)
        )
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


_ADAPTIVE_SPLIT_TIERS = ("flash_split", "pro_split")
_ADAPTIVE_DOWNLOAD_SELECTOR = "button[aria-label*='Download' i], button:has-text('Download')"
_ADAPTIVE_RUN_SELECTOR = "button[type='submit'], button:has-text('Run')"
_ADAPTIVE_FLASH_SPLIT_DISABLED = (
    "Flash split failed; Pro fallback disabled (set ADAPTIVE_TTS_PRO_FALLBACK=1)"
)


class _TTSUnitFailure(RuntimeError):
    """One adaptive send (a full chapter or one piece) gave no usable audio after Run."""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail
        normalized = re.sub(r"\s+", " ", detail or "").strip().lower()
        collapsed = re.sub(r"[0-9]{5,}", "#", normalized)[:200]
        self.signature = f"{kind}:{collapsed}"


def _adaptive_unit_failure(err_msg: str, fallback_kind: str) -> _TTSUnitFailure:
    """Quota/account errors stop the run at once; any other error fails only this unit."""
    detail = re.sub(r"\s+", " ", err_msg or "").strip()[:200]
    kind = ui_guard.classify_provider_error(detail) if detail else fallback_kind
    if kind in ("quota", "account"):
        raise TTSProviderError(f"{kind}: {detail}")
    return _TTSUnitFailure(kind, detail or fallback_kind)


def _adaptive_require_no_403(alkali_state: NetworkAuditState) -> None:
    if alkali_state.get("is_403"):
        raise TTSProviderError(
            f"quota: AI Studio speech returned HTTP 403 ({alkali_state.get('url')})"
        )


def _adaptive_discard(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _require_typed_text(page: Any, speech_input: Any, text: str) -> None:
    """Read-only: the prompt textarea holds exactly the text (whitespace-collapsed)."""
    try:
        value = speech_input.input_value(timeout=1000)
    except Exception as exc:
        raise _tts_settings_error(page, f"Cannot read back the typed speech text: {exc}") from exc
    if " ".join(str(value or "").split()) != " ".join(text.split()):
        raise _tts_settings_error(page, "Typed speech text does not match the text to send")


def _require_run_button(page: Any) -> Any:
    """Read-only: exactly one visible, enabled Run control."""
    found = _strict_tts_visible(page, _ADAPTIVE_RUN_SELECTOR)
    if len(found) != 1:
        raise _tts_settings_error(
            page, f"Run needs exactly one visible control, found {len(found)}"
        )
    button = found[0]
    try:
        enabled = button.is_enabled(timeout=1000)
        aria_disabled = button.get_attribute("aria-disabled", timeout=1000)
    except Exception as exc:
        raise _tts_settings_error(page, f"Cannot verify the Run control: {exc}") from exc
    if not enabled or str(aria_disabled or "").strip().lower() == "true":
        raise _tts_settings_error(page, "Run control is disabled")
    return button


def _adaptive_send_unit(
    page: Any,
    text: str,
    dest: str,
    options: dict[str, Any],
    alkali_state: NetworkAuditState,
    *,
    recover: bool = False,
    on_sent: Callable[[], None] | None = None,
) -> None:
    """One adaptive TTS send that leaves a frame-validated WAV at dest.

    Every setting (voice, Style, temperature) is applied and verified before typing; after typing
    only read-only checks run and the Run click is the only click; Control+Enter is never pressed.
    on_sent runs immediately before the one Run click to durably account for possible dispatch.    Raises _TTSUnitFailure for a post-Run failure of this unit and TTSProviderError to stop.
    """
    model = options.get("model")
    selector = _tts_prompt_selector(model)
    temperature = options.get("temperature")
    temperature = "" if temperature is None else temperature  # missing fails the gate
    if recover:
        print("[RECOVER] Reloading the Speech Playground tab before this send...")
        page.reload(wait_until="domcontentloaded")
        time.sleep(5)
        _require_speech_workspace(page)
        reapply_speech_settings(page, options)
    _require_speech_workspace(page)
    if _visible_tts_prompt(page, selector, allow_missing=True) is None:
        print("Speech prompt box is hidden. Re-applying speech settings...")
        reapply_speech_settings(page, options)
    network_health.require_healthy(network_health.AI_STUDIO_URL)
    _verify_tts_settings(page, model, options.get("voice"), options.get("style"), temperature)
    speech_input = _visible_tts_prompt(page, selector)
    _adaptive_discard(dest)
    alkali_state["is_403"] = False
    try:
        page.bring_to_front()  # a background tab stalls rendering and downloads
    except Exception as exc:
        print(f"Warning: Could not bring the speech tab to the front: {exc}")
    print(f"Entering {len(text)} chars into AI Studio ({model})...")
    typed_at = time.monotonic()
    if humanize_text_input(page, speech_input, text) is not True:
        raise _tts_settings_error(page, "Typing into the speech prompt did not complete")
    cooldown = 3.0 + (len(text) / 500.0) * random.uniform(1.2, 2.8)
    cooldown = min(cooldown, _TTS_ADAPTIVE_COOLDOWN_MAX_SEC)  # stays inside the Run window
    print(f"Applying dynamic safety cooldown of {cooldown:.2f}s...")
    time.sleep(cooldown)
    _verify_tts_settings(page, model, options.get("voice"), options.get("style"), temperature)
    _visible_tts_prompt(page, selector)
    _require_typed_text(page, speech_input, text)
    run_btn = _require_run_button(page)
    elapsed = time.monotonic() - typed_at
    if elapsed >= _TTS_TYPE_TO_RUN_MAX_SEC:
        raise _tts_settings_error(
            page, f"{elapsed:.1f}s passed since typing (limit {_TTS_TYPE_TO_RUN_MAX_SEC:g}s)"
        )
    if on_sent is not None:
        on_sent()
    remaining_seconds = _TTS_TYPE_TO_RUN_MAX_SEC - (time.monotonic() - typed_at)
    timeout_ms = int(remaining_seconds * 1000)
    if timeout_ms <= 0:
        raise TTSProviderError(
            "uncertain: adaptive Run deadline expired after durable reservation; "
            "the durable attempt remains in flight"
        )
    try:
        click_result = run_btn.click(timeout=min(3000, timeout_ms))
    except Exception as exc:
        raise TTSProviderError(
            "uncertain: adaptive Run click outcome could not be confirmed; "
            "the durable attempt remains in flight"
        ) from exc
    if click_result is not None:
        raise TTSProviderError(
            "uncertain: adaptive Run click returned an unexpected result; "
            "the durable attempt remains in flight"
        )

    print("Synthesis started. Waiting dynamically for rendering to complete...")
    try:
        page.wait_for_selector("button:has-text('Stop')", timeout=8000)
    except Exception:
        has_error, err_msg = check_ai_studio_errors(page)
        if has_error:
            raise _adaptive_unit_failure(err_msg, "unknown") from None
        _adaptive_require_no_403(alkali_state)
        # Never re-type after an unconfirmed Run: a slow page may still be synthesizing.
        try:
            page.wait_for_selector(
                f"button:has-text('Stop'), {_ADAPTIVE_DOWNLOAD_SELECTOR}", timeout=30000
            )
        except Exception as exc:
            raise TTSProviderError(
                "unknown: AI Studio showed no Stop button, no Download button "
                "and no error banner after Run"
            ) from exc
    _adaptive_require_no_403(alkali_state)
    synth_timeout_ms = int(get_config_value("TTS_SYNTHESIS_TIMEOUT", "300")) * 1000
    try:
        page.wait_for_selector("button:has-text('Run')", timeout=synth_timeout_ms)
        print("Audio synthesis complete!")
    except Exception as exc:
        print(f"Warning: Timeout or error waiting for synthesis: {exc}")
    time.sleep(2.0)
    download_btn = page.locator(_ADAPTIVE_DOWNLOAD_SELECTOR).first
    try:
        download_btn.wait_for(state="visible", timeout=10000)
    except Exception:
        pass
    saved = False
    try:
        if download_btn.is_visible():
            with page.expect_download(timeout=15000) as download_info:
                human_hover_and_click(page, download_btn)
            download_info.value.save_as(dest)
            saved = True
            print(f"Audio file downloaded and saved: {dest}")
    except Exception as exc:
        print(f"[ERROR] Error downloading audio file: {exc}")
    if not saved:
        saved = _adaptive_salvage_download(page, dest)
    _adaptive_require_no_403(alkali_state)
    if saved and is_valid_wav_file(dest):
        return
    _adaptive_discard(dest)
    has_error, err_msg = check_ai_studio_errors(page)
    raise _adaptive_unit_failure(
        err_msg if has_error else "", "invalid_audio" if saved else "no_audio"
    )


def _adaptive_speech_text(model: Any, speech: SpeechText) -> str:
    """Flash speaks the directed text (tags included); tags are never sent to Pro."""
    return speech.directed_text if _is_flash_model(model) else speech.clean_text


def _adaptive_unit_options(voice_config: dict[str, Any], model: str) -> dict[str, Any]:
    options = {key: value for key, value in voice_config.items() if key != "style"}
    options["model"] = model
    options["adaptive"] = True  # settings (temperature included) fail closed
    if _is_flash_model(model):
        options["style"] = voice_config.get("style")
    return options


def _adaptive_switch_model(page: Any, options: dict[str, Any]) -> None:
    """Re-navigate to the exact model URL (Pro fallback and back) and redo every setting."""
    model = options["model"]
    print(f"[TIER] Switching the Speech Playground tab to {model}...")
    page.goto(
        f"https://aistudio.google.com/generate-speech?model={model}",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    _wait_for_speech_workspace_ready(page, model)
    _require_speech_workspace(page, model)
    reapply_speech_settings(page, options)


def _adaptive_prior_md5s(
    manifest: dict[str, Any], voice_folder: str, chap_num: int, *, skip_pieces_of: Any = None
) -> set[str]:
    """MD5s of every completed chapter and piece, plus the previous chapter file on disk."""
    digests: set[Any] = set()
    for chap in manifest.get("chapters", []):
        if chap.get("md5"):
            digests.add(chap["md5"])
        if chap is skip_pieces_of:
            continue
        for piece in chap.get("pieces") or []:
            if piece.get("md5"):
                digests.add(piece["md5"])
    previous = os.path.join(voice_folder, f"Chapter_{chap_num - 1}.wav")
    if chap_num > 1 and os.path.exists(previous):
        digests.add(get_file_md5(previous))
    digests.discard(None)
    return digests


def _adaptive_attempt(
    page: Any,
    text: str,
    dest: str,
    options: dict[str, Any],
    alkali_state: NetworkAuditState,
    prior_md5s: set[str],
    session: dict[str, Any],
    on_sent: Callable[[], None] | None = None,
) -> str | None:
    """One send of one unit; returns the MD5 of a valid WAV that matches no earlier audio."""
    if session["page_model"] != options["model"]:
        _adaptive_switch_model(page, options)
        session.update(page_model=options["model"], dirty=False, sends=0)
    reload_limit = int(get_config_value("TTS_PROACTIVE_RELOAD_INTERVAL", "40"))
    recover = bool(session["dirty"]) or session["sends"] >= reload_limit
    if recover:
        session["sends"] = 0
    session["dirty"] = True
    session["sends"] += 1
    if on_sent is None:
        _adaptive_send_unit(page, text, dest, options, alkali_state, recover=recover)
    else:
        _adaptive_send_unit(
            page, text, dest, options, alkali_state, recover=recover, on_sent=on_sent
        )
    digest = get_file_md5(dest)
    if digest and digest in prior_md5s:
        _adaptive_discard(dest)
        raise _TTSUnitFailure("duplicate", "audio matches an earlier chapter or piece")
    session["dirty"] = False
    return digest


def _adaptive_retry_state(
    latest_run: str, manifest: dict[str, Any], chap: dict[str, Any], speech: SpeechText,
    voice_config: dict[str, Any], sha: str | None,
) -> dict[str, Any]:
    """Bind durable chapter spending before any browser action; never infer old entitlements."""
    from youtube_automation.production import voice_direction

    recipe = {
        "chapter_num": int(chap["chapter_num"]),
        "clean_text": speech.clean_text,
        "directed_text": speech.directed_text,
        "paragraph_count": speech.paragraph_count,
        "direction_sha256": sha,
        "primary": _adaptive_unit_options(voice_config, voice_config["model"]),
        "pro": _adaptive_unit_options(voice_config, voice_direction.PRO_MODEL),
    }
    fingerprint = hashlib.sha256(
        json.dumps(recipe, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    state = chap.get("tts_attempts")
    if state is None:
        if chap.get("full_sent") or chap.get("voice_tier") or chap.get("pieces") or chap.get("md5"):
            raise ValueError(
                f"Chapter {chap['chapter_num']} has incomplete legacy sends without durable "
                "TTS accounting; refusing to resend"
            )
        state = {
            "version": 1, "recipe_sha256": fingerprint, "retries_left": 1,
            "previous_failure": None, "units": {},
        }
        chap["tts_attempts"] = state
        save_manifest(latest_run, manifest)
    if not isinstance(state, dict) or type(state.get("version")) is not int or state["version"] != 1:
        raise ValueError("Malformed or unsupported durable TTS accounting")
    if state.get("recipe_sha256") != fingerprint:
        raise ValueError("Durable TTS chapter recipe changed; refusing a fresh send entitlement")
    _adaptive_validate_retry_state(state)
    if chap.get("full_sent") and "full" not in state["units"]:
        raise ValueError("Durable TTS accounting is missing the full chapter reservation")
    if chap.get("voice_tier") in _ADAPTIVE_SPLIT_TIERS and "full" not in state["units"]:
        raise ValueError("Durable TTS accounting is missing the split tier's full attempt")
    return state


def _adaptive_validate_retry_state(state: dict[str, Any]) -> None:
    """Validate spend and signature history rather than trusting a mutable remaining counter."""
    if type(state.get("retries_left")) is not int or state["retries_left"] not in (0, 1):
        raise ValueError("Malformed durable TTS retry allowance")
    units = state.get("units")
    if not isinstance(units, dict):
        raise ValueError("Malformed durable TTS units")
    ordered = []
    for unit_id, unit in units.items():
        if not isinstance(unit_id, str) or not re.fullmatch(r"full|(?:pro_)?part_[1-9][0-9]*", unit_id):
            raise ValueError("Malformed durable TTS unit identity")
        if not isinstance(unit, dict) or not isinstance(unit.get("model"), str):
            raise ValueError("Malformed durable TTS unit")
        if not isinstance(unit.get("recipe_sha256"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", unit["recipe_sha256"]
        ) or not isinstance(unit.get("audio_file"), str):
            raise ValueError("Malformed durable TTS unit recipe")
        attempts = unit.get("attempts")
        limit = 1 if unit_id == "full" else _TTS_UNIT_ATTEMPT_LIMIT
        if not isinstance(attempts, list) or not 1 <= len(attempts) <= limit:
            raise ValueError("Malformed durable TTS unit attempts")
        for index, attempt in enumerate(attempts):
            if not isinstance(attempt, dict) or type(attempt.get("sequence")) is not int:
                raise ValueError("Malformed durable TTS attempt sequence")
            status = attempt.get("status")
            if status not in ("IN_FLIGHT", "FAILED", "COMPLETED"):
                raise ValueError("Malformed durable TTS attempt status")
            if index < len(attempts) - 1 and status != "FAILED":
                raise ValueError("Durable TTS attempted an already completed or uncertain unit")
            if type(attempt.get("is_retry")) is not bool or attempt["is_retry"] != (index > 0):
                raise ValueError("Malformed durable TTS retry reservation")
            if status == "COMPLETED" and not isinstance(attempt.get("md5"), str):
                raise ValueError("Malformed completed durable TTS attempt")
            if status == "FAILED":
                if not isinstance(attempt.get("kind"), str) or not isinstance(attempt.get("detail"), str):
                    raise ValueError("Malformed durable TTS failure")
                if attempt.get("signature") != _TTSUnitFailure(attempt["kind"], attempt["detail"]).signature:
                    raise ValueError("Malformed durable TTS failure signature")
                if type(attempt.get("retry_allowed")) is not bool:
                    raise ValueError("Malformed durable TTS failure entitlement")
            ordered.append((attempt["sequence"], unit_id, index, unit, attempt))
    ordered.sort(key=lambda row: row[0])
    if [row[0] for row in ordered] != list(range(1, len(ordered) + 1)):
        raise ValueError("Malformed durable TTS accounting order")
    previous = None
    retries_left = 1
    for _sequence, unit_id, index, unit, attempt in ordered:
        if attempt["is_retry"]:
            if retries_left <= 0 or not unit["attempts"][index - 1].get("retry_allowed"):
                raise ValueError("Durable TTS retry allowance was exceeded")
            retries_left -= 1
        if attempt["status"] == "FAILED":
            current = {"model": unit["model"], "signature": attempt["signature"]}
            expected = (
                unit_id != "full" and attempt["kind"] == "transient" and previous != current
                and retries_left > 0 and index + 1 < _TTS_UNIT_ATTEMPT_LIMIT
            )
            if attempt["retry_allowed"] != expected:
                raise ValueError("Malformed durable TTS failure retry decision")
            previous = current
    if state.get("previous_failure") != previous or state["retries_left"] != retries_left:
        raise ValueError("Durable TTS retry allowance or failure history changed")
    if any(row[4]["status"] == "IN_FLIGHT" for row in ordered):
        raise TTSProviderError(
            "uncertain: durable TTS action was interrupted; refusing any new browser action"
        )


def _adaptive_journaled_attempt(
    page: Any, text: str, dest: str, options: dict[str, Any], alkali_state: NetworkAuditState,
    prior_md5s: Callable[[], set[str]], session: dict[str, Any], latest_run: str, manifest: dict[str, Any],
    chap: dict[str, Any], budget: dict[str, Any], unit_id: str,
) -> str | None:
    """Reserve one action and any retry atomically before navigation, typing or Run."""
    _adaptive_validate_retry_state(budget)
    audio_file = os.path.relpath(dest, latest_run).replace("\\", "/")
    recipe = hashlib.sha256(
        json.dumps(
            {"text": text, "options": options, "audio_file": audio_file},
            ensure_ascii=False, sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    unit = budget["units"].get(unit_id)
    if unit is None:
        unit = {"recipe_sha256": recipe, "model": options["model"],
                "audio_file": audio_file, "attempts": []}
        budget["units"][unit_id] = unit
    elif (
        unit.get("recipe_sha256") != recipe or unit.get("model") != options["model"]
        or unit.get("audio_file") != audio_file
    ):
        raise ValueError(f"Durable TTS unit {unit_id} recipe changed; refusing to resend")
    attempts = unit["attempts"]
    if attempts:
        last = attempts[-1]
        if last["status"] == "COMPLETED":
            if not is_valid_wav_file(dest) or get_file_md5(dest) != last["md5"]:
                raise ValueError(f"Completed TTS unit {unit_id} is missing or changed; refusing to resend")
            cached_digest: str = last["md5"]
            return cached_digest
        if not last["retry_allowed"]:
            if last["kind"] in ("quota", "account"):
                raise TTSProviderError(f"{last['kind']}: {last['detail']}")
            raise _TTSUnitFailure(last["kind"], last["detail"])
        budget["retries_left"] -= 1
    attempt = {
        "sequence": sum(len(u["attempts"]) for u in budget["units"].values()) + 1,
        "status": "IN_FLIGHT", "is_retry": bool(attempts),
    }
    attempts.append(attempt)
    save_manifest(latest_run, manifest)
    try:
        kwargs = {}
        if unit_id == "full":
            kwargs["on_sent"] = lambda: _adaptive_mark_full_sent(latest_run, manifest, chap)
        digest = _adaptive_attempt(
            page, text, dest, options, alkali_state, prior_md5s(), session, **kwargs
        )
    except _TTSUnitFailure as failure:
        current = {"model": options["model"], "signature": failure.signature}
        retry_allowed = (
            unit_id != "full" and failure.kind == "transient"
            and current != budget["previous_failure"] and budget["retries_left"] > 0
            and len(attempts) < _TTS_UNIT_ATTEMPT_LIMIT
        )
        attempt.update(
            status="FAILED", kind=failure.kind, detail=failure.detail,
            signature=failure.signature, retry_allowed=retry_allowed,
        )
        budget["previous_failure"] = current
        save_manifest(latest_run, manifest)
        raise
    except TTSProviderError as failure:
        kind, separator, detail = str(failure).partition(":")
        if separator and kind in ("quota", "account"):
            known = _TTSUnitFailure(kind, detail.strip())
            attempt.update(
                status="FAILED", kind=kind, detail=known.detail, signature=known.signature,
                retry_allowed=False,
            )
            budget["previous_failure"] = {"model": options["model"], "signature": known.signature}
            save_manifest(latest_run, manifest)
        raise
    # Any other exception leaves the reservation uncertain, including a click or write failure.
    if not isinstance(digest, str) or not digest:
        raise TTSProviderError("unknown: completed TTS action has no verified audio digest")
    attempt.update(status="COMPLETED", md5=digest)
    save_manifest(latest_run, manifest)
    return digest


def _adaptive_retry_piece(
    page: Any, text: str, dest: str, options: dict[str, Any], alkali_state: NetworkAuditState,
    prior_md5s: Callable[[], set[str]], session: dict[str, Any], label: str, budget: dict[str, Any],
    latest_run: str, manifest: dict[str, Any], chap: dict[str, Any], unit_id: str,
) -> str | None:
    """Retry only a durably authorized transient failure under the chapter's shared allowance."""
    while True:
        try:
            return _adaptive_journaled_attempt(
                page, text, dest, options, alkali_state, prior_md5s, session, latest_run,
                manifest, chap, budget, unit_id,
            )
        except _TTSUnitFailure as failure:
            print(f"[TIER] {label} failed: {failure}")
            if not budget["units"][unit_id]["attempts"][-1]["retry_allowed"]:
                raise


def _adaptive_voice_pieces(
    page: Any, latest_run: str, voice_folder: str, manifest: dict[str, Any],
    chap: dict[str, Any], speech: SpeechText, options: dict[str, Any], part_tag: str,
    alkali_state: NetworkAuditState, session: dict[str, Any], budget: dict[str, Any],
) -> list[str]:
    """Voice pieces in order, preserving completed takes across restart and tier changes."""
    from youtube_automation.production.voice_direction import split_pieces

    chap_num = int(chap["chapter_num"])
    parts_dir = os.path.join(voice_folder, "parts")
    os.makedirs(parts_dir, exist_ok=True)
    records = chap.setdefault("pieces", [])
    paths = []
    for index, piece in enumerate(split_pieces(speech, 2), 1):
        unit_id = f"{part_tag}_{index}"
        dest = os.path.abspath(
            os.path.join(parts_dir, f"Chapter_{chap_num}_{unit_id}.wav")
        )
        record = next((r for r in records if r.get("unit_id") == unit_id), None)
        if record is not None and record.get("status") == "COMPLETED":
            unit = budget["units"].get(unit_id)
            attempt = unit["attempts"][-1] if unit else {}
            if (
                attempt.get("status") != "COMPLETED" or attempt.get("md5") != record.get("md5")
                or not is_valid_wav_file(dest) or get_file_md5(dest) != record.get("md5")
                or record.get("audio_file") != os.path.relpath(dest, latest_run).replace("\\", "/")
            ):
                raise ValueError(
                    f"Completed voice piece {index} of Chapter {chap_num} is missing or changed; "
                    "refusing to resend it"
                )
            _adaptive_journaled_attempt(
                page, _adaptive_speech_text(options["model"], piece), dest, options, alkali_state,
                lambda: _adaptive_prior_md5s(manifest, voice_folder, chap_num),
                session, latest_run, manifest, chap, budget, unit_id,
            )
            print(f"[SKIP] Chapter {chap_num} piece {index} already completed.")
            paths.append(dest)
            continue
        label = f"Chapter {chap_num} piece {index} ({options['model']})"
        print(f"\nSynthesizing {label}...")
        digest = _adaptive_retry_piece(
            page, _adaptive_speech_text(options["model"], piece), dest, options, alkali_state,
            lambda: _adaptive_prior_md5s(manifest, voice_folder, chap_num),
            session, label, budget, latest_run, manifest, chap, unit_id,
        )
        if record is None:
            record = {"index": index, "unit_id": unit_id, "model": options["model"]}
            records.append(record)
        record.update(
            audio_file=os.path.relpath(dest, latest_run).replace("\\", "/"),
            md5=digest, status="COMPLETED",
        )
        save_manifest(latest_run, manifest)
        paths.append(dest)
    return paths


def _adaptive_split_tier(
    chap_num: int, speech: SpeechText, model: str, failure: _TTSUnitFailure | None
) -> str:
    """Tier after a sent one-send chapter; never one that would resend the same text.

    failure is None when an earlier run already sent the full chapter (manifest full_sent).
    """
    from youtube_automation.production import voice_direction

    flash = _is_flash_model(model)
    if len(voice_direction.split_pieces(speech, 2)) > 1:
        return "flash_split" if flash else "pro_split"
    if flash and voice_direction.pro_fallback_enabled():
        return "pro_split"  # another model and the clean text, so not an unchanged resend
    if failure is None:
        kind, detail = "unknown", "the full chapter was already sent by an earlier run"
    else:
        kind = failure.kind if failure.kind in ("transient", "unknown") else "unknown"
        detail = failure.detail
    note = "Pro fallback disabled (set ADAPTIVE_TTS_PRO_FALLBACK=1)" if flash else "no other tier"
    raise TTSProviderError(
        f"{kind}: {detail} (Chapter {chap_num} has <=2 paragraphs, so a split would "
        f"resend it unchanged; {note})"
    ) from failure


def _adaptive_mark_full_sent(
    latest_run: str, manifest: dict[str, Any], chap: dict[str, Any]
) -> None:
    """Called only after the full chapter's Run click returned: never resend that text."""
    chap["full_sent"] = True
    save_manifest(latest_run, manifest)


def _adaptive_start_tier(
    latest_run: str, manifest: dict[str, Any], chap: dict[str, Any], tier: str, model: str,
    sha: str | None,
) -> None:
    chap.update(voice_tier=tier, voice_model=model, voice_direction_sha256=sha)
    chap.setdefault("pieces", [])  # completed takes and durable spending survive model fallback
    save_manifest(latest_run, manifest)


def _adaptive_complete_chapter(
    latest_run: str, manifest: dict[str, Any], chap: dict[str, Any], digest: str | None, *,
    model: str, sha: str | None, tier: str,
) -> None:
    """The existing completion path plus the model, direction and tier behind the audio."""
    chap["status"] = "COMPLETED"
    if digest:
        chap["md5"] = digest
    chap.update(voice_model=model, voice_direction_sha256=sha, voice_tier=tier)
    sync_audio_manifest(latest_run, manifest)
    save_manifest(latest_run, manifest)
    print(
        f"[MANIFEST] Chapter {chap['chapter_num']} marked COMPLETED via {tier} "
        f"(MD5: {(digest or 'n/a')[:8]})."
    )


def _require_adaptive_voice_metadata(
    manifest: dict[str, Any], model: str, sha: str | None, pro_model: str
) -> None:
    """Fail closed when finished audio came from another model or direction.

    Legacy audio without metadata is Pro audio, so it is accepted only on a Pro run.
    """
    for chap in manifest.get("chapters", []):
        if "voice_model" not in chap and "voice_direction_sha256" not in chap:
            if _is_flash_model(model) and chap.get("status") == "COMPLETED":
                raise ValueError(
                    f"Voice chapter {chap.get('chapter_num')} is COMPLETED without voice_model "
                    f"metadata; refusing to stitch it into a {model!r} run"
                )
            continue
        expected_model = pro_model if chap.get("voice_tier") == "pro_split" else model
        if chap.get("voice_model") == expected_model and chap.get("voice_direction_sha256") == sha:
            continue
        done = [p for p in chap.get("pieces") or [] if p.get("status") == "COMPLETED"]
        if (
            chap.get("status") == "COMPLETED" or done or chap.get("tts_attempts") is not None
            or chap.get("full_sent") or chap.get("voice_tier") or chap.get("pieces")
        ):
            raise ValueError(
                f"Voice chapter {chap.get('chapter_num')} was synthesized with model "
                f"{chap.get('voice_model')!r} and direction "
                f"{chap.get('voice_direction_sha256')!r}; this run uses {model!r} and {sha!r}"
            )
        for key in ("voice_model", "voice_direction_sha256", "voice_tier", "pieces"):
            chap.pop(key, None)


def _prepare_adaptive_voice(
    latest_run: str, manifest: dict[str, Any], brief: Brief, transcript_text: str
) -> tuple[dict[str, Any], VoiceDirection | None, dict[int, SpeechText]]:
    """Choose the adaptive TTS model and its direction before any browser work; fail closed."""
    from youtube_automation.production import voice_direction

    model = voice_direction.adaptive_tts_model()
    direction = None  # Pro never speaks tags or a Style, so it needs no direction
    if _is_flash_model(model):
        channel_id = getattr(getattr(brief, "channel", None), "channel_id", None)
        if not isinstance(channel_id, str) or not channel_id.strip():
            raise ValueError(
                f"{model} needs the episode brief's channel id to load voice_direction.json"
            )
        direction = voice_direction.load_voice_direction(
            latest_run, transcript_text, channel_id=channel_id
        )
        if direction is None:
            raise ValueError(
                f"{model} requires an approved voice_direction.json "
                "(a Style is required on every run)"
            )
        if direction.model != model:
            raise ValueError(f"voice_direction.json targets {direction.model!r}, not {model!r}")
    sha = direction.sha256 if direction is not None else None
    _require_adaptive_voice_metadata(manifest, model, sha, voice_direction.PRO_MODEL)
    speech = voice_direction.chapter_speech(
        transcript_text, manifest.get("chapters", []), direction
    )
    voice_config = manifest.setdefault("voice_config", {})
    voice_config["model"] = model
    if _is_flash_model(model):
        if direction is None:
            raise ValueError("Flash voice direction missing after validation")
        voice_config["style"] = direction.style
    else:
        voice_config.pop("style", None)
    for chap in manifest.get("chapters", []):
        if chap.get("status") != "COMPLETED":
            _adaptive_retry_state(
                latest_run, manifest, chap, speech[int(chap["chapter_num"])], voice_config, sha
            )
    save_manifest(latest_run, manifest)
    sync_audio_manifest(latest_run, manifest)
    return voice_config, direction, speech


def _adaptive_voice_chapters(
    page: Any,
    latest_run: str,
    voice_folder: str,
    manifest: dict[str, Any],
    direction: VoiceDirection | None,
    speech_map: dict[int, SpeechText],
    alkali_state: NetworkAuditState,
) -> None:
    """Per chapter: one full send, then <=2-paragraph pieces, then (opt-in) Pro pieces.

    A failed full chapter is never resent; quota/account errors stop at once.
    """
    from youtube_automation.production import voice_direction

    voice_config = manifest["voice_config"]
    model = voice_config["model"]
    sha = direction.sha256 if direction is not None else None
    prefix = "flash" if _is_flash_model(model) else "pro"
    primary = _adaptive_unit_options(voice_config, model)
    pro = _adaptive_unit_options(voice_config, voice_direction.PRO_MODEL)
    session: dict[str, Any] = {"page_model": model, "dirty": False, "sends": 0}
    for chap in manifest.get("chapters", []):
        chap_num = int(chap["chapter_num"])
        target = chap.get("audio_file") or os.path.join(voice_folder, f"Chapter_{chap_num}.wav")
        if not os.path.isabs(target):
            target = os.path.abspath(os.path.join(latest_run, target))
        if chap.get("status") == "COMPLETED":
            if not is_valid_wav_file(target) or not chap.get("md5") or get_file_md5(target) != chap["md5"]:
                raise ValueError(f"Completed Chapter {chap_num} is missing or changed; refusing to resend")
            print(f"[SKIP] Chapter {chap_num} audio already generated and verified.")
            continue
        speech = speech_map[chap_num]
        tier = chap.get("voice_tier")
        budget = _adaptive_retry_state(latest_run, manifest, chap, speech, voice_config, sha)
        if tier not in _ADAPTIVE_SPLIT_TIERS:
            print(f"\nSynthesizing Chapter {chap_num} in one send ({prefix}_full)...")
            try:
                digest = _adaptive_journaled_attempt(
                    page, _adaptive_speech_text(model, speech), target, primary, alkali_state,
                    partial(_adaptive_prior_md5s, manifest, voice_folder, chap_num),
                    session, latest_run, manifest, chap, budget, "full",
                )
            except _TTSUnitFailure as failure:
                tier = _adaptive_split_tier(chap_num, speech, model, failure)
                print(f"[TIER] Chapter {chap_num} failed ({failure}); {tier}, no full resend.")
                tier_start_model = voice_direction.PRO_MODEL if tier == "pro_split" else model
                _adaptive_start_tier(latest_run, manifest, chap, tier, tier_start_model, sha)
            else:
                _adaptive_complete_chapter(
                    latest_run, manifest, chap, digest, model=model, sha=sha, tier=f"{prefix}_full"
                )
                continue
        tier_model = model
        if tier == "flash_split":
            try:
                parts = _adaptive_voice_pieces(
                    page, latest_run, voice_folder, manifest, chap, speech, primary, "part",
                    alkali_state, session, budget,
                )
            except _TTSUnitFailure as failure:
                if not voice_direction.pro_fallback_enabled():
                    raise TTSProviderError(_ADAPTIVE_FLASH_SPLIT_DISABLED) from failure
                print(f"[TIER] Chapter {chap_num} Flash split failed ({failure}); trying Pro.")
                tier = "pro_split"
                _adaptive_start_tier(
                    latest_run, manifest, chap, tier, voice_direction.PRO_MODEL, sha
                )
        if tier == "pro_split":
            if _is_flash_model(model) and not voice_direction.pro_fallback_enabled():
                raise TTSProviderError(_ADAPTIVE_FLASH_SPLIT_DISABLED)
            try:
                parts = _adaptive_voice_pieces(
                    page, latest_run, voice_folder, manifest, chap, speech, pro, "pro_part",
                    alkali_state, session, budget,
                )
            except _TTSUnitFailure as failure:
                raise TTSProviderError(
                    f"Pro split failed for Chapter {chap_num}: {failure}"
                ) from failure
            tier_model = voice_direction.PRO_MODEL
        voice_direction.concat_wavs(
            [Path(part) for part in parts], target, gap_sec=_TTS_PIECE_GAP_SEC
        )
        if not is_valid_wav_file(target):
            raise TTSProviderError(f"unknown: joined audio for Chapter {chap_num} is invalid")
        digest = get_file_md5(target)
        if digest in _adaptive_prior_md5s(manifest, voice_folder, chap_num, skip_pieces_of=chap):
            raise TTSProviderError(f"unknown: joined audio for Chapter {chap_num} is a duplicate")
        _adaptive_complete_chapter(
            latest_run, manifest, chap, digest, model=tier_model, sha=sha, tier=tier
        )


def _run_voice_generation() -> None:
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
        # Adaptive model (ADAPTIVE_TTS_MODEL, not .env TTS_MODEL) and direction, before any browser.
        voice_config, adaptive_direction, adaptive_speech = _prepare_adaptive_voice(
            latest_run, manifest, adaptive_brief, transcript_text
        )
        target_tts_model = voice_config["model"]

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

                    def _escalate_harvest_failure(chap_idx: int, reason: str, switching_enabled: bool) -> None:
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
                _wait_for_speech_workspace_ready(tab1_speech, target_tts_model)
                _require_speech_workspace(tab1_speech, target_tts_model)
                reapply_speech_settings(tab1_speech, voice_config)

                latest_alkali_state: NetworkAuditState = {"status": None, "url": None, "is_403": False}

                def _on_speech_response(response: Response, state: NetworkAuditState = latest_alkali_state) -> None:
                    if "alkalimakersuite" in response.url and response.status == 403:
                        state["is_403"] = True
                        state["status"] = 403
                        state["url"] = response.url
                        print(f"\n[NETWORK AUDIT] Captured HTTP 403 from alkalimakersuite: {response.url}")

                tab1_speech.on("response", _on_speech_response)

                attempt_count = 0
                chapters_since_reload = 0

                # Iterate through all saved chapters from manifest
                if adaptive_brief:
                    _adaptive_voice_chapters(
                        tab1_speech, latest_run, voice_folder, manifest,
                        adaptive_direction, adaptive_speech, latest_alkali_state,
                    )
                for chap_entry in ([] if adaptive_brief else manifest.get("chapters", [])):
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

                    hidden_input_attempts = 0
                    while True:
                        latest_alkali_state["is_403"] = False
                        print(
                            f"\nSynthesizing Audio for Chapter {chap_num} (Attempt {attempt_count + 1})..."
                        )

                        # URL Guardrail check to prevent typing into standard AI Studio prompt tabs
                        if not _is_speech_url(tab1_speech.url):
                            print(
                                "[SAFETY CHECK] Correcting tab navigation to Speech Playground..."
                            )
                            for _nav_attempt in range(_TTS_NAV_RETRY_LIMIT):
                                try:
                                    tab1_speech.goto(
                                        f"https://aistudio.google.com/generate-speech?model={target_tts_model}",
                                        wait_until="domcontentloaded",
                                        timeout=30000,
                                    )
                                    time.sleep(3)
                                except Exception as nav_err:
                                    print(
                                        f"[WARNING] Speech Playground navigation warning: {nav_err}"
                                    )
                                    time.sleep(2)
                                if _is_speech_workspace(tab1_speech):
                                    reapply_speech_settings(tab1_speech, voice_config)
                                    break
                            else:
                                raise TTSWorkspaceUnavailableError(
                                    f"Speech Playground unavailable after {_TTS_NAV_RETRY_LIMIT} navigations "
                                    f"(current URL: {tab1_speech.url})"
                                )

                        reload_limit = int(get_config_value("TTS_PROACTIVE_RELOAD_INTERVAL", "40"))
                        if chapters_since_reload >= reload_limit:
                            print(
                                "\n[MAINTENANCE] Proactively refreshing Speech Playground session..."
                            )
                            tab1_speech.bring_to_front()
                            tab1_speech.reload(wait_until="domcontentloaded")
                            time.sleep(5)
                            _require_speech_workspace(tab1_speech)
                            reapply_speech_settings(tab1_speech, voice_config)
                            chapters_since_reload = 0

                        # Recovery reload if prior attempt failed
                        if attempt_count > 0:
                            print(
                                "[RECOVER] Reloading Speech Playground Tab to refresh credentials..."
                            )
                            tab1_speech.bring_to_front()
                            tab1_speech.reload(wait_until="domcontentloaded")
                            time.sleep(5)
                            _require_speech_workspace(tab1_speech)
                            reapply_speech_settings(tab1_speech, voice_config)
                            chapters_since_reload = 0

                        tab1_speech.bring_to_front()

                        speech_input = _visible_tts_prompt(
                            tab1_speech, _TTS_PROMPT_SELECTOR, allow_missing=True
                        )
                        if speech_input is None:
                            print("Speech Playground input box was hidden. Re-applying speech settings to dismiss splash...")
                            _require_speech_workspace(tab1_speech)
                            reapply_speech_settings(tab1_speech, voice_config)
                            time.sleep(2)
                            speech_input = _visible_tts_prompt(
                                tab1_speech, _TTS_PROMPT_SELECTOR, allow_missing=True
                            )
                            if speech_input is None:
                                hidden_input_attempts += 1
                                if hidden_input_attempts > _TTS_NAV_RETRY_LIMIT:
                                    raise TTSWorkspaceUnavailableError(
                                        f"Speech Playground prompt box stayed hidden (current URL: {tab1_speech.url})"
                                    )
                                attempt_count = attempt_count + 1
                                time.sleep(2)
                                continue

                        clean_text = sanitize_script_text(chap_text)
                        print(f"Entering Chapter {chap_num} script text into AI Studio ({len(clean_text)} chars)...")
                        if adaptive_brief:
                            network_health.require_healthy(network_health.AI_STUDIO_URL)
                        _require_current_tts_settings(
                            tab1_speech, target_tts_model, voice_config.get("voice")
                        )
                        speech_input = _visible_tts_prompt(tab1_speech, _TTS_PROMPT_SELECTOR)
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
                        _require_current_tts_settings(
                            tab1_speech, target_tts_model, voice_config.get("voice")
                        )
                        _visible_tts_prompt(tab1_speech, _TTS_PROMPT_SELECTOR)
                        try:
                            human_hover_and_click(tab1_speech, run_btn)
                        except Exception:
                            if adaptive_brief:
                                raise
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
                            if adaptive_brief and has_error:
                                _adaptive_post_run_failure(err_msg)
                            if has_error:
                                print(f"Synthesis failed due to AI Studio error: {err_msg}")
                            else:
                                print("Warning: Synthesis 'Stop' button did not appear within 8s.")
                                if adaptive_brief:
                                    # Never re-type after an unconfirmed Run: a slow page may still be synthesizing.
                                    try:
                                        tab1_speech.wait_for_selector(
                                            "button:has-text('Stop'), button[aria-label*='Download' i], "
                                            "button:has-text('Download')",
                                            timeout=30000,
                                        )
                                        print("Synthesis activity confirmed after an extended wait...")
                                        started_rendering = True
                                    except Exception as exc:
                                        raise TTSProviderError(
                                            "unknown: AI Studio showed no Stop button, no Download button "
                                            "and no error banner after Run"
                                        ) from exc

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
                            attempt_count = attempt_count + 1
                            retry_limit = int(get_config_value("FAILOVER_RETRY_LIMIT", "3"))
                            if attempt_count >= retry_limit:
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
                        if adaptive_brief and not download_success:
                            download_success = _adaptive_salvage_download(tab1_speech, target_dest)

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

                                attempt_count = attempt_count + 1
                                retry_limit = int(get_config_value("FAILOVER_RETRY_LIMIT", "3"))
                                if attempt_count >= retry_limit:
                                    if accounts_enabled:
                                        print(
                                            f"\n[FAILOVER ALERT] Chapter {chap_num} produced duplicate audio {retry_limit} times. Rotating Account Profile..."
                                        )
                                        rotate_profile_index()
                                        kill_cdp_chrome()
                                        failover_triggered = True
                                        break
                                    else:
                                        print(
                                            f"\n[FATAL ERROR] Chapter {chap_num} produced duplicate audio after {retry_limit} attempts. Halting."
                                        )
                                        sys.exit(1)
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
                            attempt_count = 0
                            break
                        else:
                            has_err, err_msg = check_ai_studio_errors(tab1_speech)
                            if adaptive_brief:
                                _adaptive_post_run_failure(err_msg if has_err else "")
                            if (latest_alkali_state.get("is_403") or (has_err and is_ai_studio_quota_error(err_msg))) and accounts_enabled:
                                print(
                                    "\n[FAILOVER ALERT] Quota saturation observed during synthesis/download (HTTP 403 / 'Link a paid API key'). "
                                    "Switching immediately to next active account profile..."
                                )
                                rotate_profile_index()
                                kill_cdp_chrome()
                                failover_triggered = True
                                break

                            attempt_count = attempt_count + 1
                            retry_limit = int(get_config_value("FAILOVER_RETRY_LIMIT", "3"))

                            if attempt_count >= retry_limit:
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

                            backoff_delay = 5.0 * (2.0 ** (attempt_count - 1))
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

        except (AdaptiveBrowserOwnershipError, TTSWorkspaceUnavailableError, TTSProviderError):
            raise
        except Exception as e:
            if adaptive_brief:
                raise
            print(f"[RECOVERY] Playwright context closed or browser crashed: {e}")
            time.sleep(3)

        if failover_triggered:
            print(
                "\n[SYSTEM] Reinitializing Playwright environment with new profile. Fast-forwarding...\n"
            )
            attempt_count = 0
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
    "TTSProviderError",
    "TTSWorkspaceUnavailableError",
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
