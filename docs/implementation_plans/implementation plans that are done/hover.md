Here is the exact, step-by-step implementation plan to permanently resolve the `subtree intercepts pointer events` Playwright error.

### Architectural Diagnosis
Playwright includes a strict "Actionability Engine" that simulates human behavior. Before it hovers or clicks, it fires a laser through the Z-axis of the web page. If it hits an invisible UI layer (in this case, Google's `<div class="generated-image-controls">` overlay) before hitting the target `<img>`, it aborts the action to prevent misclicks. 

By applying the **`force=True`** parameter, we command Playwright to bypass the actionability checks and execute the DOM event directly on the coordinates, completely ignoring the invisible HTML layers. Moving the coordinates to the dead center (`width / 2`, `height / 2`) also prevents any CSS border-radius clipping issues on the corners.

---

### Implementation Plan: Playwright Actionability Override

**Objective:** Update the hover and click mechanics in `script_image_generator.py` to forcefully bypass transparent UI overlays and trigger the download button safely.

**Step-by-Step Execution:**
1. **Recalculate Hover Coordinates:** Replace the top-right corner math (`width - 30`, `30`) with absolute center math (`width / 2`, `height / 2`).
2. **Override Hover Actionability:** Inject `force=True` into `img_locator.hover()`.
3. **Override Click Actionability:** Inject `force=True` into `dl_btn.click()`.

---

### The Code Block for `script_image_generator.py`

Open `script_image_generator.py` and scroll down to the image generation execution block (around line 850). 

Locate the `try:` block starting below `# 1. Locate the generated image`.

**Replace the entire `try...except` block with this structurally reinforced version:**

```python
                        try:
                            # Wait for image to actually be attached and visible
                            img_locator.wait_for(state="visible", timeout=15000)
                            
                            # Force scroll into view to ensure the hover action is not blocked
                            img_locator.scroll_into_view_if_needed()
                            time.sleep(1)
                            
                            # 2. Leverage Playwright's Relative Hover (Forced Center)
                            box = img_locator.bounding_box()
                            if box:
                                # Hover the exact dead-center of the image to trigger the UI overlay safely
                                hover_x = box["width"] / 2
                                hover_y = box["height"] / 2
                                
                                # force=True bypasses the "subtree intercepts pointer events" error from hidden Google UI layers
                                img_locator.hover(position={"x": hover_x, "y": hover_y}, force=True)
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
                                        # Force the click just in case the UI overlay shifts
                                        dl_btn.click(force=True)
                                        
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
```