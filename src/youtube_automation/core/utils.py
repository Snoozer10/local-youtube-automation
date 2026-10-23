import json
import logging
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from dotenv import load_dotenv


# Locate project defaults without replacing explicit process-level configuration.
def _find_project_root() -> str:
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists() or (parent / ".env").exists():
            return str(parent)
    return str(Path(__file__).resolve().parents[3])

PROJECT_ROOT = _find_project_root()
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(ENV_PATH, override=False)

# Configure logging
LOG_DIR = Path(PROJECT_ROOT) / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "pipeline.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)

logger = logging.getLogger("Pipeline")


@dataclass(frozen=True)
class PipelineConfig:
    """Centralized typed configuration for the refinement pipeline."""

    cdp_port: int = 9222
    browser_type: str = "chrome"
    model_name: str = "Pro"
    timeout_seconds: int = 420
    max_retries: int = 4
    switch_accounts: bool = False

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        """Load configuration from environment variables."""
        return cls(
            cdp_port=int(get_config_value("CDP_PORT", "9222")),
            browser_type=get_config_value("BROWSER_TYPE", "chrome"),
            model_name=get_config_value("REFINE_MODEL", "Pro"),
            timeout_seconds=int(get_config_value("REFINE_PARAGRAPH_TIMEOUT", "420")),
            max_retries=int(get_config_value("FAILOVER_RETRY_LIMIT", "4")),
            switch_accounts=get_config_value("SWITCH_ACCOUNTS_ENABLED", "false").lower()
            in ("true", "1", "yes"),
        )


# Global config instance is materialized after get_config_value is defined
# (fix: module-level call previously raised NameError at import time).


def get_config_value(target_key: str, default_val: str = "") -> str:
    """Reads a KEY=VALUE pair from environment variables (.env), stripping accidental quotes."""
    val = os.getenv(target_key)
    if val is not None:
        cleaned = val.strip()
        # Strip wrapping single or double quotes
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (
            cleaned.startswith("'") and cleaned.endswith("'")
        ):
            cleaned = cleaned[1:-1].strip()
        return cleaned
    return default_val


# Global config instance
CONFIG = PipelineConfig.from_env()


def update_config_value(target_key: str, new_val: str | int | float | bool) -> None:
    """Atomically updates or adds a specific KEY=VALUE pair in .env and syncs active memory."""
    os.environ[target_key] = str(new_val)
    lines = []
    key_found = False

    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            lines = []

    new_lines = []
    for line in lines:
        if line.strip() and not line.startswith("#") and "=" in line:
            key, _ = line.split("=", 1)
            if key.strip() == target_key:
                new_lines.append(f"{target_key}={new_val}\n")
                key_found = True
                continue
        new_lines.append(line)

    if not key_found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{target_key}={new_val}\n")

    target_dir = os.path.dirname(os.path.abspath(ENV_PATH)) or "."
    tf = tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8")
    try:
        tf.writelines(new_lines)
        tf.flush()
        os.fsync(tf.fileno())
        temp_name = tf.name
    finally:
        tf.close()
    os.replace(temp_name, ENV_PATH)
    logger.info(f"[SYSTEM] Successfully updated config variable: {target_key} -> {new_val}")


def atomic_write_json(path: str, payload: Any, *, ensure_ascii: bool = False, indent: int = 4) -> None:
    """Crash-safe JSON write: temp file in the target dir -> fsync -> os.replace.

    Payload is the stdlib JSON serialization boundary; unsupported values raise.
    """
    directory = os.path.dirname(path) or "."
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=directory, delete=False, encoding="utf-8", suffix=".tmp"
        ) as tf:
            tmp_path = tf.name
            json.dump(payload, tf, ensure_ascii=ensure_ascii, indent=indent)
            tf.flush()
            os.fsync(tf.fileno())
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def is_port_in_use(port: int | str) -> bool:
    """Checks if a local TCP port is actively occupied."""
    port_num = int(port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port_num)) == 0


class _BrowserFacts(TypedDict):
    pid: int
    creation_time: float
    executable: str
    cmdline: list[str]


class _OwnedBrowserRecord(TypedDict):
    pid: int
    creation_time: float
    executable: str
    user_data_dir: str
    profile: str
    started_at: float


OWNED_BROWSER_REGISTRY = Path(PROJECT_ROOT) / ".runtime" / "owned_browsers.json"


