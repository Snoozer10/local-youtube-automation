"""Audacity automation client module.

Provides Win32 Named Pipes IPC (\\\\.\\pipe\\ToSrvPipe and \\\\.\\pipe\\FromSrvPipe),
macro preset synchronization, and automated batch audio polishing.
"""

import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Protocol, TextIO, TypedDict

from typing_extensions import Unpack

from youtube_automation.audio.wav_validation import AudioProbe
from youtube_automation.core.audacity_windows import OwnedAudacityWindows
from youtube_automation.core.window_readiness import (
    ProcessLike,
    ReadinessState,
    wait_for_owned_window_readiness,
)

# Windows console hardening: guarantee UTF-8 for Arabic output even when piped.
if sys.platform.startswith("win") and isinstance(sys.stdout, io.TextIOWrapper) and isinstance(sys.stderr, io.TextIOWrapper):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass


class _ExchangeOutcome(TypedDict, total=False):
    response: str
    error: BaseException


class CommandOptions(TypedDict, total=False):
    strict: bool
    timeout_sec: float


class CommandSender(Protocol):
    def __call__(self, write_pipe: TextIO, read_pipe: TextIO, command: str,
                 *, strict: bool = False, timeout_sec: float = 90) -> str: ...


class PipeNewlineOptions(TypedDict, total=False):
    newline: str


class PipeOpener(Protocol):
    def __call__(self, file: str, mode: Literal["r", "w"] = "r", *, encoding: str,
                 newline: str | None = None) -> TextIO: ...


class PipeOwnerVerifier(Protocol):
    def __call__(self, write_pipe: TextIO, read_pipe: TextIO, expected_pid: int) -> bool: ...


def get_latest_run_folder(runs_path: str = "youtube_runs") -> str | None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    rel_to_script = os.path.join(script_dir, runs_path)
    resolved_path = rel_to_script if os.path.exists(rel_to_script) else runs_path
    if not os.path.exists(resolved_path):
        return None
    subdirs = [
        os.path.join(runs_path, d)
        for d in os.listdir(runs_path)
        if os.path.isdir(os.path.join(runs_path, d))
    ]
    if not subdirs:
        return None
    return max(subdirs, key=os.path.getmtime)


def send_audacity_command(write_pipe: TextIO, read_pipe: TextIO, command: str, *, strict: bool = False, timeout_sec: float = 90) -> str:
    """Sends a single scripting command to Audacity and waits for response.

    Audacity Named Pipe protocol:
    Audacity transmits arbitrary information lines (often starting with a leading newline
    when no textual output is produced), followed by 'BatchCommand finished: <status>',
    followed by a final empty line ('\\n') marking completion.
    """
    def exchange() -> str:
        eol = "\r\n\0" if sys.platform == "win32" else "\n"
        write_pipe.write(command + eol)
        write_pipe.flush()

        response = ""
        saw_batch_finished = False
        while True:
            line = read_pipe.readline()
            if not line:  # Audacity crashed or closed pipe
                if strict:
                    if not saw_batch_finished:
                        raise RuntimeError(f"Audacity command did not confirm success: {command}: response ended before BatchCommand finished status")
                    raise RuntimeError(f"Audacity command did not confirm success: {command}: response ended before terminal blank boundary")
                break
            response += line
            if strict and len(response) > 1024 * 1024:
                raise ValueError(f"Audacity response exceeded 1 MiB: {command}")

            if "BatchCommand finished" in line:
                saw_batch_finished = True
            elif saw_batch_finished and line.strip() == "":
                break
            elif not saw_batch_finished and line.strip() == "":
                if strict:
                    if response.strip():
                        raise RuntimeError(f"Audacity command did not confirm success: {command}: response ended before BatchCommand finished status")
                    continue                # A contentful blank boundary ends the reply; strict mode
                # independently enforces the explicit success marker.
                if response.strip():
                    break
                # Keep empty leading replies compatible with legacy mocks.
                if hasattr(read_pipe, "has_pending") and not read_pipe.has_pending():
                    break
        return response

    t0 = time.perf_counter()
    if strict:
        if timeout_sec <= 0:
            raise ValueError("Audacity command timeout must be positive")
        outcome: _ExchangeOutcome = {}
        finished = threading.Event()

        def run_exchange() -> None:
            try:
                outcome["response"] = exchange()
            except BaseException as exc:
                outcome["error"] = exc
            finally:
                finished.set()

        threading.Thread(target=run_exchange, daemon=True).start()
        if not finished.wait(timeout_sec):
            raise TimeoutError(f"Audacity command timed out after {timeout_sec}s: {command}")
        if "error" in outcome:
            raise outcome["error"]
        response = outcome["response"]
    else:
        response = exchange()

    latency_ms = (time.perf_counter() - t0) * 1000
    cleaned_response = response.strip().replace("\n", " | ")
    status_tag = "OK" if ("OK" in cleaned_response or "BatchCommand finished: OK" in cleaned_response) else "INFO"
    if "failed" in cleaned_response.lower() or "error" in cleaned_response.lower():
        status_tag = "WARN"
    print(f"  [PIPE {status_tag} ({latency_ms:5.1f}ms)] {command} -> {cleaned_response}", flush=True)
    if strict and not re.search(r"(?im)^BatchCommand finished:\s*OK\s*$", response):
        raise RuntimeError(f"Audacity command did not confirm success: {command}: {cleaned_response}")
    return response


