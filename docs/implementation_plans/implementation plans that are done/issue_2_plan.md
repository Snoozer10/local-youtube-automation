Here is the formal implementation plan and the exact code blocks for Issue 2, incorporating your excellent `KEY=VALUE` structure.

### Implementation Plan for Issue 2
1.  **Add a Shared Config Parser:** I will provide a new function `get_config_model(target_key, default_val)` that parses `gemini_model.txt` line-by-line, looking for the specific key. It will also auto-generate the file with your template if it's accidentally deleted.
2.  **Update `generate_voice.py`:**
    *   Add the parser and the `select_gemini_model()` UI helper (ported from the image script).
    *   In `main()`, fetch the `VOICE_GENERATOR_MODEL` value.
    *   Execute the model selection immediately after Tab 2 initializes the clean chat.
3.  **Update `script_image_generator.py`:**
    *   Add the same parser function.
    *   In `main()`, swap out the old `load_local_or_global_config` call with `get_config_model("IMAGE_PLANNER_MODEL", "Pro")`. (The execution logic is already in place here).

---

### Code Blocks for `generate_voice.py`

**Step 1: Add the Parser and UI Helper**
Paste these two functions anywhere above your `main()` function:

```python
def get_config_model(target_key, default_val="Flash-Lite"):
    """Reads a KEY=VALUE pair from the shared gemini_model.txt file."""
    config_path = "gemini_model.txt"
    if not os.path.exists(config_path):
        # Auto-create the template if it doesn't exist
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("# Configuration for Gemini Web App Models\n")
                f.write("VOICE_GENERATOR_MODEL=Flash-Lite\n")
                f.write("IMAGE_PLANNER_MODEL=Pro\n")
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

def select_gemini_model(page, target_model="Flash-Lite"):
    """Clicks the top-left dropdown in Gemini Web App and selects the target model."""
    print(f"\n[MODEL] Verifying Gemini LLM selection (Target: {target_model})...")
    model_btn = None
    btn_selectors = [
        "button:has-text('Flash-Lite')", "button:has-text('Pro')", 
        "button:has-text('Flash')", "button:has-text('Thinking')",
        "button[aria-label*='model' i]", "button[aria-label*='mode' i]", "[aria-haspopup='menu']"
    ]
    for sel in btn_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible() and loc.is_enabled():
                model_btn = loc
                break
        except Exception:
            continue
            
    if not model_btn:
        print("Warning: Could not locate Gemini model selector button. Proceeding with default.")
        return False
        
    try:
        active_text = model_btn.inner_text().strip()
        print(f"Active model detected on page: '{active_text}'")
        if target_model.lower() in active_text.lower():
            print(f"Success: Correct model '{target_model}' is already active.")
            return True
            
        print(f"Model mismatch. Switching to '{target_model}'...")
        model_btn.click()
        time.sleep(2)
        
        dropdown_selectors = [
            f"mat-option :text('{target_model}')", f"mat-option:has-text('{target_model}')",
            f"button:has-text('{target_model}')", f"[role='menuitem'] :text('{target_model}')",
            f"[role='menuitem']:has-text('{target_model}')", f":text('{target_model}')"
        ]
        
        option_clicked = False
        for sel in dropdown_selectors:
            try:
                opt = page.locator(sel).first
                if opt.is_visible():
                    opt.click()
                    option_clicked = True
                    print(f"Successfully selected model option: '{target_model}'")
                    time.sleep(2)
                    break
            except Exception:
                continue
                
        if not option_clicked:
            try:
                page.locator(f"text='{target_model}'").first.click(timeout=3000)
                option_clicked = True
                time.sleep(2)
            except Exception:
                page.locator("body").click()
                
        return option_clicked
    except Exception as e:
        print(f"Warning: Model selection failed: {e}")
        return False
```

**Step 2: Initialize and Call in `main()`**
Inside `main()`, locate the "Preset Configuration" block (around line 348) and add the new fetcher:

```python
    # Parse preset configuration choices (voice_option_notes.txt)
    voice_options = read_voice_options()
    target_model_name = voice_options.get("model", "gemini-2.5-pro-preview-tts")
    
    # NEW: Fetch target LLM model for Tab 2
    target_llm_model = get_config_model("VOICE_GENERATOR_MODEL", "Flash-Lite")
```

Next, scroll down to the "PHASE 4" block (around line 416) where `tab2_chat` is initialized. Call the selector right after starting the clean chat:

```python
        tab2_chat.bring_to_front()
        start_clean_gemini_chat(tab2_chat)

        # NEW: Select the correct LLM Model before sending prompts
        select_gemini_model(tab2_chat, target_llm_model)

        # Target the chat input textarea box
        chat_box = find_input_box(tab2_chat)
```

---

### Code Blocks for `script_image_generator.py`

**Step 1: Add the Parser Function**
Copy the exact same `get_config_model` function from above and paste it near the top of `script_image_generator.py` (e.g., above the `main()` function).

**Step 2: Update the Fetch Logic in `main()`**
Inside `main()` (around line 635), locate where `target_model` is defined and replace it so it uses the new parser:

*Change this:*
```python
            visuals_plan = load_local_or_global_config(subfolder, "visuals_plan.txt")
            visual_style = load_local_or_global_config(subfolder, "visual_style.txt", "2D digital webcomic style.")
            target_model = load_local_or_global_config(subfolder, "gemini_model.txt", "Flash-Lite")
```

*To this:*
```python
            visuals_plan = load_local_or_global_config(subfolder, "visuals_plan.txt")
            visual_style = load_local_or_global_config(subfolder, "visual_style.txt", "2D digital webcomic style.")
            target_model = get_config_model("IMAGE_PLANNER_MODEL", "Pro")  # <-- NEW
```

Make sure your local `gemini_model.txt` is updated to the `KEY=VALUE` format.