def _read_owned_browsers() -> dict[str, Any]:
    # Registry bytes are untrusted JSON; identity guards validate each record before use.
    try:
        value = json.loads(OWNED_BROWSER_REGISTRY.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _write_owned_browsers(value: dict[str, _OwnedBrowserRecord]) -> None:
    OWNED_BROWSER_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(str(OWNED_BROWSER_REGISTRY), value)


def _listener_pids(port: int) -> set[int]:
    if os.name != "nt":
        return set()
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    found: set[int] = set()
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if (
            len(parts) >= 5
            and parts[0].upper() == "TCP"
            and parts[1].rsplit(":", 1)[-1] == str(port)
            and parts[3].upper() == "LISTENING"
            and parts[4].isdigit()
        ):
            found.add(int(parts[4]))
    return found


def _browser_process_facts(pid: int) -> _BrowserFacts:
    """Return process identity fields needed to prove pipeline ownership."""
    import psutil

    process = psutil.Process(pid)
    with process.oneshot():
        return {
            "pid": process.pid,
            "creation_time": process.create_time(),
            "executable": process.exe(),
            "cmdline": process.cmdline(),
        }


def _normalized_browser_path(value: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(value)))


def _browser_facts_match(facts: _BrowserFacts, executable: str, user_data_dir: str, profile: str) -> bool:
    if type(facts.get("pid")) is not int or facts["pid"] <= 0:
        return False
    creation_time = facts.get("creation_time")
    if isinstance(creation_time, bool) or not isinstance(creation_time, (int, float)):
        return False
    if not isinstance(facts.get("executable"), str):
        return False
    if _normalized_browser_path(facts["executable"]) != _normalized_browser_path(executable):
        return False
    command_line = facts.get("cmdline")
    if not isinstance(command_line, (list, tuple)):
        return False
    user_data_values = [
        arg.split("=", 1)[1]
        for arg in command_line
        if isinstance(arg, str) and arg.startswith("--user-data-dir=")
    ]
    profile_values = [
        arg.split("=", 1)[1]
        for arg in command_line
        if isinstance(arg, str) and arg.startswith("--profile-directory=")
    ]
    return (
        len(user_data_values) == 1
        and _normalized_browser_path(user_data_values[0])
        == _normalized_browser_path(user_data_dir)
        and len(profile_values) == 1
        and os.path.normcase(profile_values[0]) == os.path.normcase(profile)
    )


def _owned_browser_is_current(record: dict[str, Any], port: int) -> bool:
    # The caller supplies a JSON registry row; this guard establishes its identity contract.
    pid = record.get("pid")
    creation_time = record.get("creation_time")
    if type(pid) is not int or pid <= 0:
        return False
    if isinstance(creation_time, bool) or not isinstance(creation_time, (int, float)):
        return False
    if not all(isinstance(record.get(key), str) and record[key] for key in ("executable", "user_data_dir", "profile")):
        return False
    if _listener_pids(port) != {pid}:
        return False
    facts = _browser_process_facts(pid)
    return (
        facts.get("pid") == pid
        and facts.get("creation_time") == creation_time
        and _browser_facts_match(
            facts, record["executable"], record["user_data_dir"], record["profile"]
        )
    )


def kill_cdp_chrome(port: int | str = 9222) -> bool:
    """Terminate only a currently verified PID and profile recorded by this workspace."""
    port = int(port)
    registry = _read_owned_browsers()
    record = registry.get(str(port))
    if not isinstance(record, dict):
        if is_port_in_use(port):
            logger.warning(
                f"[OWNERSHIP] Refusing to terminate unregistered browser on CDP port {port}."
            )
        return False

    pid = record.get("pid")
    try:
        # Legacy records without creation time or launch arguments fail closed.
        if not _owned_browser_is_current(record, port):
            logger.warning(
                f"[OWNERSHIP] Refusing to terminate browser with unverified identity on CDP port {port}."
            )
            return False
        # Re-read identity and listener immediately before acting to reduce PID-reuse races.
        if not _owned_browser_is_current(record, port):
            logger.warning(
                f"[OWNERSHIP] Browser identity changed before termination on CDP port {port}."
            )
            return False
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            )
            if result.returncode != 0:
                return False
        else:
            import psutil

            process = psutil.Process(pid)
            if process.create_time() != record["creation_time"]:
                return False
            process.terminate()
        for _ in range(8):
            if not is_port_in_use(port):
                registry.pop(str(port), None)
                _write_owned_browsers(registry)
                logger.info(f"[SYSTEM] Terminated owned CDP process PID {pid} on port {port}.")
                return True
            time.sleep(0.5)
    except Exception as exc:
        logger.warning(f"[WARN] Owned browser termination failed: {exc}")
    return False


