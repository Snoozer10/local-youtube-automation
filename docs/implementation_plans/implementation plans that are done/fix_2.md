### Architectural Diagnosis: Why it targeted "Pro"

If you look closely at your previous terminal output, it printed this exact line:
`[MODEL] Verifying Gemini model selection (Target: Pro)...`

**Why did this happen?** 
The script is *already* reading from your `.txt` config file! Your `gemini_model.txt` file currently has the line `IMAGE_PLANNER_MODEL=Pro`. Because the text file said "Pro", the script obediently targeted "Pro". 

**To change it to Flash-Lite:** All you have to do is open your `gemini_model.txt` file and change that line to `IMAGE_PLANNER_MODEL=Flash-Lite`. 

However, your request to "make it customizable in .txt to change the model whenever I want" brings up a brilliant point: **We haven't made the Google Flow Image Model (e.g., "Nano Banana 2") customizable yet!**

Let's do a massive upgrade. We will upgrade the config file so you can control **both** the Gemini Chat Model *and* the Google Flow Image Model entirely from the `.txt` file. We will also add a "fuzzy matcher" so it doesn't get confused if Google writes "Flash-Lite" with a hyphen or a space ("Flash Lite").

---

### Implementation Plan

**Objective:** Add complete `.txt` customization for the Google Flow Image model, and add fuzzy text-matching to the Gemini model selector so it never fails on hyphenated names.

**Step 1: Update the Config File & Template (`utils.py`)**
We will add `FLOW_IMAGE_MODEL=Nano Banana 2` to the configuration system.

**Step 2: Upgrade `select_gemini_model` (`flow_image_generator.py`)**
We will add logic that checks for both "Flash-Lite" and "Flash Lite" so Google's UI changes don't break it.

**Step 3: Upgrade `setup_flow_ui` (`flow_image_generator.py`)**
We will script Playwright to click the image model dropdown inside Google Flow and select whatever model you typed into the `.txt` file.

---

### Step 1: Add the new setting to `utils.py`
Open `utils.py`. Locate the `get_config_value` function. Add the new `FLOW_IMAGE_MODEL` line to the template generator block:

```python
                f.write("IMAGE_RESET_LOOP_LIMIT=20\n")
                f.write("SWITCH_ACCOUNTS_ENABLED=true\n")
                f.write("ACTIVE_PROFILE_INDEX=1\n")
                f.write("FAILOVER_RETRY_LIMIT=3\n")
                f.write("BROWSER_TYPE=chrome\n")
                f.write("FLOW_IMAGE_MODEL=Nano Banana 2\n") # <-- NEW: Controls the Google Flow UI
```
*(Also, open your actual `gemini_model.txt` on your computer and manually paste `FLOW_IMAGE_MODEL=Nano Banana 2` into it, and ensure `IMAGE_PLANNER_MODEL=Flash-Lite` is set!)*

---

### Step 2: The Code Updates for `flow_image_generator.py`

Open `flow_image_generator.py`. We are going to replace **two functions** (`select_gemini_model` and `setup_flow_ui`), and tweak **one line** in `main()`.

**1. Replace the `select_gemini_model` function (around line 50):**
```python
def select_gemini_model(page, target_model="Flash-Lite"):
    """Robust model selection with fuzzy matching for hyphens/spaces."""
    print(f"\n[MODEL] Verifying Gemini model selection (Target: {target_model})...")
    model_btn = None
    
    # Handle Google's UI variations (e.g., "Flash-Lite" vs "Flash Lite")
    target_alt = target_model.replace("-", " ") 
    
    btn_selectors = [
        f"button:has-text('{target_model}')", 
        f"button:has-text('{target_alt}')",
        "button[aria-label*='model' i]", 
        "button[aria-label*='mode' i]"
    ]
    
    for sel in btn_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible() and loc.is_enabled():
                if "setting" in (loc.get_attribute("aria-label") or "").lower():
                    continue
                model_btn = loc
                break
        except Exception: continue
            
    if not model_btn: 
        print("Warning: Could not locate Gemini model selector button.")
        return False
        
    try:
        active_text = model_btn.inner_text().strip().lower()
        if target_model.lower() in active_text or target_alt.lower() in active_text:
            print(f"Success: Correct model '{target_model}' is already active.")
            return True
            
        print(f"Switching to '{target_model}'...")
        model_btn.click()
        time.sleep(2)
        
        dropdown_selectors = [
            f"mat-option:has-text('{target_model}')", f"mat-option:has-text('{target_alt}')",
            f"[role='menuitem']:has-text('{target_model}')", f"[role='menuitem']:has-text('{target_alt}')",
            f":text('{target_model}')", f":text('{target_alt}')"
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
            page.keyboard.press("Escape") 
            
        return option_clicked
    except Exception as e: 
        print(f"Warning: Model selection failed: {e}")
        page.keyboard.press("Escape")
        return False
```