def find_preset_file() -> str | None:
    """Locates the preset text file in the workspace."""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    candidates = [
        "YouTube_Voice_Optimizer.txt.txt",
        "YouTube_Voice_Optimizer.txt",
        "YouTube_Voice_Optimizer",
    ]
    for filename in candidates:
        path = os.path.join(project_root, filename)
        if os.path.isfile(path):
            return path
    return None


def sync_macro_to_audacity(preset_path: str | None) -> None:
    """Copies the preset file into Audacity's AppData Macros folder before launch."""
    if not preset_path or not os.path.exists(preset_path):
        return

    appdata = os.getenv("APPDATA")
    if not appdata:
        return

    macros_dir = os.path.join(appdata, "audacity", "macros")
    os.makedirs(macros_dir, exist_ok=True)

    # Copy under both possible names so Audacity GUI always registers it
    try:
        shutil.copy(preset_path, os.path.join(macros_dir, "YouTube_Voice_Optimizer.txt"))
        shutil.copy(
            preset_path, os.path.join(macros_dir, "Achird Gemini Voice cut and enhance.txt")
        )
        print(f"[SYSTEM] Synced preset settings to Audacity Macros folder: {macros_dir}")
    except Exception as e:
        print(f"[WARNING] Could not sync macro file to AppData: {e}")


def apply_preset_file(write_pipe: TextIO, read_pipe: TextIO, preset_path: str | None, *, strict: bool = False, command_sender: CommandSender | None = None) -> bool:
    """Reads effect settings line-by-line preset file and executes them via pipe."""
    if not preset_path or not os.path.exists(preset_path):
        return False

    print(f" Applying preset settings directly '{preset_path}'...")
    with open(preset_path, encoding="utf-8") as f:
        lines = f.readlines()

    sender = command_sender or send_audacity_command

    def send(command: str) -> str:
        if strict:
            return sender(write_pipe, read_pipe, command, strict=True)
        return sender(write_pipe, read_pipe, command)

    executed_count = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Ignore export commands inside preset files (export is handled explicitly by Python).
        if line.startswith("Export") or line.startswith("ExportWav"):
            continue

        # Select all audio before applying each effect (avoid duplicate SelectAll).
        if not line.startswith("SelectAll"):
            send("SelectAll:")

        # Ensure correct formatting (e.g. "NoiseGate:attack=..." instead of "NoiseGate: attack=...").
        if ":" in line:
            cmd_name, cmd_args = line.split(":", 1)
            formatted_cmd = f"{cmd_name.strip()}:{cmd_args.strip()}"
        else:
            formatted_cmd = line.strip()

        send(formatted_cmd)
        executed_count += 1
        time.sleep(0.2)

    return executed_count > 0


def load_checkpoint(folder: str) -> list[str]:
    path = os.path.join(folder, "audacity_checkpoint.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                files: list[str] = data.get("polished_files", [])
                return files
        except Exception as e:
            print(f"[WARNING] Ignoring unreadable audacity_checkpoint.json: {e}")
    return []


def save_checkpoint(folder: str, polished_files: Sequence[str]) -> None:
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "audacity_checkpoint.json")
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"polished_files": polished_files}, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def delete_checkpoint(folder: str) -> None:
    path = os.path.join(folder, "audacity_checkpoint.json")
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            print(f"[WARNING] Could not delete audacity_checkpoint.json: {e}")


def ensure_audacity_script_pipe_enabled() -> None:
    """Enable and verify Audacity's script pipe in the exact [Module] section."""
    appdata = os.getenv("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is required to verify Audacity script-pipe configuration")

    cfg_path = os.path.join(appdata, "audacity", "audacity.cfg")

    def configure(raw: bytes) -> bytes:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("Audacity configuration is not valid UTF-8") from exc

        bom = "\ufeff" if text.startswith("\ufeff") else ""
        content = text[len(bom) :]
        lines = content.splitlines(keepends=True)
        newline = "\r\n" if "\r\n" in content else "\r" if "\r" in content and "\n" not in content else "\n"

        def section_name(line: str) -> str:
            return line.strip().strip("\r\n")

        module_headers = [
            index
            for index, line in enumerate(lines)
            if section_name(line.lstrip("\ufeff") if index == 0 else line).casefold() == "[module]"
        ]
        if len(module_headers) > 1:
            raise RuntimeError("Audacity configuration has duplicate [Module] sections")

        if not module_headers:
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += newline
            lines.extend([f"[Module]{newline}", f"mod-script-pipe=1{newline}"])
        else:
            header = module_headers[0]
            next_section = next(
                (
                    index
                    for index in range(header + 1, len(lines))
                    if lines[index].strip().startswith("[")
                    and lines[index].strip().endswith("]")
                ),
                len(lines),
            )
            setting_indices = [
                index
                for index in range(header + 1, next_section)
                if re.match(r"^\s*mod-script-pipe\s*=", lines[index], re.IGNORECASE)
            ]
            if len(setting_indices) > 1:
                raise RuntimeError("Audacity configuration has duplicate mod-script-pipe settings")

            if setting_indices:
                index = setting_indices[0]
                line = lines[index]
                match = re.match(r"^(\s*mod-script-pipe\s*=\s*)(.*?)(\r\n|\r|\n)?$", line, re.IGNORECASE)
                if not match:
                    raise RuntimeError("Audacity mod-script-pipe setting cannot be parsed")
                key_match = re.match(r"^\s*([^=]+?)\s*=", line)
                if not key_match or key_match.group(1).strip() != "mod-script-pipe":
                    raise RuntimeError("Audacity mod-script-pipe key spelling is not canonical")
                prefix, value, ending = match.groups()
                if ";" in value or "#" in value:
                    raise RuntimeError("Audacity mod-script-pipe has an ambiguous inline comment")
                if value.strip() != "1":
                    indentation = line[:len(line) - len(line.lstrip())]
                    lines[index] = f"{indentation}mod-script-pipe=1{ending or ''}"
            else:
                header_line = lines[header]
                ending = "\r\n" if header_line.endswith("\r\n") else "\r" if header_line.endswith("\r") else "\n" if header_line.endswith("\n") else newline
                if not header_line.endswith(("\n", "\r")):
                    lines[header] += ending
                lines.insert(header + 1, f"mod-script-pipe=1{ending}")

        return (bom + "".join(lines)).encode("utf-8")

    try:
        original = open(cfg_path, "rb").read() if os.path.exists(cfg_path) else b""
        updated = configure(original)
        if updated != original:
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            temp_path = f"{cfg_path}.{uuid.uuid4().hex}.tmp"
            descriptor = os.open(temp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(updated)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, cfg_path)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        readback = open(cfg_path, "rb").read()
        if readback != updated:
            raise RuntimeError("Audacity configuration changed during readback verification")
        if configure(readback) != readback:
            raise RuntimeError("Audacity script-pipe configuration failed readback verification")
    except Exception as exc:
        raise RuntimeError(f"Could not configure or verify Audacity script pipe: {exc}") from exc


