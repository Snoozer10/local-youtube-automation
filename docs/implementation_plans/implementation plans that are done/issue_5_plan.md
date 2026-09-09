### Implementation Plan for Issue 5

**Objective:** Replace the hardcoded session reset interval (15) in `script_image_generator.py` with a dynamic, fail-safe variable fetched from `gemini_model.txt`.

**Step-by-Step Execution:**
1.  **Update the Config Template:** Add `IMAGE_RESET_LOOP_LIMIT=20` to the `get_config_model` fallback template so it automatically populates if the file is recreated.
2.  **Fetch and Safely Cast:** Right before the image rendering loop begins in `main()`, fetch the string from the config and safely cast it using your `try/except` and `.strip()` logic, defaulting to `20` upon failure.
3.  **Inject into Modulus Math:** Replace the hardcoded `15` with `reset_loop_limit` inside the `if executed_generations_count > 1 and...` condition.

---

### Code Blocks for `script_image_generator.py`

**Step 1: Update the Auto-Generator Template**
Locate the `get_config_model` function at the top of your script. Update the `with open(...)` block to include the new limit:
*Change it to look like this:*
```python
        # Auto-create the template if it doesn't exist
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("# Configuration for Gemini Web App Models\n")
                f.write("VOICE_GENERATOR_MODEL=Flash-Lite\n")
                f.write("IMAGE_PLANNER_MODEL=Pro\n")
                f.write("IMAGE_RESET_LOOP_LIMIT=20\n")  # <-- NEW
        except Exception:
            pass
```

**Step 2: Fetch and Cast the Variable**
Scroll down inside `main()`, right before you open the fresh chat session for PHASE 2 (around line 790). Add your robust fetching logic:

*Change this:*
```python
            # PHASE 2: IMAGE RENDERING
            print("\n" + "="*50)
            print("PHASE 2: IMAGE RENDERING PHASE")
            print("="*50)
            print(f"Loaded {total_frames} pre-planned prompts for image rendering.")

            # Open a fresh chat session for rendering to clear memory of previous topic runs
```

*To this:*
```python
            # PHASE 2: IMAGE RENDERING
            print("\n" + "="*50)
            print("PHASE 2: IMAGE RENDERING PHASE")
            print("="*50)
            print(f"Loaded {total_frames} pre-planned prompts for image rendering.")

            # NEW: Dynamic Runtime Session Reset fetching
            raw_limit = get_config_model("IMAGE_RESET_LOOP_LIMIT", "20")
            try:
                reset_loop_limit = int(raw_limit.strip())
            except ValueError:
                print(f"Warning: Invalid limit '{raw_limit}' in config. Defaulting to 20.")
                reset_loop_limit = 20

            # Open a fresh chat session for rendering to clear memory of previous topic runs
```

**Step 3: Update the Loop Logic**
Scroll down slightly to the `executed_generations_count` block (around line 818) inside the `for current_run, ...` loop. Swap the hardcoded `15` for our new variable:

*Change this:*
```python
                # Run window optimization reset block (every 15 active runs)
                executed_generations_count += 1
                if executed_generations_count > 1 and (executed_generations_count - 1) % 15 == 0:
                    print(f"\n[RESET] Running window optimization block (Frame Index {idx})...")
```

*To this:*
```python
                # Run window optimization reset block based on config limit
                executed_generations_count += 1
                if executed_generations_count > 1 and (executed_generations_count - 1) % reset_loop_limit == 0:
                    print(f"\n[RESET] Running window optimization block (Frame Index {idx} / Limit: {reset_loop_limit})...")
```

Make sure you also manually add `IMAGE_RESET_LOOP_LIMIT=20` to the existing `gemini_model.txt` file on the root folder so the script can read it. 

