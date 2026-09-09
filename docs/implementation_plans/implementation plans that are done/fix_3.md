## Implementation Plan: Deep JSON Prompting

**Objective:** Upgrade `flow_image_generator.py` to request, parse, and inject deeply nested JSON objects directly into Google Flow, enforcing absolute frame-to-frame consistency and strict negative constraints.

**Phase 1: Upgrade the Python Parser (`parse_json_prompts`)**
1. Modify the JSON extraction loop to check if the `visual_prompt` is a nested dictionary.
2. If it is a dictionary, use `json.dumps(vp, indent=2)` to convert the deep JSON object into a beautifully formatted string. This ensures that when Playwright types it into the Google Flow text box, it retains the exact JSON structure.

**Phase 2: Overhaul the Monolithic Template (`monolithic_template`)**
1. Rewrite the system prompt to forbid flat text strings.
2. Instruct Gemini 1.5 Pro to output `visual_prompt` as a nested JSON object with explicit keys: `subject`, `wardrobe`, `environment`, `lighting`, `camera`, `composition`, `color_palette`, `style`, `mood`, and `constraints`.
3. Provide a strict example of the JSON schema so Gemini never deviates from the format.

---

### Step 1: Update the Python Parser

Open `flow_image_generator.py`. Locate the `parse_json_prompts(file_path)` function near the top of the file (around line 30).

**Replace the entire `parse_json_prompts` function with this upgraded version:**

```python
def parse_json_prompts(file_path):
    """Parses pure JSON arrays to extract nested deep-JSON prompts for Flow."""
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    prompts = []
    # Extract JSON arrays from the text file (handles multiple chunks appended together)
    json_blocks = re.findall(r'\[\s*\{.*?\}\s*\]', content, re.DOTALL)
    
    for block in json_blocks:
        try:
            data = json.loads(block)
            for item in data:
                idx = int(item.get("index", 0))
                vp = item.get("visual_prompt", "")
                
                # CRITICAL UPGRADE: If visual_prompt is a deeply nested dictionary, 
                # convert it to a beautifully indented JSON string so Google Flow can read it natively!
                if isinstance(vp, dict):
                    prompt = json.dumps(vp, indent=2)
                else:
                    prompt = str(vp).strip()
                    
                if idx > 0 and prompt:
                    prompts.append((idx, prompt))
        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse a JSON block: {e}")
            
    # Sort by index to ensure correct sequential order
    prompts.sort(key=lambda x: x[0])
    return prompts
```

---

### Step 2: Update the Monolithic Template

Scroll down to **Phase 1: SINGLE-SESSION JSON STORYBOARD PLANNING** (around line 208).

**Replace the entire `monolithic_template = """ ... """` block with this Elite JSON Schema:**

```python
                        # THE ELITE DEEP-JSON MONOLITHIC TEMPLATE
                        monolithic_template = """# SYSTEM PROMPT: ELITE JSON MONOLITHIC KEYFRAME ARCHITECT

You are translating an Arabic script chunk into visual prompts for Google Flow (Nano Banana 2 model). 
CRITICAL LIMITATION: The image generator is completely STATELESS and HAS ZERO MEMORY. Advanced image models parse Key-Value JSON data with extreme accuracy to isolate variables and prevent feature-bleed. 

To ensure frame-to-frame consistency, EVERY single prompt must be a massive, exhaustive "Monolithic Prompt" written entirely as a DEEP NESTED JSON OBJECT.

## THE DEEP JSON STRUCTURE MANDATE
Your output MUST be a strict JSON array containing objects. Each object represents one frame.
Inside each frame object, the "visual_prompt" key MUST contain a NESTED JSON OBJECT using this exact schema:

- "subject": Anatomy, expression, pose, action. IF NOT B-ROLL, use the exact Monolithic Character: "A 2D cartoon male with a perfectly round white head, no nose, exactly 3 sparse thin black hair strands on top, and expressive circular white eyes. Thin black line-art limbs."
- "wardrobe": "Plain, unbranded dark charcoal-grey hoodie (hood down) and dark sweatpants."
- "environment": The physical location and setting details.
- "lighting": Type, direction, contrast, and source (e.g., "dramatic chiaroscuro", "harsh overhead spotlight").
- "camera": shot_type (wide, medium, close-up), angle (eye-level, low-angle, high-angle, dutch-angle), and focus.
- "composition": framing (rule-of-thirds, asymmetrical), and negative_space (low, medium, high).
- "color_palette": dominant_colors (always cool-toned slate/charcoal), accent_colors (exactly ONE vibrant pop of color).
- "style": genre ("2D digital webcomic illustration"), line_art ("pristine solid uniform black vector outlines"), coloring ("flat base colors").
- "mood": emotion and atmosphere.
- "constraints": { "no_text": true, "no_logos": true, "no_watermarks": true, "no_gibberish": true, "no_speech_bubbles": true }

## CINEMATIC RULES
1. CAMERA TAGS: Rotate constantly. Never use two wide shots in a row.
2. B-ROLL MACRO: For 1 out of every 4 prompts, the character MUST BE COMPLETELY ABSENT. The "subject" should be a macro description of a symbolic object, and "wardrobe" should be null.

## CRITICAL JSON OUTPUT FORMAT
You must output STRICTLY a JSON array. Do not write any conversational text outside the JSON block.

[
  {
    "index": 1,
    "timestamp": "[00:00]",
    "visual_prompt": {
      "subject": {
        "type": "character",
        "description": "A 2D cartoon male with a perfectly round white head, no nose, exactly 3 sparse thin black hair strands on top, and expressive circular white eyes. Thin black line-art limbs.",
        "action": "Sitting on the floor, gripping his knees.",
        "expression": "panic, dilated pinpoint pupils"
      },
      "wardrobe": {
        "clothing": "Plain, unbranded dark charcoal-grey hoodie (hood down) and dark sweatpants."
      },
      "environment": {
        "setting": "Minimalist dark slate-blue room fading into black emptiness.",
        "background_style": "minimalist void"
      },
      "lighting": {
        "type": "dramatic chiaroscuro",
        "direction": "top-down",
        "source": "harsh overhead spotlight"
      },
      "camera": {
        "shot_type": "wide",
        "angle": "dutch-angle",
        "focus": "sharp"
      },
      "composition": {
        "framing": "asymmetrical, character pushed to extreme bottom-right",
        "negative_space": "high"
      },
      "color_palette": {
        "dominant_colors": ["dark slate-blue", "charcoal", "white"],
        "accent_colors": ["neon-cyan glowing clock in foreground"],
        "contrast_level": "high"
      },
      "style": {
        "genre": "2D digital webcomic illustration",
        "line_art": "pristine solid uniform black vector outlines",
        "coloring": "flat base colors"
      },
      "mood": {
        "emotion": "panic",
        "atmosphere": "chaotic and tense"
      },
      "constraints": {
        "no_text": true,
        "no_logos": true,
        "no_watermarks": true,
        "no_gibberish": true,
        "no_speech_bubbles": true
      }
    }
  }
]

Reply EXACTLY with: "JSON System Ready. Awaiting chunks."
"""
```

Save `flow_image_generator.py` with these changes. This establishes a true AI-to-AI data pipeline. Gemini is outputting API-ready data, and Playwright is passing that data directly to Flow's image generation engine!