def map_profile_index(num_str: str | int) -> str:
    """Maps a human numeric index or explicit directory name to Chrome's native Profile directory names."""
    raw = str(num_str).strip()
    if raw.startswith("Profile ") or raw == "Default":
        return raw
    try:
        num = int(raw)
        if num <= 1:
            return "Default"
        else:
            return f"Profile {num - 1}"
    except ValueError:
        return "Default"


def get_chrome_path() -> str | None:
    """Dynamically locates Google Chrome executable on Windows across system and user paths."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

    paths = [
        os.path.join(program_files, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(program_files_x86, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(local_app_data, r"Google\Chrome\Application\chrome.exe"),
    ]
    return next((p for p in paths if p and os.path.exists(p)), None)


def get_opera_path() -> str | None:
    """Dynamically locates Opera or Opera GX executable on Windows."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    paths = [
        os.path.join(local_app_data, r"Programs\Opera\opera.exe"),
        os.path.join(local_app_data, r"Programs\Opera\launcher.exe"),
        os.path.join(local_app_data, r"Programs\Opera GX\opera.exe"),
        os.path.join(local_app_data, r"Programs\Opera GX\launcher.exe"),
        r"C:\Program Files\Opera\opera.exe",
        r"C:\Program Files\Opera GX\opera.exe",
    ]
    return next((p for p in paths if os.path.exists(p)), None)


