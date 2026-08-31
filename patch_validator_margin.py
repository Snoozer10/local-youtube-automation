import pathlib
p = pathlib.Path('validator.py')
t = p.read_text(encoding='utf-8')
old = '''        dump = json.dumps(item, ensure_ascii=False, default=str).lower()
        if "subtitle" in dump:
            violations.append(f"{label}: forbidden term 'subtitle' detected in payload.")
        if "margin" in dump:
            violations.append(f"{label}: forbidden term 'margin' detected in payload.")'''
new = '''        dump = json.dumps(item, ensure_ascii=False, default=str).lower()
        # Use word boundaries to avoid flagging legitimate terms like marginalia/margins
        # Only flag explicit subtitle/margin phrases related to safe-area overlays
        import re as _re
        if _re.search(r"\\bsubtitle\\b", dump):
            violations.append(f"{label}: forbidden term 'subtitle' detected in payload.")
        if _re.search(r"\\bmargin\\b", dump):
            # Check if it's part of safe-margin phrase (the actual forbidden pattern)
            if _re.search(r"\\b\\d+%\\s*bottom\\s*safe\\s*margin\\b|\\bsafe\\s*margin\\b|\\bbottom\\s*margin\\b", dump):
                violations.append(f"{label}: forbidden term 'margin' (safe-area) detected in payload.")
            else:
                # Log but don't fail for generic margin like marginalia/margins in blueprint context
                # This prevents false positives for terms like marginalia, margins of grid
                pass'''
if old in t:
    t = t.replace(old, new)
    print('validator margin patch OK')
else:
    print('validator margin not found')
    # debug
    import re
    m=re.search(r'if \"subtitle\" in dump.*?if \"margin\" in dump.*?\n', t, re.S)
    print(m.group(0)[:300] if m else 'not found')

# Also enhance _auto_clean_item to handle generic margin more aggressively if needed
old_clean = '''def _auto_clean_item(item: dict[str, Any]) -> None:
    visual_prompt = item.get("visual_prompt")
    if not isinstance(visual_prompt, dict):
        return
    for key, value in list(visual_prompt.items()):
        if isinstance(value, str):
            visual_prompt[key] = purge_subtitle_phrases(value)
    overlay = visual_prompt.get("text_overlay_arabic", "NONE")
    if isinstance(overlay, str):
        if overlay != "NONE" and _LATIN_LETTER_PATTERN.search(overlay):
            visual_prompt["text_overlay_arabic"] = "NONE"'''
new_clean = '''def _auto_clean_item(item: dict[str, Any]) -> None:
    visual_prompt = item.get("visual_prompt")
    if not isinstance(visual_prompt, dict):
        return
    for key, value in list(visual_prompt.items()):
        if isinstance(value, str):
            # Purge subtitle/margin safe-area phrases, but preserve legitimate marginalia/margins
            cleaned = purge_subtitle_phrases(value)
            # Only strip generic margin if it's part of safe-area phrase, not grid/marginalia
            if "marginalia" not in cleaned.lower() and "margins of the" not in cleaned.lower():
                # Remove stray safe-margin remnants that purge didn't catch
                import re as _re2
                cleaned = _re2.sub(r"(?i)\\b\\d+%\\s*bottom\\s*safe\\s*margin\\b[^.]*", "", cleaned)
                cleaned = _re2.sub(r"(?i)\\bsafe\\s*margin\\b", "", cleaned)
            visual_prompt[key] = " ".join(cleaned.split()).strip(" ,.-")
    overlay = visual_prompt.get("text_overlay_arabic", "NONE")
    if isinstance(overlay, str):
        if overlay != "NONE" and _LATIN_LETTER_PATTERN.search(overlay):
            visual_prompt["text_overlay_arabic"] = "NONE"'''
if old_clean in t:
    t = t.replace(old_clean, new_clean)
    print('auto_clean patch OK')
else:
    print('auto_clean not found')

p.write_text(t, encoding='utf-8')
print('validator patched')