def clear_audacity_temp_data() -> None:
    """Wipes Audacity's temporary SessionData and AutoSave folders to prevent recovery popups."""
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        session_data_dir = os.path.join(local_appdata, "Audacity", "SessionData")
        if os.path.exists(session_data_dir):
            for item in os.listdir(session_data_dir):
                item_path = os.path.join(session_data_dir, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                except Exception:
                    pass

    roaming_appdata = os.getenv("APPDATA")
    if roaming_appdata:
        autosave_dir = os.path.join(roaming_appdata, "audacity", "AutoSave")
        if os.path.exists(autosave_dir):
            for item in os.listdir(autosave_dir):
                item_path = os.path.join(autosave_dir, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                except Exception:
                    pass


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


def sync_polished_audio_manifest(latest_run: str, silence_padding_sec: float = 0.300, *, strict: bool = False) -> dict[str, Any] | None:
    """Synchronize post-mastered audio durations and paths from polished_chapters.

    Adaptive runs update audio_manifest.json only, preserving the raw voice
    checkpoint. Legacy runs also update voice_generation_manifest.json.
    """
    if strict:
        return _sync_adaptive_polished_manifest(latest_run)
    if not latest_run or not os.path.exists(latest_run):
        return None

    polished_dir = os.path.join(latest_run, "polished_chapters")
    if not os.path.exists(polished_dir):
        return None

    audio_manifest_path = os.path.join(latest_run, "audio_manifest.json")
    voice_manifest_path = os.path.join(latest_run, "voice_generation_manifest.json")

    # 1. Update audio_manifest.json if present
    if os.path.exists(audio_manifest_path):
        try:
            with open(audio_manifest_path, encoding="utf-8") as f:
                data = json.load(f)

            padding = float(data.get("silence_padding_sec", silence_padding_sec))
            current_time = 0.0
            segments = data.get("segments", [])
            updated_count = 0

            for seg in segments:
                base_name = os.path.basename(seg.get("audio_file", ""))
                if not base_name:
                    seg_idx = seg.get("index", 1)
                    base_name = f"Chapter_{seg_idx}.wav"

                polished_path = os.path.join(polished_dir, base_name)
                probe = probe_audio_file(polished_path) if os.path.exists(polished_path) else None

                if probe:
                    duration = probe["duration"]
                    seg["audio_file"] = f"polished_chapters/{base_name}"
                    seg["duration"] = duration
                    updated_count += 1
                else:
                    duration = float(seg.get("duration", 0.0))

                start_time = round(current_time, 3)
                end_time = round(start_time + duration, 3)
                seg["start_time"] = start_time
                seg["end_time"] = end_time

                if seg.get("status") == "COMPLETED" and duration > 0:
                    current_time = end_time + padding
                else:
                    current_time = end_time

            data["cumulative_duration_sec"] = round(current_time, 3)

            # Atomic write
            tmp_path = audio_manifest_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, audio_manifest_path)
            print(
                f"[MANIFEST SYNC] Updated audio_manifest.json: {updated_count}/{len(segments)} segments "
                f"re-timed from polished_chapters (cumulative duration: {data['cumulative_duration_sec']}s)"
            )
        except Exception as e:
            print(f"[MANIFEST WARNING] Failed to sync audio_manifest.json with polished audio: {e}")

    # 2. Update voice_generation_manifest.json if present
    if os.path.exists(voice_manifest_path):
        try:
            with open(voice_manifest_path, encoding="utf-8") as f:
                vdata = json.load(f)

            chapters = vdata.get("chapters", [])
            for chap in chapters:
                chap_num = chap.get("chapter_num", chap.get("index", 1))
                base_name = f"Chapter_{chap_num}.wav"
                polished_path = os.path.join(polished_dir, base_name)
                probe = probe_audio_file(polished_path) if os.path.exists(polished_path) else None
                if probe:
                    chap["audio_file"] = f"polished_chapters/{base_name}"
                    chap["duration"] = probe["duration"]
                    chap["sample_rate"] = probe["framerate"]
                    chap["channels"] = probe["channels"]
                    chap["bit_depth"] = probe["sampwidth"] * 8

            tmp_path = voice_manifest_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(vdata, f, ensure_ascii=False, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, voice_manifest_path)
            print("[MANIFEST SYNC] Synchronized voice_generation_manifest.json with polished audio.")
        except Exception as e:
            print(f"[MANIFEST WARNING] Failed to sync voice_generation_manifest.json: {e}")
    return None


def _sync_adaptive_polished_manifest(latest_run: str) -> dict[str, Any]:
    """Record physical, gapless chapter offsets without changing the raw voice checkpoint."""
    from youtube_automation.core.utils import atomic_write_json
    from youtube_automation.production.ledger import publication_guard

    manifest_path = os.path.join(latest_run, "audio_manifest.json")
    data = _adaptive_polished_manifest_payload(latest_run)
    with publication_guard():
        atomic_write_json(manifest_path, data)
    return data


def verify_adaptive_polished_manifest(latest_run: str) -> dict[str, Any]:
    """Reject polished audio that has drifted since the last successful DSP sync."""
    manifest_path = os.path.join(latest_run, "audio_manifest.json")
    with open(manifest_path, encoding="utf-8") as handle:
        recorded: dict[str, Any] = json.load(handle)
    actual = _adaptive_polished_manifest_payload(latest_run)
    if actual != recorded:
        raise ValueError("Polished chapters no longer match the adaptive audio manifest")
    return recorded


def _adaptive_polished_manifest_payload(latest_run: str) -> dict[str, Any]:
    manifest_path = os.path.join(latest_run, "audio_manifest.json")
    with open(manifest_path, encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    segments = data.get("segments", [])
    if not isinstance(segments, list) or not segments:
        raise ValueError("Adaptive audio manifest has no chapter segments")
    polished_dir = os.path.join(latest_run, "polished_chapters")
    total_frames = 0
    sample_rate = None
    fmt = None
    for index, segment in enumerate(segments, 1):
        if segment.get("index") != index or segment.get("status") != "COMPLETED":
            raise ValueError("Adaptive audio manifest chapters are incomplete or out of order")
        name = f"Chapter_{index}.wav"
        path = os.path.join(polished_dir, name)
        probe = probe_audio_file(path)
        if not probe or probe["nframes"] <= 0:
            raise ValueError(f"Missing or invalid polished chapter: {name}")
        current_format = (probe["framerate"], probe["channels"], probe["sampwidth"])
        if fmt is None:
            fmt = current_format
            sample_rate = probe["framerate"]
        elif current_format != fmt:
            raise ValueError(f"Polished chapter format differs: {name}")
        assert sample_rate is not None
        segment["audio_file"] = f"polished_chapters/{name}"
        segment["start_time"] = round(total_frames / sample_rate, 3)
        total_frames += probe["nframes"]
        segment["end_time"] = round(total_frames / sample_rate, 3)
        segment["duration"] = round(probe["nframes"] / sample_rate, 3)
        segment["sample_rate"] = probe["framerate"]
        segment["channels"] = probe["channels"]
        segment["bit_depth"] = probe["sampwidth"] * 8
        digest = hashlib.md5()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        segment["md5"] = digest.hexdigest()
    assert sample_rate is not None and fmt is not None
    data["silence_padding_sec"] = 0.0
    data["cumulative_duration_sec"] = round(total_frames / sample_rate, 3)
    data["completed_segments"] = len(segments)
    data["format"] = {
        "sample_rate": fmt[0],
        "channels": fmt[1],
        "bit_depth": fmt[2] * 8,
        "encoding": "PCM_S16LE" if fmt[2] == 2 else f"PCM_{fmt[2] * 8}BIT",
    }
    return data


def audacity_is_running() -> bool:
    """Refuse to attach an adaptive run to somebody else's open Audacity session."""
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Audacity.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    return any(row and row[0].casefold() == "audacity.exe" for row in csv.reader(result.stdout.splitlines()))


def validate_adaptive_voice_run(latest_run: str) -> tuple[int, str]:
    from youtube_automation.production.contracts import load_brief
    from youtube_automation.production.narration import prepare_manifest
    from youtube_automation.production.writing import verify_written_episode

    verify_written_episode(latest_run)
    brief = load_brief(latest_run)
    with open(os.path.join(latest_run, "voice_generation_manifest.json"), encoding="utf-8") as handle:
        voice_manifest = json.load(handle)
    with open(os.path.join(latest_run, "refined_script.txt"), encoding="utf-8") as handle:
        script = handle.read().strip()
    prepared = prepare_manifest(latest_run, voice_manifest, brief, script)
    if any(chapter["status"] != "COMPLETED" for chapter in prepared["chapters"]):
        raise ValueError("All adaptive voice chapters must complete before Audacity")
    return len(prepared["chapters"]), prepared["adaptive_voice_recipe"]


def main() -> None:
    latest_run = sys.argv[1] if len(sys.argv) > 1 else get_latest_run_folder()
    if not latest_run or not os.path.isdir(latest_run):
        raise ValueError("Audio processing requires an existing run directory")
    adaptive = os.path.isfile(os.path.join(latest_run, "episode_brief.json"))
    if adaptive:
        if len(sys.argv) <= 1:
            raise ValueError("Adaptive Audacity requires an explicit run directory")
        expected_chapters, expected_recipe = validate_adaptive_voice_run(latest_run)
    else:
        expected_chapters, expected_recipe = 0, None
    from youtube_automation.production.ledger import leased_resource, resource_database

    with leased_resource(resource_database(), "audacity"):
        return _process_run(
            latest_run,
            adaptive=adaptive,
            expected_chapters=expected_chapters,
            expected_recipe=expected_recipe,
        )


def _open_text_pipe(file: str, mode: Literal["r", "w"] = "r", *, encoding: str,
                    newline: str | None = None) -> TextIO:
    return open(file, mode, encoding=encoding, newline=newline)


def _open_audacity_pipes(owned_process: ProcessLike, pipe_opener: PipeOpener | None = None) -> tuple[TextIO, TextIO]:
    """Open both script pipes, stopping promptly if the owned child exits."""
    opener = pipe_opener or _open_text_pipe
    write_pipe = None
    read_pipe = None

    for attempt in range(80):
        exit_code = owned_process.poll()
        if exit_code is not None:
            raise RuntimeError(f"Owned Audacity process exited before pipe startup (exit code {exit_code})")

        try:
            newline_options: PipeNewlineOptions = {"newline": ""} if sys.platform == "win32" else {}
            candidate_write = opener(r"\\.\pipe\ToSrvPipe", "w", encoding="utf-8", **newline_options)
            try:
                candidate_read = opener(r"\\.\pipe\FromSrvPipe", encoding="utf-8", **newline_options)
            except Exception:
                candidate_write.close()
                raise
        except OSError as pipe_error:
            if attempt % 10 == 9:
                print(f"  [WAIT] Audacity pipe not ready yet ({attempt + 1}/80)... still waiting")
            for _ in range(10):
                exit_code = owned_process.poll()
                if exit_code is not None:
                    raise RuntimeError(
                        f"Owned Audacity process exited before pipe startup (exit code {exit_code})"
                    ) from pipe_error
                time.sleep(0.1)
        else:
            write_pipe, read_pipe = candidate_write, candidate_read
            break

    if write_pipe is None or read_pipe is None:
        raise ConnectionError(
            "Could not connect to Audacity Named Pipes after 80s! "
            "Verify Audacity.exe is installed and mod-script-pipe=1 is in audacity.cfg."
        )
    return write_pipe, read_pipe


class AudacityReadinessError(RuntimeError):
    """Readiness failed; keep a possible recovery or modal session for inspection."""


def _ensure_audacity_ready(process: ProcessLike, executable_path: str | Path, evidence_dir: str | Path) -> OwnedAudacityWindows:
    """Fail closed unless the launched process has one stable, owned main HWND."""
    try:
        windows = OwnedAudacityWindows(process, executable_path, evidence_dir)
        result = wait_for_owned_window_readiness(
            process, expected_creation_time=windows.creation_time,
            expected_executable=windows.executable, observe=windows.observe,
            capture=windows.capture, timeout_sec=12.0,
            stable_observations=3, interval_sec=0.5,
        )
        if result.state is not ReadinessState.READY:
            raise AudacityReadinessError(
                f"Audacity readiness blocked: {result.state.value}:{result.reason}"
            )
        final = wait_for_owned_window_readiness(
            process, expected_creation_time=windows.creation_time,
            expected_executable=windows.executable, observe=windows.observe,
            capture=windows.capture, timeout_sec=2.0,
            stable_observations=1, interval_sec=0.0,
        )
        if process.poll() is not None:
            raise AudacityReadinessError(
                "Audacity readiness changed:pid_exited:owned_process_exited"
            )
        if final.state is not ReadinessState.READY:
            raise AudacityReadinessError(
                f"Audacity readiness changed: {final.state.value}:{final.reason}"
            )
        return windows
    except AudacityReadinessError:
        raise
    except Exception as exc:
        raise AudacityReadinessError(
            f"Audacity readiness backend failed: {type(exc).__name__}: {exc}"
        ) from exc


def _named_pipe_server_pid(pipe: TextIO) -> int | None:
    """Return the native named-pipe server PID, failing on any unreadable handle."""
    if sys.platform != "win32":
        return None
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_server_pid = kernel32.GetNamedPipeServerProcessId
    get_server_pid.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    get_server_pid.restype = wintypes.BOOL
    server_pid = wintypes.ULONG()
    handle = msvcrt.get_osfhandle(pipe.fileno())
    if not get_server_pid(wintypes.HANDLE(handle), ctypes.byref(server_pid)):
        error = ctypes.get_last_error()
        raise OSError(error, "Could not read Audacity named-pipe server PID")
    return int(server_pid.value)


def _verify_audacity_pipe_owner(write_pipe: TextIO, read_pipe: TextIO, expected_pid: int) -> bool:
    """On Windows require both live pipe handles to be served by the owned process."""
    if sys.platform != "win32":
        return True
    if type(expected_pid) is not int or expected_pid <= 0:
        return False
    try:
        return all(
            _named_pipe_server_pid(pipe) == expected_pid
            for pipe in (write_pipe, read_pipe)
        )
    except Exception:
        return False


def _close_pipe_pair(write_pipe: TextIO | None, read_pipe: TextIO | None) -> None:
    for pipe in (write_pipe, read_pipe):
        try:
            if pipe:
                pipe.close()
        except Exception:
            pass


def _send_owned_audacity_command(
    write_pipe: TextIO,
    read_pipe: TextIO,
    command: str,
    *,
    expected_pid: int,
    command_sender: CommandSender | None = None,
    pipe_owner_verifier: PipeOwnerVerifier | None = None,
    **kwargs: Unpack[CommandOptions],
) -> str:
    verifier = pipe_owner_verifier or _verify_audacity_pipe_owner
    try:
        verified = verifier(write_pipe, read_pipe, expected_pid)
    except Exception as exc:
        _close_pipe_pair(write_pipe, read_pipe)
        raise AudacityReadinessError("Audacity pipe owner query failed closed") from exc
    if verified is not True:
        _close_pipe_pair(write_pipe, read_pipe)
        raise AudacityReadinessError("Audacity pipe owner does not match the launched process")
    sender = command_sender or send_audacity_command
    return sender(write_pipe, read_pipe, command, **kwargs)


def _open_ready_audacity_session(
    process: ProcessLike, executable_path: str | Path, evidence_dir: str | Path, *,
    pipe_opener: PipeOpener | None = None, command_sender: CommandSender | None = None,
    pipe_owner_verifier: PipeOwnerVerifier | None = None,
) -> tuple[TextIO, TextIO]:
    """Guard pipe startup and each handshake command with current owned-window state."""
    _ensure_audacity_ready(process, executable_path, evidence_dir)
    write_pipe, read_pipe = _open_audacity_pipes(process, pipe_opener=pipe_opener)
    try:
        if not write_pipe or not read_pipe:
            raise ConnectionError("Audacity Named Pipes returned an incomplete handle pair")
        _ensure_audacity_ready(process, executable_path, evidence_dir)
        _send_owned_audacity_command(
            write_pipe, read_pipe, "Help: Command=Help", expected_pid=process.pid,
            command_sender=command_sender, pipe_owner_verifier=pipe_owner_verifier, strict=True,
        )
        _ensure_audacity_ready(process, executable_path, evidence_dir)
        _send_owned_audacity_command(
            write_pipe, read_pipe, "SelectAll:", expected_pid=process.pid,
            command_sender=command_sender, pipe_owner_verifier=pipe_owner_verifier, strict=True,
        )
        return write_pipe, read_pipe
    except Exception:
        _close_pipe_pair(write_pipe, read_pipe)
        raise


def _process_run(latest_run: str, *, adaptive: bool, expected_chapters: int = 0, expected_recipe: str | None = None) -> None:
    print("=============================================")
    print("Starting Autonomous Audacity Audio Polishing")
    print("=============================================")

    if audacity_is_running():
        raise RuntimeError(
            "Audacity is already open; close the user-owned session before automated polishing"
        )

    ensure_audacity_script_pipe_enabled()  # <--- CALL IT HERE

    # Find and sync preset file
    preset_file_path = find_preset_file()
    if adaptive and not preset_file_path:
        raise FileNotFoundError("Adaptive Audacity requires a known voice optimizer preset")
    if preset_file_path:
        print(f"[SYSTEM] Found preset file: '{preset_file_path}'")
        if not adaptive:
            sync_macro_to_audacity(preset_file_path)
    else:
        print("[WARNING] No preset file found! Audacity will rely on default internal macros.")

    # 1. Locate Run Folder

    print(f"Target Video Folder: {latest_run}")

    # 2. Determine Processing Target
    master_track_path = os.path.join(latest_run, "full_episode_voice.wav")
    files_to_process = []

    if os.path.exists(master_track_path):
        if adaptive:
            raise ValueError("Adaptive Audacity must polish chapters before the master is stitched")
        print("[SYSTEM] Found 'full_episode_voice.wav'. Targeting the master voice track only.")
        output_dir = os.path.join(latest_run, "audacity_voice")
        files_to_process.append((0, "full_episode_voice.wav", latest_run, output_dir))
    else:
        print("[SYSTEM] Master voice track not found. Scanning 'voice_chapters' subfolder...")
        chapters_dir = os.path.join(latest_run, "voice_chapters")

        if not os.path.exists(chapters_dir):
            print(
                f"Error: Neither 'full_episode_voice.wav' nor the 'voice_chapters' folder exists in '{latest_run}'."
            )
            sys.exit(1)

        output_dir = os.path.join(latest_run, "polished_chapters")
        chapter_files = []
        for name in os.listdir(chapters_dir):
            if name.startswith("Chapter_") and name.endswith(".wav"):
                match = re.search(r"Chapter_(\d+)\.wav", name)
                if match:
                    idx = int(match.group(1))
                    chapter_files.append((idx, name, chapters_dir, output_dir))

        chapter_files.sort(key=lambda x: x[0])

        if not chapter_files:
            print(f"Error: No Chapter_*.wav files found in '{chapters_dir}'.")
            sys.exit(1)

        print(
            f"Found {len(chapter_files)} chapters to polish inside the 'voice_chapters' directory."
        )
        files_to_process = chapter_files
        if adaptive and [index for index, *_rest in chapter_files] != list(range(1, expected_chapters + 1)):
            raise ValueError("Adaptive voice chapter files do not match the verified voice manifest")

    # Load checkpoint progress
    polished_files = load_checkpoint(latest_run)
    if adaptive and polished_files:
        # Legacy checkpoints contain names only, with no source or output digest.
        # Reprocess candidates rather than treating stale WAVs as accepted work.
        polished_files = []
    if polished_files:
        print(
            f"[CHECKPOINT] Resuming. Already polished {len(polished_files)} of {len(files_to_process)} files."
        )

    # 3. Find Audacity Executable Path
    audacity_paths = [
        r"C:\Program Files\Audacity\Audacity.exe",
        r"C:\Program Files (x86)\Audacity\Audacity.exe",
    ]
    executable_path = next((p for p in audacity_paths if os.path.exists(p)), None)
    if not executable_path:
        print("Error: Audacity.exe not found in standard Windows paths.")
        sys.exit(1)

    # 4. Polish target audio files sequentially (Single Persistent Session)
    EXPORT_WAIT_TIMEOUT_SEC = 900

    owned_process: subprocess.Popen[bytes] | None = None
    preserve_owned_process = False

    def send_owned_command(write_pipe: TextIO, read_pipe: TextIO, command: str, **kwargs: Unpack[CommandOptions]) -> str:
        if owned_process is None:
            _close_pipe_pair(write_pipe, read_pipe)
            raise AudacityReadinessError("Owned Audacity process is unavailable for pipe validation")
        return _send_owned_audacity_command(
            write_pipe, read_pipe, command, expected_pid=owned_process.pid, **kwargs
        )

    def launch_audacity_session() -> tuple[TextIO, TextIO]:
        nonlocal owned_process
        print("  Launching Audacity instance...")
        owned_process = subprocess.Popen([executable_path])
        w_pipe, r_pipe = _open_ready_audacity_session(
            owned_process, executable_path, latest_run
        )
        print("  Audacity Named Pipes connected successfully.")
        print("  Audacity session handshake complete and responsive.")
        return w_pipe, r_pipe

    def terminate_audacity_session(w_pipe: TextIO | None, r_pipe: TextIO | None) -> None:
        nonlocal owned_process
        # Kill process FIRST so FromSrvPipe EOFs and unblocks any reading thread/call without Windows CRT file-lock deadlock
        if owned_process is not None and owned_process.poll() is None:
            owned_process.terminate()
            try:
                owned_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                owned_process.kill()
                owned_process.wait(timeout=5)
        owned_process = None
        try:
            if w_pipe:
                w_pipe.close()
        except Exception:
            pass
        try:
            if r_pipe:
                r_pipe.close()
        except Exception:
            pass

    write_pipe: TextIO | None = None
    read_pipe: TextIO | None = None
    try:
        write_pipe, read_pipe = launch_audacity_session()
    except Exception as e:
        print(f"[ERROR] Failed to start Audacity session: {e}")
        if isinstance(e, AudacityReadinessError):
            print("[REVIEW] Audacity window left open; recovery/dialog state was preserved.")
        else:
            terminate_audacity_session(write_pipe, read_pipe)
        if adaptive:
            raise
        sys.exit(1)

    try:
        for idx, name, base_dir, output_dir in files_to_process:
            if name in polished_files and (not adaptive or probe_audio_file(os.path.join(output_dir, name))):
                print(f"Skipping already polished file: {name}")
                continue

            os.makedirs(output_dir, exist_ok=True)
            raw_audio_path = os.path.join(base_dir, name)
            polished_audio_path = os.path.join(output_dir, name)
            export_path = (
                os.path.join(output_dir, f".{name}.{uuid.uuid4().hex}.pending.wav")
                if adaptive else polished_audio_path
            )

            if not adaptive and os.path.exists(polished_audio_path):
                try:
                    os.remove(polished_audio_path)
                except Exception:
                    pass

            if base_dir == latest_run:
                print(f"\nProcessing Master Track: {name}...")
            else:
                print(f"\nProcessing Chapter {idx}: {name}...")

            clean_import_path = os.path.abspath(raw_audio_path).replace("\\", "\\\\")
            clean_export_path = os.path.abspath(export_path).replace("\\", "\\\\")

            try:
                # 1. Import raw audio
                send_owned_command(
                    write_pipe, read_pipe, f'Import2:Filename="{clean_import_path}"', strict=True
                )

                # 2. Apply preset settings (NoiseGate, TruncateSilence, BassAndTreble, Compressor, Normalize)
                preset_success = apply_preset_file(
                    write_pipe, read_pipe, preset_file_path, strict=True, command_sender=send_owned_command
                )
                if adaptive and not preset_success:
                    raise ValueError("Adaptive Audacity preset contains no executable effects")

                # Fallback if preset file was missing
                if not preset_success:
                    print("  Falling back to internal macro command...")
                    send_owned_command(write_pipe, read_pipe, "SelectAll:", strict=True)
                    send_owned_command(
                        write_pipe, read_pipe, "Macro_YouTube_Voice_Optimizer:", strict=True
                    )

                # 3. Export polished track
                send_owned_command(write_pipe, read_pipe, "SelectAll:", strict=True)
                send_owned_command(
                    write_pipe, read_pipe,
                    f'Export2:Filename="{clean_export_path}" NumChannels=1', strict=True,
                )

                # 4. Wait for exported file to complete
                print(f"  Waiting for Audacity to finish processing and save to {output_dir}...")
                wait_start = time.time()
                while not os.path.exists(export_path):
                    if time.time() - wait_start > EXPORT_WAIT_TIMEOUT_SEC:
                        raise TimeoutError(
                            f"Export never produced '{name}' within {EXPORT_WAIT_TIMEOUT_SEC}s"
                        )
                    time.sleep(0.5)

                last_size = -1
                size_stable_since = time.time()
                while True:
                    try:
                        current_size = os.path.getsize(export_path)
                        if current_size > 0 and current_size == last_size:
                            break
                        if current_size != last_size:
                            last_size = current_size
                            size_stable_since = time.time()
                        elif time.time() - size_stable_since > EXPORT_WAIT_TIMEOUT_SEC:
                            raise TimeoutError(
                                f"'{name}' size never stabilized within {EXPORT_WAIT_TIMEOUT_SEC}s"
                            )
                    except OSError:
                        pass
                    time.sleep(0.5)

                print("  Polished file successfully exported!")
                if adaptive:
                    candidate_probe = probe_audio_file(export_path)
                    if not candidate_probe or candidate_probe["nframes"] <= 0:
                        raise ValueError(f"Audacity exported invalid WAV audio: {name}")
                    from youtube_automation.production.ledger import publication_guard

                    with publication_guard():
                        os.replace(export_path, polished_audio_path)

                # --- OUTPUT SYNC SAFEGUARD ---
                if name == "full_episode_voice.wav" and os.path.exists(polished_audio_path):
                    try:
                        shutil.copy(polished_audio_path, master_track_path)
                        print(
                            f"  [SYNC] Synchronized polished voice track to root: '{master_track_path}'"
                        )
                    except Exception as e:
                        print(f"  [WARNING] Sync copy failed: {e}")

                polished_files.append(name)
                save_checkpoint(latest_run, polished_files)

                # 5. Clear tracks canvas cleanly for the next chapter
                send_owned_command(write_pipe, read_pipe, "SelectAll:", strict=True)
                send_owned_command(write_pipe, read_pipe, "RemoveTracks:", strict=True)

            except TimeoutError as te:
                if adaptive and os.path.exists(export_path):
                    os.remove(export_path)
                if adaptive:
                    raise
                print(f"  [TIMEOUT] {te}")
                print(f"  Skipping '{name}' — it will be retried on the next pipeline resume.")
            except Exception as e:
                if adaptive and os.path.exists(export_path):
                    os.remove(export_path)
                if adaptive:
                    raise
                print(f"  [ERROR] Processing failed for '{name}': {e}")
                print("  Recovering Audacity session for subsequent chapters...")
                terminate_audacity_session(write_pipe, read_pipe)
                try:
                    write_pipe, read_pipe = launch_audacity_session()
                except Exception as rec_err:
                    print(f"  [FATAL] Could not recover Audacity session: {rec_err}")
                    if isinstance(rec_err, AudacityReadinessError):
                        preserve_owned_process = True
                    break
    finally:
        print("  Safely closing Audacity instance...")
        if not preserve_owned_process:
            terminate_audacity_session(write_pipe, read_pipe)

    if adaptive:
        incomplete = [
            name for _idx, name, _base, output in files_to_process
            if name not in polished_files
            or not (probe := probe_audio_file(os.path.join(output, name)))
            or probe["nframes"] <= 0
        ]
        if incomplete:
            raise RuntimeError("Adaptive Audacity left incomplete chapters: " + ", ".join(incomplete))
        expected_names = {name for _idx, name, _base, _output in files_to_process}
        actual_names = {
            name for name in os.listdir(os.path.join(latest_run, "polished_chapters"))
            if re.fullmatch(r"Chapter_\d+\.wav", name)
        }
        if actual_names != expected_names:
            raise RuntimeError("Adaptive polished chapter directory has extra or missing WAVs")
        if validate_adaptive_voice_run(latest_run) != (expected_chapters, expected_recipe):
            raise ValueError("Adaptive source or channel changed during Audacity processing")
    print("\n[SYSTEM] Polishing complete.")
    # Synchronize post-mastered durations to manifests
    try:
        sync_polished_audio_manifest(latest_run, strict=adaptive)
    except Exception as e:
        if adaptive:
            raise
        print(f"  [WARNING] Could not synchronize polished audio manifest: {e}")
    delete_checkpoint(latest_run)

    print("=============================================")
    print("Success! All target audio assets have been polished.")
    print("=============================================")


__all__ = [
    "apply_preset_file",
    "clear_audacity_temp_data",
    "delete_checkpoint",
    "ensure_audacity_script_pipe_enabled",
    "find_preset_file",
    "get_latest_run_folder",
    "load_checkpoint",
    "main",
    "probe_audio_file",
    "save_checkpoint",
    "send_audacity_command",
    "sync_macro_to_audacity",
    "sync_polished_audio_manifest",
]


if __name__ == "__main__":
    main()