**2. Replace the `setup_flow_ui` function (around line 95):**
*(This adds the logic to select "Nano Banana" or "Imagen 3" based on your `.txt` file).*
```python
def setup_flow_ui(page, target_flow_model="Nano Banana 2"):
    """Navigates to Google Flow and configures the UI (Model, 16:9, Agent OFF)."""
    print(f"\n[FLOW] Configuring workspace (Target Model: {target_flow_model})...")
    page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)

    try:
        new_proj_btn = page.locator("button:has-text('New project'), text='+ New project'").first
        if new_proj_btn.is_visible():
            new_proj_btn.click()
            time.sleep(3)
    except Exception: pass

    # Turn Agent OFF
    try:
        agent_btn = page.locator("button:has-text('Agent')").first
        if agent_btn.is_visible():
            is_active = agent_btn.evaluate("el => el.getAttribute('aria-pressed') === 'true' || el.classList.contains('active')")
            if is_active:
                print("[FLOW] Turning Agent OFF to protect monolithic prompts.")
                agent_btn.click()
                time.sleep(1)
    except Exception: pass

    # Select Custom Flow Model
    try:
        # Looking for the dropdown that currently holds a model name like Nano Banana or Imagen
        model_dropdown = page.locator("button:has-text('Nano Banana'), button:has-text('Imagen'), button[aria-haspopup='listbox']").first
        if model_dropdown.is_visible():
            active_flow_text = model_dropdown.inner_text()
            if target_flow_model.lower() not in active_flow_text.lower():
                print(f"[FLOW] Changing image model to '{target_flow_model}'...")
                model_dropdown.click()
                time.sleep(1)
                
                model_option = page.locator(f"[role='option']:has-text('{target_flow_model}'), mat-option:has-text('{target_flow_model}')").first
                if model_option.is_visible():
                    model_option.click()
                    time.sleep(1)
                else:
                    page.keyboard.press("Escape")
    except Exception as e: 
        print(f"[FLOW] Warning setting image model: {e}")

    # Set 16:9
    try:
        settings_icon = page.locator("button:has(svg path[d*='M3']), button[aria-label*='Settings' i]").last
        if settings_icon.is_visible():
            settings_icon.click()
            time.sleep(1)
        ratio_btn = page.locator("button:has-text('16:9'), div:has-text('16:9')").first
        if ratio_btn.is_visible():
            ratio_btn.click()
            print("[FLOW] Aspect Ratio set to 16:9.")
            time.sleep(1)
        page.keyboard.press("Escape")
    except Exception: pass
```

**3. Inject the Config Fetcher in `main()`**
Scroll down to your `main()` loop where the config variables are pulled (around line 170). 
Add `target_flow_model` and pass it to `setup_flow_ui`.

*Change this chunk:*
```python
                    target_planner_model = get_config_value("IMAGE_PLANNER_MODEL", "Flash-Lite")
                    reset_loop_limit = int(get_config_value("IMAGE_RESET_LOOP_LIMIT", "20"))
```
*To this:*
```python
                    target_planner_model = get_config_value("IMAGE_PLANNER_MODEL", "Flash-Lite")
                    target_flow_model = get_config_value("FLOW_IMAGE_MODEL", "Nano Banana 2")
                    reset_loop_limit = int(get_config_value("IMAGE_RESET_LOOP_LIMIT", "20"))
```

*Finally, update the two places where `setup_flow_ui(flow_page)` is called (around lines 255 and 273) to include the new variable:*
`setup_flow_ui(flow_page, target_flow_model)`