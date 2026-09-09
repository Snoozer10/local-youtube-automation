This is the grand finale. Issue 7 connects all the pieces we have built into a fully autonomous, self-healing pipeline.

### Architectural Analysis & Strategy for Issue 7

When a script fails 3 times and needs to switch accounts, we face a major technical challenge: **Playwright Context Death**. If we kill Chrome to swap the profile directory, all of Playwright's internal objects (`browser`, `context`, `page`) become instantly invalid and will throw detached connection errors if we try to keep using them in the current loop.

**The Solution: The "Idempotent Outer Recovery Loop"**
Instead of writing complex code to dynamically rebuild pages and tabs mid-stream, we will exploit a brilliant feature of your existing code: **Your scripts are already idempotent.** 
Because you implemented `voice_checkpoint.json` and file-size checks (`if os.path.exists(save_path)...`), your scripts know exactly where to resume. 

We will wrap the entire Playwright execution block inside an outer `while True:` loop. If a failover triggers, we simply:
1. Update the config file to the next profile index.
2. Kill Chrome.
3. `break` the inner loops, allowing the `with sync_playwright() as p:` context to naturally close.
4. Let the `while True:` loop restart the script from the top. It will boot the new profile, instantly "fast-forward" past all completed files, and resume exactly at the failure point!

### Here is the implementation plan.

---

### Step 1: Upgrade `utils.py`

We need to add the ability to *write* to the config file to update the profile index, and define the retry limit.

1. Open `utils.py`. Find the template generation block inside `get_config_value` and add the retry limit so it looks like this:
```python
                f.write("IMAGE_RESET_LOOP_LIMIT=20\n")
                f.write("SWITCH_ACCOUNTS_ENABLED=true\n")
                f.write("ACTIVE_PROFILE_INDEX=1\n")
                f.write("FAILOVER_RETRY_LIMIT=3\n") # <-- NEW
```

2. Add these two new functions at the bottom of `utils.py`:
```python
def update_config_value(target_key, new_val):
    """Updates a specific KEY=VALUE pair in gemini_model.txt."""
    config_path = "gemini_model.txt"
    lines = []
    key_found = False
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    with open(config_path, "w", encoding="utf-8") as f:
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

def rotate_profile_index():
    """Increments the active profile index in the config and returns the new index."""
    current_idx = int(get_config_value("ACTIVE_PROFILE_INDEX", "1"))
    new_idx = current_idx + 1
    update_config_value("ACTIVE_PROFILE_INDEX", str(new_idx))
    print(f"\n[FAILOVER SYSTEM] Rotated ACTIVE_PROFILE_INDEX from {current_idx} to {new_idx} in config.")
    return new_idx
```

---

### Step 2: Implement Failover in `script_image_generator.py`

At the top of the file, update your import to include the new functions:
```python
from utils import get_config_value, launch_chrome_with_profile, rotate_profile_index, kill_cdp_chrome
```

Now, locate the `def main():` function. We are going to wrap the Playwright block in the outer recovery loop.

**Change the top of `main()` to look like this:**
```python
def main():
    batch_queue = scan_batch_folders()
    if not batch_queue:
        print("No active topic directories... exiting.")
        return
        
    chrome_path = get_chrome_path()

    # NEW: The Outer Recovery Loop
    while True:
        failover_triggered = False
        
        try:
            with sync_playwright() as p:
                # Issue 6: Multi-Profile Initialization Framework
                switch_enabled_str = get_config_value("SWITCH_ACCOUNTS_ENABLED", "false").lower()
                accounts_enabled = switch_enabled_str in ['true', '1', 'yes']
                current_profile_idx = get_config_value("ACTIVE_PROFILE_INDEX", "1")
                # ... (rest of your connection logic remains the same)
```

Now, scroll down to the bottom of the generation loop (around line 935), right where it says `if not success: print(f"Error: Frame {idx} failed completely...")`.

**Replace that specific failure block with this failover logic:**
```python
                if not success:
                    if accounts_enabled:
                        print(f"\n[FAILOVER ALERT] Frame {idx} failed completely. Triggering Account Rotation...")
                        rotate_profile_index()
                        kill_cdp_chrome()
                        failover_triggered = True
                        break # Break out of the image generation loop
                    else:
                        print(f"Error: Frame {idx} failed completely after 3 attempts. Skipping to next frame.")
            
            # If failover was triggered, we must break the folder loop to restart Playwright
            if failover_triggered:
                break

        if failover_triggered:
            print("\n[SYSTEM] Reinitializing Playwright environment with new profile. Fast-forwarding...\n")
            time.sleep(3)
            continue # Restart the 'while True' outer loop
        else:
            print("\nAll batch topic directory processings completed.")
            break # Exit script completely if everything finished successfully
```

---

### Step 3: Implement Failover in `generate_voice.py`

Update your import at the top:
```python
from utils import get_config_value, launch_chrome_with_profile, rotate_profile_index, kill_cdp_chrome
```

Locate `def main():`. Wrap it in the exact same outer loop:
```python
    print("Verified input files...")

    # NEW: The Outer Recovery Loop
    while True:
        failover_triggered = False
        
        try:
            with sync_playwright() as p:
                chrome_path = get_chrome_path()
                # Issue 6: Multi-Profile Initialization Framework
                switch_enabled_str = get_config_value("SWITCH_ACCOUNTS_ENABLED", "false").lower()
                accounts_enabled = switch_enabled_str in ['true', '1', 'yes']
                current_profile_idx = get_config_value("ACTIVE_PROFILE_INDEX", "1")
                # ... (rest of connection logic)
```

Finally, scroll down to the absolute bottom of the script, where the exponential backoff handles failures (around line 720).

**Replace the `if attempt_count >= 3:` block with the dynamic failover logic:**
```python
                attempt_count = getattr(main, 'attempt_count', 0) + 1
                main.attempt_count = attempt_count
                
                retry_limit = int(get_config_value("FAILOVER_RETRY_LIMIT", "3"))
                
                if attempt_count >= retry_limit:
                    if accounts_enabled:
                        print(f"\n[FAILOVER ALERT] Chapter {chapter_idx} failed {retry_limit} times. Triggering Account Rotation...")
                        rotate_profile_index()
                        kill_cdp_chrome()
                        failover_triggered = True
                        break # Break out of the synthesis loop
                    else:
                        print(f"\n[FATAL ERROR] Chapter {chapter_idx} failed to generate after {retry_limit} attempts. Pausing execution.")
                        sys.exit(1)
                    
                print(f"\n[RETRY ALERT] Chapter {chapter_idx} audio was not generated correctly (Attempt {attempt_count}/{retry_limit}).")
                # ... (the rest of your exponential backoff sleep stays here)

        # Catch the failover outside the inner while loop
        if failover_triggered:
            print("\n[SYSTEM] Reinitializing Playwright environment with new profile. Fast-forwarding...\n")
            main.attempt_count = 0 # Reset attempts for the new profile
            time.sleep(3)
            continue # Restart the 'while True' outer loop
        else:
            break # Exit the script if everything finished successfully
```

*(Note: Adding `try/except` around `with sync_playwright():` as shown above protects the script from crashing if Playwright complains about the browser being forcibly closed by our `taskkill` command).*


Implement these final updates.