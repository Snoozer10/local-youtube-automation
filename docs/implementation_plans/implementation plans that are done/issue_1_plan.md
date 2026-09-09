### Implementation Plan for Issue 1

Here is the exact plan integrating your edge-case protections:
1.  **Imports:** Add `hashlib` to support MD5 generation.
2.  **MD5 Helper:** Add a new `get_file_md5()` function that safely streams the file in chunks to calculate the hash.
3.  **Error Selectors:** Update `check_ai_studio_errors()` to catch the specific 500 and Quota error strings.
4.  **Download & Verification Block:** Replace the existing download logic inside the main loop to:
    *   Wrap `expect_download` with a specific timeout to catch silent UI failures (Edge Case A).
    *   Rely on Playwright's `download.save_as()` which natively blocks until the file is fully written to disk, preventing race conditions (Edge Case B).
    *   Fetch the MD5 of the newly saved file and compare it against `Chapter_{chapter_idx - 1}.wav`, explicitly guarding for `chapter_idx > 1` (Edge Case C).
    *   Trigger the loop's built-in `[RECOVER]` state by modifying `main.attempt_count` and calling `continue` if a duplicate is found.

Here are the exact code blocks to apply to `generate_voice.py`.

---

### Step 1: Add the required import
At the top of `generate_voice.py`, add `hashlib` to your imports (around line 12):

```python
import math
import json
import tempfile
import hashlib  # <-- NEW: Added for MD5 verification
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError # <-- NEW: Import TimeoutError safely
```

### Step 2: Add the MD5 Helper Function
Add this helper function anywhere above `main()` (e.g., right before `check_ai_studio_errors`):

```python
def get_file_md5(file_path):
    """Calculates the MD5 hash of a file to verify absolute uniqueness."""
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
```

### Step 3: Update the Error Selectors
Locate the `check_ai_studio_errors(page)` function (around line 324). Update the `error_selectors` list to explicitly include your strings:

```python
def check_ai_studio_errors(page):
    error_selectors = [
        "text='Http response'",
        "text='status code'",
        "text='500 Internal Server Error'",  # <-- NEW
        "text='Quota Exceeded'",             # <-- NEW
        "text='quota exceeded'",             # <-- NEW (lowercase fallback)
        "mat-snack-bar-container",
        ".error-container"
    ]
    # ... rest of the function remains the same
```

### Step 4: Replace the Download & Verification Logic
Locate the download block inside your `main()` `while True:` loop (around line 673). Replace the entire `if download_btn.is_visible(): ... else: ...` block with the following robust version:

```python
            if download_btn.is_visible():
                download_success = False
                try:
                    # Edge Case A: Wrap in try/except with a strict timeout so it doesn't hang if UI fails silently
                    with tab1_speech.expect_download(timeout=15000) as download_info:
                        human_hover_and_click(tab1_speech, download_btn)
                    
                    download = download_info.value
                    
                    # Edge Case B: save_as natively blocks until the file is completely written to disk
                    download.save_as(target_dest)
                    print(f"File downloaded and saved to: {target_dest}")
                    download_success = True

                except PlaywrightTimeoutError:
                    print("\n[TIMEOUT] Playwright timed out waiting for the download event to trigger. Possible silent 500 error.")
                except Exception as e:
                    print(f"\n[ERROR] Error downloading or saving audio file: {e}")

                if download_success:
                    # Edge Case C: MD5 Duplicate Verification (Only if chapter > 1)
                    is_duplicate = False
                    if chapter_idx > 1:
                        previous_dest = os.path.join(latest_run, f"Chapter_{chapter_idx - 1}.wav")
                        if os.path.exists(previous_dest):
                            current_md5 = get_file_md5(target_dest)
                            previous_md5 = get_file_md5(previous_dest)
                            
                            if current_md5 and previous_md5 and current_md5 == previous_md5:
                                is_duplicate = True
                                print(f"\n[ALERT] MD5 Hash Match! Google served stale audio (Duplicate of Chapter {chapter_idx - 1}).")
                                
                    if is_duplicate:
                        # Clean up the bad file, increment attempts, and restart loop to trigger [RECOVER] block
                        try:
                            os.remove(target_dest)
                        except Exception:
                            pass
                        main.attempt_count = getattr(main, 'attempt_count', 0) + 1
                        continue

                    # If successful and unique, save progress checkpoint
                    try:
                        checkpoint_path = os.path.join(latest_run, "voice_checkpoint.json")
                        checkpoint_data = {"completed_chapters": chapter_idx}
                        with open(checkpoint_path, "w", encoding="utf-8") as f:
                            json.dump(checkpoint_data, f, ensure_ascii=False, indent=4)
                        print(f"Progress checkpoint saved for chapter {chapter_idx}.")
                    except Exception as ec:
                        print(f"Warning: Failed to save progress checkpoint ({ec})")
                else:
                    # If download_success is False (Timeout or other error), force retry
                    main.attempt_count = getattr(main, 'attempt_count', 0) + 1
                    continue
            else:
                print("\n[WARNING] Download button not found on screen.")
                main.attempt_count = getattr(main, 'attempt_count', 0) + 1
                continue
```