def launch_browser_with_profile(
    browser_type: str, profile_index: str | int, port: int | None = None,
) -> bool:
    if port is None:
        port = int(get_config_value("CDP_PORT", "9222"))

    logger.info(
        f"[SYSTEM DIAGNOSTIC] Launching with browser_type='{browser_type}' (Account index: {profile_index})"
    )
    profile_dir = map_profile_index(profile_index)
    is_opera = "opera" in browser_type.lower()

    # Dynamic assignments based on browser selection and .env overrides
    browser_name = "Opera" if is_opera else "Chrome"
    exe_path = get_opera_path() if is_opera else get_chrome_path()
    default_dir = r"C:\OperaDebugProfile" if is_opera else r"C:\ChromeDebugProfile"
    env_dir_key = "OPERA_USER_DATA_DIR" if is_opera else "CHROME_USER_DATA_DIR"
    user_data_dir = get_config_value(env_dir_key, default_dir)

    if not exe_path:
        logger.critical(
            f"[FATAL ERROR] {browser_name} executable not found. Please check installation paths."
        )
        sys.exit(1)

    logger.info(
        f"[SYSTEM] Booting {browser_name} connected to Account Index {profile_index} ('{profile_dir}')"
    )

    # Replace only a previously verified owned browser; never seize an unrelated listener.
    if is_port_in_use(port) and not kill_cdp_chrome(port):
        logger.error(
            f"[OWNERSHIP] CDP port {port} is occupied by an unowned browser; refusing replacement."
        )
        return False

    cmd = [
        exe_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        f"--profile-directory={profile_dir}",
        "--disable-session-crashed-bubble",
        "--disable-infobars",
        "--restore-last-session=false",
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
        "--disable-background-media-suspend",
        "--disable-quic",
        "--no-first-run",
        "--no-default-browser-check",
        "--hide-crash-restore-bubble",
    ]
    process = subprocess.Popen(cmd)

    def reject_launch(reason: str) -> bool:
        if process.poll() is None:
            process.terminate()
        logger.error(f"[OWNERSHIP] Refusing browser launch on CDP port {port}: {reason}.")
        return False

    url = f"http://127.0.0.1:{port}/json/version"
    last_transport_error: urllib.error.URLError | ConnectionRefusedError | TimeoutError | None = None
    for _ in range(15):
        time.sleep(1)
        try:
            response_context = urllib.request.urlopen(url, timeout=1)
        except urllib.error.URLError as exc:
            if isinstance(exc, urllib.error.HTTPError) or not isinstance(
                exc.reason, (ConnectionRefusedError, TimeoutError)
            ):
                return reject_launch(f"ownership verification failed ({type(exc).__name__})")
            last_transport_error = exc
            continue
        except (ConnectionRefusedError, TimeoutError) as exc:
            last_transport_error = exc
            continue
        except Exception as exc:
            return reject_launch(f"ownership verification failed ({type(exc).__name__})")

        try:
            with response_context as response:
                if response.status != 200:
                    return reject_launch(f"unexpected CDP status {response.status}")
                try:
                    payload = json.loads(response.read())
                except Exception as exc:
                    return reject_launch(f"invalid CDP version response ({type(exc).__name__})")
                websocket_url = payload.get("webSocketDebuggerUrl") if isinstance(payload, dict) else None
                browser_version = payload.get("Browser") if isinstance(payload, dict) else None
                websocket_prefix = f"ws://127.0.0.1:{port}/devtools/browser/"
                if (
                    not isinstance(browser_version, str)
                    or not browser_version
                    or not isinstance(websocket_url, str)
                    or not websocket_url.startswith(websocket_prefix)
                    or not websocket_url[len(websocket_prefix):]
                ):
                    return reject_launch("CDP version response schema is invalid")
                expected_pid = process.pid
                if _listener_pids(int(port)) != {expected_pid}:
                    return reject_launch("listener PID does not exactly match launched PID")
                facts = _browser_process_facts(expected_pid)
                if not _browser_facts_match(facts, exe_path, user_data_dir, profile_dir):
                    return reject_launch("process image or browser profile does not match launch")
                if facts.get("pid") != expected_pid:
                    return reject_launch("process identity changed after launch")
                # Recheck both sides immediately before registering ownership.
                if _listener_pids(int(port)) != {expected_pid}:
                    return reject_launch("listener changed during ownership verification")
                final_facts = _browser_process_facts(expected_pid)
                if (
                    final_facts.get("pid") != expected_pid
                    or final_facts.get("creation_time") != facts.get("creation_time")
                    or not _browser_facts_match(final_facts, exe_path, user_data_dir, profile_dir)
                ):
                    return reject_launch("process identity changed during ownership verification")
                if isinstance(final_facts.get("creation_time"), bool) or not isinstance(
                    final_facts.get("creation_time"), (int, float)
                ):
                    return reject_launch("process creation time is unavailable")
                registry = _read_owned_browsers()
                registry[str(int(port))] = {
                    "pid": expected_pid,
                    "creation_time": final_facts["creation_time"],
                    "executable": _normalized_browser_path(final_facts["executable"]),
                    "user_data_dir": _normalized_browser_path(user_data_dir),
                    "profile": profile_dir,
                    "started_at": time.time(),
                }
                _write_owned_browsers(registry)
                logger.info(
                    f"[SYSTEM] {browser_name} debugging session successfully established!"
                )
                return True
        except Exception as exc:
            return reject_launch(f"ownership verification failed ({type(exc).__name__})")

    if last_transport_error is not None:
        return reject_launch(
            f"CDP endpoint did not become ready after 15 observations ({type(last_transport_error).__name__})"
        )
    logger.error(f"[ERROR] {browser_name} failed to start or bind to port {port}.")
    if process.poll() is None:
        process.terminate()
    return False


STATE_FILE = "runtime_state.json"


