import os
import sys
import time
import subprocess
import urllib.request
from dotenv import load_dotenv

# Locate and load the .env file from the project root directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(ENV_PATH)

def get_config_value(target_key, default_val=""):
    """Reads a KEY=VALUE pair from environment variables (.env)."""
    val = os.getenv(target_key)
    if val is not None:
        print(f"[DEBUG PARSER] Match found in .env! key='{target_key}' -> value='{val.strip()}'")
        return val.strip()
    return default_val

def update_config_value(target_key, new_val):
    """Updates or adds a specific KEY=VALUE pair in the local .env file and syncs active memory."""
    # Update active environment in memory so subsequent get_config_value reads see it instantly
    os.environ[target_key] = str(new_val)
    
    lines = []
    key_found = False
    
    # Read the existing .env file
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    # Write the updated value back to the .env file
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        for line in lines:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, _ = line.split("=", 1)
                if key.strip() == target_key:
                    f.write(f"{target_key}={new_val}\n")
                    key_found = True
                    continue
            f.write(line)
        if not key_found:
            f.write(f"{target_key}={new_val}\n")
    print(f"[SYSTEM] Successfully updated config variable: {target_key} -> {new_val}")

def kill_cdp_chrome(port=9222):
    """Surgically kills only the Chrome process listening on the CDP port."""
    if os.name == 'nt':
        cmd = f"netstat -ano | findstr :{port}"
        try:
            lines = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')
            for line in lines:
                if 'LISTENING' in line:
                    pid = line.strip().split()[-1]
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(f"Killed CDP Chrome process (PID: {pid}) on port {port}.")
                    time.sleep(2)  # CRITICAL: Wait for the OS to free the TCP socket
        except Exception:
            pass

def map_profile_index(num_str):
    """Maps a human numeric index to Chrome's native Profile directory names."""
    try:
        num = int(str(num_str).strip())
        if num <= 1:
            return "Default"
        else:
            return f"Profile {num - 1}"
    except ValueError:
        return "Default"

def get_chrome_path():
    """Dynamically locates Google Chrome executable on Windows."""
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    return next((p for p in paths if os.path.exists(p)), None)

def get_opera_path():
    """Dynamically locates Opera or Opera GX executable on Windows."""
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    paths = [
        os.path.join(local_app_data, r"Programs\Opera\opera.exe"),
        os.path.join(local_app_data, r"Programs\Opera\launcher.exe"),
        os.path.join(local_app_data, r"Programs\Opera GX\opera.exe"),
        os.path.join(local_app_data, r"Programs\Opera GX\launcher.exe"),
        r"C:\Program Files\Opera\opera.exe",
        r"C:\Program Files\Opera GX\opera.exe"
    ]
    return next((p for p in paths if os.path.exists(p)), None)

def launch_browser_with_profile(browser_type, profile_index, port=9222):
    """Dynamically launches Chrome or Opera based on configuration."""
    print(f"[SYSTEM DIAGNOSTIC] Launching with browser_type='{browser_type}' (Account index: {profile_index})")
    profile_dir = map_profile_index(profile_index)
    is_opera = "opera" in browser_type.lower()
    
    # Dynamic assignments based on browser selection
    browser_name = "Opera" if is_opera else "Chrome"
    exe_path = get_opera_path() if is_opera else get_chrome_path()
    user_data_dir = r"C:\OperaDebugProfile" if is_opera else r"C:\ChromeDebugProfile"

    if not exe_path:
        print(f"[FATAL ERROR] {browser_name} executable not found. Please check installation paths.")
        sys.exit(1)

    print(f"\n[SYSTEM] Booting {browser_name} connected to Account Index {profile_index} ('{profile_dir}')")
    
    # Clear the port prior to launching
    kill_cdp_chrome(port)
    
    cmd = (
        f'"{exe_path}" --remote-debugging-port={port} '
        f'--user-data-dir="{user_data_dir}" '
        f'--profile-directory="{profile_dir}" '
        f'--disable-session-crashed-bubble --disable-infobars '
        f'--restore-last-session=false --disable-renderer-backgrounding'
    )
    subprocess.Popen(cmd, shell=True)
    
    # Blocking loop to ensure debugger socket is open
    url = f"http://localhost:{port}/json/version"
    for _ in range(15):
        time.sleep(1)
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    print(f"[SYSTEM] {browser_name} debugging session successfully established!")
                    return True
        except Exception:
            continue
            
    print(f"[ERROR] {browser_name} failed to start or bind to port {port}.")
    return False

def rotate_profile_index():
    """Increments the active profile index in the config and returns the new index."""
    current_idx = int(get_config_value("ACTIVE_PROFILE_INDEX", "1"))
    new_idx = current_idx + 1
    update_config_value("ACTIVE_PROFILE_INDEX", str(new_idx))
    
    print(f"\n[FAILOVER SYSTEM] Rotated ACTIVE_PROFILE_INDEX from {current_idx} to {new_idx} in config.")
    
    # Fire Telegram Alert
    send_telegram_notification(f"⚠️ [Alert] Account {current_idx} failed/blocked. Rotated to Account {new_idx} successfully.")
    
    return new_idx

def send_telegram_notification(message):
    """Sends a push notification to your phone via Telegram."""
    bot_token = get_config_value("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = get_config_value("TELEGRAM_CHAT_ID", "").strip()
    
    # Skip if the user hasn't set up the keys yet
    if not bot_token or not chat_id:
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    import json
    data = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    
    try:
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=5):
            pass # Success
    except Exception as e:
        print(f"[WARNING] Could not send Telegram notification: {e}")