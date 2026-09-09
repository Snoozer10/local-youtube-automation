# Implementation Plan: Google Flow UI State Reset & Active Polling Fix

## 1. Architectural Diagnosis
**The Bug:** The script is rapidly looping through generation attempts (Attempt 1 -> Attempt 2 -> Attempt 3) without waiting, eventually crashing Chrome. The terminal shows immediate `Google Flow rejected the prompt` errors.
**The Root Cause:** 
1. **Hidden DOM Elements (The Fast-Fail Trap):** The script uses `flow_page.get_by_text(...).count() > 0` to check for error messages. In modern web apps, error toasts (like "Failed") are often kept in the DOM but hidden via CSS (`display: none`). Playwright's `count()` counts *hidden* elements too, causing an instant false-positive failure on every tick.
2. **State Pollution (The Rapid-Fire Trap):** When a prompt legitimately fails, Google Flow displays an error toast on the screen. Because the script does not reload the page or dismiss the toast, Attempt 2 starts, sees the *exact same error toast* from Attempt 1, and instantly fails again. This creates a rapid-fire cascade that crashes the browser memory.

## 2. Remediation Strategy
1. **Visible-Only Filtering:** We must append `.filter(state="visible")` or use `.is_visible()` to the Playwright locators so it only flags errors that are actively displaying on the screen.
2. **State Clean-Up (Soft Reload):** If an attempt fails, we must clear the UI state so the next attempt starts fresh. We will use `flow_page.goto(active_project_url)` at the end of a failed attempt. This acts as a "soft reset," clearing error toasts without abandoning the project.
3. **Exponential Backoff:** Inject a cooldown sleep timer before a retry to respect Google's rate limits.

---

## 3. Code Modifications

**Target File:** `flow_image_generator.py`
**Target Section:** Phase 2 Image Rendering, inside the `for attempt in range(1, 4):` loop.

### Action 1: Update the Fast-Fail Monitor
Locate the "Dynamic Active Polling Monitor" block (around line 345).

*Old Code to Replace:*
```python
                                for tick in range(90): # Up to 3 minutes of monitoring
                                    # Fast-Fail: Check for safety filters or API errors
                                    if flow_page.get_by_text(re.compile(r"(unusual activity|Failed|Couldn't generate)", re.IGNORECASE)).count() > 0:
                                        print("  ⚠️ Google Flow rejected the prompt (Safety/Rate Limit).")
                                        raise Exception("Generation failed due to API rejection.")
                                        
                                    # Look for active loading percentages anywhere on the screen (e.g., "5%", "99%")
                                    is_loading = flow_page.get_by_text(re.compile(r"\d+%")).count() > 0
```

*New Injected Code:*
```python
                                for tick in range(90): # Up to 3 minutes of monitoring
                                    # Fast-Fail: Only trigger if the error text is VISIBLE on screen
                                    error_toast = flow_page.get_by_text(re.compile(r"(unusual activity|Failed|Couldn't generate)", re.IGNORECASE)).filter(state="visible")
                                    if error_toast.count() > 0:
                                        print(f"  ⚠️ Google Flow rejected the prompt: {error_toast.first.inner_text()}")
                                        raise Exception("Generation failed due to API rejection or UI error.")
                                        
                                    # Look for active loading percentages anywhere on the screen (e.g., "5%", "99%")
                                    is_loading = flow_page.get_by_text(re.compile(r"\d+%")).filter(state="visible").count() > 0
```

### Action 2: Add the UI State Reset (Soft Reload)
Locate the `except Exception as e:` block at the very end of the `attempt` loop (around line 430).

*Old Code to Replace:*
```python
                            except PlaywrightTimeoutError: print("  ⚠️ Playwright Timeout Error.")
                            except Exception as e: print(f"  ⚠️ Error: {e}")
```

*New Injected Code:*
```python
                            except PlaywrightTimeoutError: 
                                print("  ⚠️ Playwright Timeout Error.")
                            except Exception as e: 
                                print(f"  ⚠️ Error: {e}")
                            
                            # CRITICAL FIX: If the attempt failed, the UI is likely polluted with an error toast.
                            # We must refresh the specific project URL to clear the error state before the next attempt.
                            if not success and attempt < 3:
                                print("  🔄 Clearing UI error state before retry...")
                                time.sleep(3) # Brief cooldown for rate limits
                                flow_page.goto(active_project_url, wait_until="domcontentloaded")
                                time.sleep(3)
```

## 4. Verification Steps for Antigravity
1. Execute the code replacement.
2. Verify that `active_project_url` is successfully passed and utilized in the new `flow_page.goto()` block.
3. Validate that `.filter(state="visible")` was successfully chained to the locator, ensuring hidden DOM elements do not trigger false-positive API rejections.