def get_runtime_state(key: str, default: str = "") -> str:
    """Reads dynamic execution state from a separate JSON store rather than mutating .env."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
                return str(data.get(key, default))
        except Exception:
            pass
    return get_config_value(key, default)


def set_runtime_state(key: str, value: str) -> None:
    """Atomically persists dynamic execution state to JSON store without Windows file lock errors."""
    data = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data[key] = value
    target_dir = os.path.dirname(os.path.abspath(STATE_FILE)) or "."
    tf = tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8")
    try:
        json.dump(data, tf, ensure_ascii=False, indent=2)
        tf.flush()
        os.fsync(tf.fileno())
        temp_name = tf.name
    finally:
        tf.close()
    os.replace(temp_name, STATE_FILE)


def rotate_profile_index() -> int:
    """Increments the active profile index in runtime state and fires alerts."""
    raw = get_runtime_state("ACTIVE_PROFILE_INDEX", "1")
    match = re.search(r"\d+", str(raw))
    current_idx = int(match.group(0)) if match else 1
    new_idx = current_idx + 1
    if new_idx > 5:
        new_idx = 2
    new_val = f"Profile {new_idx}" if str(raw).strip().startswith("Profile ") else str(new_idx)
    set_runtime_state("ACTIVE_PROFILE_INDEX", new_val)

    logger.warning(
        f"[FAILOVER SYSTEM] Rotated ACTIVE_PROFILE_INDEX from {current_idx} to {new_idx} in runtime state."
    )
    send_telegram_notification(
        f"⚠️ [Alert] Account {current_idx} failed/blocked. Rotated to Account {new_idx} successfully."
    )
    return new_idx


def active_profile_index() -> int:
    """Return the normalized numeric index for the active browser profile."""
    raw = get_runtime_state("ACTIVE_PROFILE_INDEX", "1")
    match = re.search(r"\d+", str(raw))
    return max(1, int(match.group(0))) if match else 1


def next_profile_index(current: str | int | None = None) -> int:
    """Return the next configured account index using the established failover ring."""
    if current is None:
        current_idx = active_profile_index()
    else:
        match = re.search(r"\d+", str(current))
        current_idx = max(1, int(match.group(0))) if match else 1
    target = current_idx + 1
    return 2 if target > 5 else target


def failover_owned_browser_profile() -> int:
    """Switch from an exhausted account to the next verified owned CDP profile."""
    current_idx = active_profile_index()
    target_idx = next_profile_index(current_idx)
    if not switch_owned_browser_profile(target_idx):
        raise RuntimeError(
            f"Could not switch the owned CDP browser from account {current_idx} "
            f"to account {target_idx} after Gemini quota exhaustion"
        )
    logger.warning(
        f"[FAILOVER SYSTEM] Gemini quota exhausted on account {current_idx}; "
        f"verified account {target_idx} and committed it as active."
    )
    send_telegram_notification(
        f"⚠️ [Alert] Gemini quota exhausted on Account {current_idx}. "
        f"Switched to verified Account {target_idx}."
    )
    return target_idx


def switch_owned_browser_profile(
    target_profile_index: str | int,
    *,
    browser_type: str | None = None,
    port: int | None = None,
) -> bool:
    """Switch the pipeline-owned CDP browser and commit state only after verification.

    This is an operator-directed capacity switch, so it deliberately emits no failover
    notification and never labels the previous account as failed.
    """
    cdp_port = int(port or get_config_value("CDP_PORT", "9222"))
    browser = browser_type or get_config_value("BROWSER_TYPE", "chrome")
    previous = get_runtime_state("ACTIVE_PROFILE_INDEX", "1")
    target = str(target_profile_index).strip()
    expected_profile = map_profile_index(target)
    registry = _read_owned_browsers()
    prior_record = registry.get(str(cdp_port))
    had_owned_listener = bool(prior_record and is_port_in_use(cdp_port))

    if is_port_in_use(cdp_port) and not kill_cdp_chrome(cdp_port):
        logger.error(
            f"[OWNERSHIP] Refusing profile switch because CDP port {cdp_port} is not owned."
        )
        return False

    if launch_browser_with_profile(browser, target, cdp_port):
        active = _read_owned_browsers().get(str(cdp_port), {})
        if active.get("profile") == expected_profile and is_port_in_use(cdp_port):
            set_runtime_state("ACTIVE_PROFILE_INDEX", target)
            logger.info(
                f"[SYSTEM] Switched owned browser from account {previous} to {target} "
                f"({expected_profile})."
            )
            return True
        kill_cdp_chrome(cdp_port)

    logger.error(
        f"[ERROR] Could not verify account {target} ({expected_profile}); runtime state remains {previous}."
    )
    if had_owned_listener:
        launch_browser_with_profile(browser, previous, cdp_port)
    return False


def _dispatch_telegram(bot_token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message}, ensure_ascii=False).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=4):
            pass
    except Exception as e:
        logger.warning(f"[WARNING] Async Telegram notification failed: {e}")


def send_telegram_notification(message: str) -> None:
    """Sends a non-blocking push notification to Telegram in a background worker thread."""
    bot_token = get_config_value("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = get_config_value("TELEGRAM_CHAT_ID", "").strip()

    if not bot_token or not chat_id:
        return

    # Fire and detach thread so pipeline never hangs on network latency
    t = threading.Thread(target=_dispatch_telegram, args=(bot_token, chat_id, message), daemon=True)
    t.start()
