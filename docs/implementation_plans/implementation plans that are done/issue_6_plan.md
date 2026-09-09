### Implementation Plan for Issue 6

**Objective:** Build the foundational Account Switching Framework in a centralized `utils.py` file, and update `script_image_generator.py` and `generate_voice.py` to use it during initialization.

1.  **Create `utils.py`:** We will write a brand-new file containing the parser, the surgical killer, the profile mapper, and a master `launch_chrome_with_profile()` function.
2.  **Update `gemini_model.txt`:** Add `SWITCH_ACCOUNTS_ENABLED=true` and `ACTIVE_PROFILE_INDEX=1` to the config template.
3.  **Refactor Initialization:** In both your image and voice scripts, we will replace the messy Chrome startup blocks with a clean call to our new utility framework.

---

### Part 1: Create `utils.py`

Create a new file named `utils.py` in the same directory as your other scripts, and paste this entire code block into it:

```python
import os
import sys
import time
import subprocess
import urllib.request

def get_config_value(target_key, default_val=""):
    """Reads a KEY=VALUE pair from the shared gemini_model.txt file."""
    config_path = "gemini_model.txt"
    if not os.path.exists(config_path):
        # Auto-create the template if it doesn't exist
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("# Configuration for Gemini Web App Models & Accounts\n")
                f.write("VOICE_GENERATOR_MODEL=Flash-Lite\n")
                f.write("IMAGE_PLANNER_MODEL=Pro\n")
                f.write("IMAGE_RESET_LOOP_LIMIT=20\n")
                f.write("SWITCH_ACCOUNTS_ENABLED=false\n")
                f.write("ACTIVE_PROFILE_INDEX=1\n")
        except Exception:
            pass
        return default_val
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    if key.strip() == target_key:
                        return val.strip()
    except Exception as e:
        print(f"Warning: Could not read {config_path}: {e}")
    return default_val

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

def launch_chrome_with_profile(chrome_path, profile_index, port=9222):
    """Kills existing debug sessions and launches a fresh Chrome with the target profile."""
    profile_dir = map_profile_index(profile_index)
    print(f"\n[SYSTEM] Booting Chrome connected to Account Index {profile_index} ('{profile_dir}')")
    
    # Ensure port is clear
    kill_cdp_chrome(port)
    
    cmd = (
        f'"{chrome_path}" --remote-debugging-port={port} '
        f'--user-data-dir="C:\\ChromeDebugProfile" '
        f'--profile-directory="{profile_dir}" '
        f'--disable-session-crashed-bubble --disable-infobars '
        f'--restore-last-session=false --disable-renderer-backgrounding'
    )
    subprocess.Popen(cmd, shell=True)
    
    # Block and wait for the debugger socket to open
    url = f"http://localhost:{port}/json/version"
    for _ in range(15):
        time.sleep(1)
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    print("[SYSTEM] Chrome debugging session successfully established!")
                    return True
        except Exception:
            continue
            
    print("[ERROR] Chrome failed to start or bind to port 9222.")
    return False
```

---

### Part 2: Integrate `utils.py` into your Scripts

Because we centralized everything, you can now **delete** the old `get_config_model()` functions you pasted into `generate_voice.py` and `script_image_generator.py` earlier.

At the very top of **both** `generate_voice.py` and `script_image_generator.py`, add this import:
```python
from utils import get_config_value, launch_chrome_with_profile
```

Next, in **both scripts**, find where you fetch the model names and update them to use the new `get_config_value` name. 

*Example in `generate_voice.py`:*
```python
    target_llm_model = get_config_value("VOICE_GENERATOR_MODEL", "Flash-Lite")
```

Finally, we update the Chrome connection block. In **both scripts** (around line 655 in the image script, and line 380 in the voice script), you currently have a `try: ... connect_over_cdp ... except: ... Popen ...` block. 

Replace that entire Chrome connection setup block with this infinitely cleaner framework:

```python
        chrome_path = get_chrome_path()
        browser = None
        
        # Issue 6: Multi-Profile Initialization Framework
        switch_enabled_str = get_config_value("SWITCH_ACCOUNTS_ENABLED", "false").lower()
        accounts_enabled = switch_enabled_str in ['true', '1', 'yes']
        current_profile_idx = get_config_value("ACTIVE_PROFILE_INDEX", "1")
        
        try:
            # Try to connect to an existing session first
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            print("Successfully connected to existing Chrome session.")
        except Exception:
            print("Debugging Chrome is closed or unreachable. Launching framework...")
            if not launch_chrome_with_profile(chrome_path, current_profile_idx):
                sys.exit(1)
            browser = p.chromium.connect_over_cdp("http://localhost:9222")

        context = browser.contexts[0]
```

Implement this architecture shift. Run a quick test to ensure the scripts can read from `utils.py`. Once confirmed, we are ready for the grand finale: **Issue 7: Automatic Failover Profile Rotation**!