### Implementation Plan for Issue 3
1.  **Remove Aggressive Polling Logic:** I will strip out the `page.evaluate()` block and the `scroll_into_view_if_needed()` call from inside the 1-second `while` loop in `script_image_generator.py`.
2.  **Inject the Precision Dual-Scroll:** I will place your refined JavaScript (with the added root fallback) inside the success condition (`if stable_count >= 4:`), ensuring it runs exactly *once* the moment the response is finished generating, right before the function returns the text.

Here is the exact code modification for `script_image_generator.py`.

---

### Code Block for `script_image_generator.py`

Locate the `wait_for_gemini_response(page, initial_count, timeout_seconds=90)` function (around line 180). 

Replace the **entire `while` loop** (from `while time.time() - start_time < timeout_seconds:` down to the end of the function) with this updated version:

```python
    while time.time() - start_time < timeout_seconds:
        elapsed = time.time() - start_time
        if time.time() - last_log_time >= 15:
            print(f"Still waiting for text stability... (elapsed: {elapsed:.1f}s / {timeout_seconds}s)")
            last_log_time = time.time()
            
        try:
            # Periodically bring page to front to prevent background throttling
            if int(elapsed) % 10 == 0:
                try:
                    page.bring_to_front()
                except Exception:
                    pass
            
            last_response = page.locator("model-response").last
            current_text = last_response.evaluate("el => el.innerText", timeout=5000).strip()
            
            if current_text and current_text == last_text:
                if is_gemini_generating(page):
                    # Gemini is still active (generating slowly) — do not stabilize yet
                    stable_count = 0
                else:
                    stable_count += 1
                    
                if stable_count >= 4:  # Stable for 4 consecutive seconds
                    # === ISSUE 3: ONE-TIME SMOOTH SCROLL EXECUTION ===
                    page.evaluate("""
                        (() => {
                            // 1. Locate and scroll the main chat container
                            const mainContainer = Array.from(document.querySelectorAll('*')).find(el => {
                                const rect = el.getBoundingClientRect();
                                return rect.left > 200 && el.scrollHeight > el.clientHeight && 
                                       getComputedStyle(el).overflowY !== 'hidden';
                            });
                            if (mainContainer) {
                                mainContainer.scrollTo({ top: mainContainer.scrollHeight, behavior: 'smooth' });
                            } else {
                                // Fallback: Scroll the main window viewport
                                window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
                            }

                            // 2. Locate and scroll the left sidebar UP
                            const leftSidebar = Array.from(document.querySelectorAll('*')).find(el => {
                                const rect = el.getBoundingClientRect();
                                return rect.left >= 0 && rect.left < 200 && rect.width > 50 &&
                                       el.scrollHeight > el.clientHeight && 
                                       getComputedStyle(el).overflowY !== 'hidden';
                            });
                            if (leftSidebar) {
                                leftSidebar.scrollTo({ top: 0, behavior: 'smooth' });
                            }
                        })()
                    """)
                    time.sleep(1) # Allow 1 second for the smooth scroll animation to finish visually
                    
                    if current_text.startswith("Gemini said"):
                        current_text = current_text[len("Gemini said"):].strip()
                    return current_text
            else:
                last_text = current_text
                stable_count = 0
        except Exception:
            pass
        time.sleep(1)
        
    print(f"Warning: Response timed out after {timeout_seconds} seconds.")
    return None
```

Make these changes, run a quick test if you'd like, and let me know when you are ready to tackle the complex **Issue 4: High-Quality Hover-Download Automation**.