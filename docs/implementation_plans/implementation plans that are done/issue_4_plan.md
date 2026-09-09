Here is the formalized implementation plan and the exact code block for Issue 4, utilizing all the architectural refinements we discussed.

### Implementation Plan for Issue 4

**Objective:** Strip out the brittle Base64/JS canvas extraction logic in `script_image_generator.py` and replace it with a clean, UI-driven hover-and-download sequence to retrieve the original high-quality image.

**Step-by-Step Execution:**
1.  **Locate the Image:** Wait for the `<img>` element inside the most recent `model-response` container to become fully visible in the DOM. Scroll it into view to prevent the mouse hover from being intercepted by the viewport edge.
2.  **Relative Precision Hover:** Calculate the image's width dynamically via its bounding box. Issue a Playwright `.hover()` command offset precisely 30px from the top-right corner to trigger the hidden UI overlay.
3.  **Click via Robust Selectors:** Target the newly revealed download button using a combination of English/Arabic `aria-label` and `data-tooltip` selectors to ensure it clicks regardless of localization or Google's A/B UI tests.
4.  **Native Download Interception:** Wrap the click inside a `with page.expect_download()` context manager. This shifts the download handling to the browser's network layer, preventing timeouts. Use `.save_as()` to block the thread until writing is finished.
5.  **Disk Verification Guard:** Check `os.path.exists()` and ensure `os.path.getsize() > 0` before marking the attempt as `success = True`.

---

### The Code Block for `script_image_generator.py`

**Where to paste:** 
Open `script_image_generator.py`. Locate the `for attempt in range(1, 4):` loop (around line 850). Look for the `if wait_for_gemini_response(...) is not None:` block. 

**Replace the entire chunk of code starting below `time.sleep(2)` down to `if download_attempt_success: ... break` with this clean implementation:**

```python
                        # Locate and download image using UI Hover Automation
                        download_attempt_success = False
                        last_response = gemini_page.locator("model-response").last
                        
                        # 1. Locate the generated image
                        img_locator = last_response.locator("img").first
                        
                        try:
                            # Wait for image to actually be attached and visible
                            img_locator.wait_for(state="visible", timeout=15000)
                            
                            # Force scroll into view to ensure the hover action is not blocked
                            img_locator.scroll_into_view_if_needed()
                            time.sleep(1)
                            
                            # 2. Leverage Playwright's Relative Hover
                            box = img_locator.bounding_box()
                            if box:
                                # Hover 30px from the right edge, 30px from the top
                                hover_x = box["width"] - 30
                                hover_y = 30
                                img_locator.hover(position={"x": hover_x, "y": hover_y})
                                time.sleep(1.5) # Wait for the overlay animation to reveal the button
                                
                                # 3. Robust Selector for the Download Button
                                dl_btn = last_response.locator(
                                    'button[aria-label*="Download full size" i], '
                                    'button[aria-label*="Download" i], '
                                    'button[aria-label*="تحميل" i], '
                                    'button[data-tooltip*="Download" i]'
                                ).first
                                
                                if dl_btn.is_visible():
                                    # 4. The Native expect_download Handler
                                    with gemini_page.expect_download(timeout=30000) as download_info:
                                        dl_btn.click()
                                        
                                    download = download_info.value
                                    
                                    # Blocking save operation ensures the file writes completely to disk
                                    download.save_as(save_path)
                                    
                                    # 5. Post-Download Verification Guard
                                    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                                        print(f"Successfully downloaded high-quality image: {save_path}")
                                        download_attempt_success = True
                                    else:
                                        print(f"Warning: Download completed but file is missing or 0 bytes: {save_path}")
                                else:
                                    print("Warning: Hover succeeded but Download button did not appear.")
                            else:
                                print("Warning: Could not calculate image bounding box for hover.")
                                
                        except Exception as e:
                            print(f"Warning: UI Hover/Download extraction failed: {e}")

                        if download_attempt_success:
                            success = True
                            break # Break out of the 3-attempt loop safely
```
