Here is the structured implementation plan to establish the **Unified Multi-Browser Factory Framework**.

### Implementation Strategy

**Objective:** Abstract the browser launch mechanics so that the user can seamlessly toggle between Google Chrome and Opera GX simply by modifying `BROWSER_TYPE=` in the configuration file, without altering Python code.

**Phase 1: Consolidate `utils.py`**
1. Update the configuration template block to automatically write `BROWSER_TYPE=opera` if the configuration file is missing or newly generated.
2. Inject two private helper functions (`get_chrome_path` and `get_opera_path`) into `utils.py` to dynamically search the Windows filesystem for both executables.
3. Replace the standalone `launch_chrome...` or `launch_opera...` functions with a singular `launch_browser_with_profile(browser_type, profile_index)` function. This function uses boolean logic to assign the correct executable path, display names, and critical isolated debug directories (`ChromeDebugProfile` vs `OperaDebugProfile`) based on the string retrieved from the config file.

**Phase 2: Refactor Worker Scripts**
1. Update the `from utils import...` statement at the top of `script_image_generator.py`, `generate_voice.py`, `script_image_generator_backup.py`, `generate_voice_before_whisper_fixed.py`, and `automate_all.py` to import the unified `launch_browser_with_profile` function.
2. Inside the main recovery loop of each script, fetch the `BROWSER_TYPE` variable from the configuration file.
3. Pass the fetched variable directly into the unified launch function if a CDP connection failure occurs.

---

### Step 1: Execute `utils.py` Refactoring

Open `utils.py`. First, add the new setting to the template inside `get_config_value`:

```python
                f.write("IMAGE_RESET_LOOP_LIMIT=20\n")
                f.write("SWITCH_ACCOUNTS_ENABLED=true\n")
                f.write("ACTIVE_PROFILE_INDEX=1\n")
                f.write("FAILOVER_RETRY_LIMIT=3\n")
                f.write("BROWSER_TYPE=opera\n") # <-- NEW: Accepts 'chrome' or 'opera'
```

Next, locate and **delete** any existing `get_opera_path()`, `get_chrome_path()`, `launch_chrome_with_profile()`, or `launch_opera_with_profile()` functions in `utils.py`.

**Paste this unified Factory Block at the bottom of `utils.py`:**

```python
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
            import urllib.request
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    print(f"[SYSTEM] {browser_name} debugging session successfully established!")
                    return True
        except Exception:
            continue
            
    print(f"[ERROR] {browser_name} failed to start or bind to port {port}.")
    return False
```

---

### Step 2: Refactor Worker Scripts
*(Execute this step inside `automate_all.py`, `generate_voice.py`, `script_image_generator_backup.py`, `generate_voice_before_whisper_fixed.py`,and `script_image_generator.py`)*

**1. Update Imports:**
Replace your old imports at the top of the file with:
```python
from utils import get_config_value, launch_browser_with_profile, rotate_profile_index, kill_cdp_chrome
```

*(Note: Also make sure you delete any leftover `def get_opera_path()` or `def get_chrome_path()` that might still exist inside these worker scripts, as `utils.py` handles them now.)*

**2. Update Connection Block in `main()`:**
Locate the `while True:` failover loop and Playwright initialization block. Replace it with this dynamic integration:

```python
        # The Outer Recovery Loop
        while True:
            failover_triggered = False
            
            try:
                with sync_playwright() as p:
                    # Issue 6/7: Multi-Profile & Multi-Browser Framework
                    switch_enabled_str = get_config_value("SWITCH_ACCOUNTS_ENABLED", "false").lower()
                    accounts_enabled = switch_enabled_str in ['true', '1', 'yes']
                    current_profile_idx = get_config_value("ACTIVE_PROFILE_INDEX", "1")
                    
                    # NEW: Fetch browser type dynamically from config
                    browser_type = get_config_value("BROWSER_TYPE", "chrome")
                    
                    try:
                        # Attempt to connect to an existing running session
                        browser = p.chromium.connect_over_cdp("http://localhost:9222")
                        print(f"Successfully connected to existing {browser_type.capitalize()} session.")
                    except Exception:
                        print(f"Debugging browser is closed or unreachable. Launching framework...")
                        # Call the unified launcher
                        if not launch_browser_with_profile(browser_type, current_profile_idx):
                            sys.exit(1)
                        browser = p.chromium.connect_over_cdp("http://localhost:9222")

                    context = browser.contexts[0]
```

### Final Activation Step
Open your `gemini_model.txt` file manually on your hard drive and add the line `BROWSER_TYPE=opera` (or `BROWSER_TYPE=chrome`).