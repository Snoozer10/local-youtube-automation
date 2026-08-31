import pathlib
p = pathlib.Path('validator.py')
t = p.read_text(encoding='utf-8')
old = '''        dump = json.dumps(item, ensure_ascii=False, default=str).lower()
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
new = '''        dump = json.dumps(item, ensure_ascii=False, default=str).lower()
        import re as _re
        # Flag subtitle (including plural subtitles) as forbidden - used for subtitle overlays
        if _re.search(r"\\bsubtitles?\\b", dump):
            violations.append(f"{label}: forbidden term 'subtitle' detected in payload.")
        # Flag margin as separate word (left margin band) but allow marginalia/margins (legitimate blueprint terms)
        if _re.search(r"\\bmargin\\b", dump):
            violations.append(f"{label}: forbidden term 'margin' detected in payload.")'''
if old in t:
    t = t.replace(old, new)
    print('validator2 patched')
else:
    print('validator2 not found')
    import re
    print(repr(t[t.find('dump = json.dumps'):t.find('dump = json.dumps')+500]))

p.write_text(t, encoding='utf-8')
print('written')
