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

from dotenv import load_dotenv


# Locate and load the .env file from the project root directory with override enabled
def _find_project_root() -> str:
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists() or (parent / ".env").exists():
            return str(parent)
    return str(Path(__file__).resolve().parents[3])

PROJECT_ROOT = _find_project_root()
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(ENV_PATH, override=True)

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


def update_config_value(target_key, new_val):
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


def atomic_write_json(path: str, payload, *, ensure_ascii: bool = False, indent: int = 4) -> None:
    """Crash-safe JSON write: temp file in the target dir -> fsync -> os.replace."""
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


def kill_cdp_chrome(port: int | str = 9222):
    """Surgically terminates Chrome/Opera listening on the CDP port without shell=True execution."""
    port = int(port)
    killed_any = False
    if os.name == "nt":
        try:
            # Query TCP table directly without shell pipelines
            proc = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, check=False
            )
            killed_pids = set()
            for line in proc.stdout.strip().splitlines():
                parts = line.strip().split()
                if (
                    len(parts) >= 5
                    and parts[0].upper() == "TCP"
                    and parts[1].rsplit(":", 1)[-1] == str(port)
                    and parts[3].upper() == "LISTENING"
                ):
                    pid = parts[4]
                    # Strict PID validation: must be digits only and > 100 (avoid system criticals)
                    if pid.isdigit():
                        pid_int = int(pid)
                        if pid_int > 100 and pid not in killed_pids:
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", str(pid_int)],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                check=False,
                            )
                            killed_pids.add(pid)
                            killed_any = True
                            logger.info(
                                f"[SYSTEM] Terminated CDP process (PID: {pid_int}) on port {port}."
                            )
        except Exception as e:
            logger.warning(f"[WARN] Non-shell process termination encountered an issue: {e}")
    else:
        try:
            subprocess.run(
                ["fuser", "-k", f"{port}/tcp"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            killed_any = True
        except Exception:
            pass

    # Socket-polling verification loop (up to 4s) to ensure OS socket release
    if killed_any or is_port_in_use(port):
        for _ in range(8):
            if not is_port_in_use(port):
                break
            time.sleep(0.5)


def map_profile_index(num_str):
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


def get_chrome_path():
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


def get_opera_path():
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


def launch_browser_with_profile(browser_type, profile_index, port=None):
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

    # Clear the port prior to launching
    kill_cdp_chrome(port)

    # Deep recursive lock cleaning across root and target profile directory
    target_dirs = [user_data_dir, os.path.join(user_data_dir, profile_dir)]
    for d in target_dirs:
        if os.path.exists(d):
            for lock_file in [
                "SingletonLock",
                "SingletonSocket",
                "SingletonCookie",
                "lockfile",
                "Preferences.bad",
            ]:
                lock_path = os.path.join(d, lock_file)
                if os.path.exists(lock_path):
                    try:
                        os.remove(lock_path)
                    except Exception:
                        pass

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
        "--host-resolver-rules=MAP aistudio.google.com 142.251.154.2",
        "--no-first-run",
        "--no-default-browser-check",
        "--hide-crash-restore-bubble",
    ]
    subprocess.Popen(cmd)

    # Blocking loop to ensure debugger socket is open (explicit IPv4 to prevent IPv6 ::1 lookup failure)
    url = f"http://127.0.0.1:{port}/json/version"
    for _ in range(15):
        time.sleep(1)
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    logger.info(
                        f"[SYSTEM] {browser_name} debugging session successfully established!"
                    )
                    return True
        except Exception:
            continue

    logger.error(f"[ERROR] {browser_name} failed to start or bind to port {port}.")
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


def _dispatch_telegram(bot_token, chat_id, message):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message}, ensure_ascii=False).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=4):
            pass
    except Exception as e:
        logger.warning(f"[WARNING] Async Telegram notification failed: {e}")


def send_telegram_notification(message):
    """Sends a non-blocking push notification to Telegram in a background worker thread."""
    bot_token = get_config_value("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = get_config_value("TELEGRAM_CHAT_ID", "").strip()

    if not bot_token or not chat_id:
        return

    # Fire and detach thread so pipeline never hangs on network latency
    t = threading.Thread(target=_dispatch_telegram, args=(bot_token, chat_id, message), daemon=True)
    t.start()
