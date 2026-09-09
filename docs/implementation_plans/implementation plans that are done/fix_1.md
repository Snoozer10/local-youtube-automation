### Implementation Plan

**Objective:** Restore the highly robust, strict model selector from your original `script_image_generator.py` to `flow_image_generator.py` to prevent it from targeting generic menus.

**Step-by-Step Fix:**
1. **Remove Greedy Selectors:** Delete the broad `[aria-haspopup='menu']` selector from the list.
2. **Prioritize Explicit Text Matches:** Tell Playwright to explicitly look for buttons containing the words "Pro", "Flash-Lite", or "Flash" first. (In your screenshot, we can clearly see the correct button says "Pro v" right next to the microphone).
3. **Add Escape Fallbacks:** Inject `page.keyboard.press("Escape")` into the exception handlers so that if Playwright ever accidentally clicks the wrong menu, it immediately closes it and continues the script without freezing.

---

### The Code Fix for `flow_image_generator.py`

Open `flow_image_generator.py`. Locate the `def select_gemini_model(page, target_model="Pro"):` function (around line 49).

**Replace that entire function block with this robust version:**

```python
def select_gemini_model(page, target_model="Flash-Lite"):
    """Robust model selection to guarantee target model is applied."""
    print(f"\n[MODEL] Verifying Gemini model selection (Target: {target_model})...")
    model_btn = None
    
    # Strict selectors to avoid grabbing the settings/profile menus (Removed broad aria-haspopup)
    btn_selectors = [
        f"button:has-text('{target_model}')", 
        "button:has-text('Flash-Lite')", 
        "button:has-text('Pro')", 
        "button:has-text('Flash')", 
        "button:has-text('Thinking')",
        "button[aria-label*='model' i]", 
        "button[aria-label*='mode' i]"
    ]
    
    for sel in btn_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible() and loc.is_enabled():
                # Safety check to ignore the settings menu
                if "setting" in (loc.get_attribute("aria-label") or "").lower():
                    continue
                model_btn = loc
                break
        except Exception: continue
            
    if not model_btn: 
        print("Warning: Could not locate Gemini model selector button. Proceeding with active default.")
        return False
        
    try:
        active_text = model_btn.inner_text().strip()
        if target_model.lower() in active_text.lower():
            print(f"Success: Correct model '{target_model}' is already active.")
            return True
            
        print(f"Switching to '{target_model}'...")
        model_btn.click()
        time.sleep(2)
        
        dropdown_selectors = [
            f"mat-option:has-text('{target_model}')", 
            f"[role='menuitem']:has-text('{target_model}')", 
            f":text('{target_model}')"
        ]
        
        option_clicked = False
        for sel in dropdown_selectors:
            try:
                opt = page.locator(sel).first
                if opt.is_visible():
                    opt.click()
                    time.sleep(2)
                    option_clicked = True
                    print(f"Successfully selected model option: '{target_model}'")
                    break
            except Exception: continue
            
        if not option_clicked:
            print(f"Warning: Could not find '{target_model}' inside the dropdown.")
            page.keyboard.press("Escape") # Close menu if it failed
            
        return option_clicked
    except Exception as e: 
        print(f"Warning: Model selection failed: {e}")
        page.keyboard.press("Escape")
        return False
```

Save the file