from roadmap_orchestrator import parse_roadmap_rows, parse_markdown_table_line, _row_from_cells, ROADMAP_COLUMNS
# Test 7-cell row (missing Color) should now be padded, not skipped
md_7 = '''| Index | Timestamp | Script Line | Sequence Type | Layout Classification | Camera Specification | Visual Concept & Composition | Color & Selective Arabic Text |
| 1 | [00:00] | hello | STANDALONE | AHWA_STUDIO | static | Host in studio | NONE |
| 2 | [00:04] | world | STANDALONE | AHWA_STUDIO | static | Host continues | 
| 3 | [00:08] | test | STANDALONE | AHWA_STUDIO | static | Host test |
'''
# Note: second row has 7 cells + trailing pipe? Actually let's craft 7-cell
md_7b = '''| 1 | [00:00] | hello world | STANDALONE | AHWA_STUDIO | static | Visual concept here |
| 2 | [00:04] | another | STANDALONE | AHWA_STUDIO | static | Another visual |
'''
print('=== Test 7-cell handling ===')
rows = parse_roadmap_rows(md_7b)
print(f'parsed {len(rows)} rows (expected 2 with padding)')
for r in rows:
    print(f'  idx {r.index} ts {r.timestamp} color {repr(r.color_and_arabic_text)}')

# Test 8-cell normal
md_8 = '''| Index | Timestamp | Script Line | Sequence Type | Layout Classification | Camera Specification | Visual Concept & Composition | Color & Selective Arabic Text |
| 1 | [00:00] | hello | STANDALONE | AHWA_STUDIO | static | Host in studio | NONE |
| 2 | [00:04] | world | STANDALONE | AHWA_STUDIO | static | Host continues | NONE |
'''
rows8 = parse_roadmap_rows(md_8)
print(f'8-cell parsed {len(rows8)} rows')

# Test short row logging
md_short = '''| 27 | 01:44 - 01:48 | some script | SCIENTIFIC_BLUEPRINT | RETRO_BLUEPRINT | static | Some visual |
'''
rows_short = parse_roadmap_rows(md_short)
print(f'short 7-cell parsed {len(rows_short)} (should pad)')
if rows_short:
    print(f'  padded color {repr(rows_short[0].color_and_arabic_text)}')

# Test _row_from_cells directly
cells7 = ['27', '01:44 - 01:48', 'script', 'SCIENTIFIC_BLUEPRINT', 'RETRO_BLUEPRINT', 'static', 'Some visual']
from roadmap_orchestrator import _row_from_cells
row = _row_from_cells(cells7 + [''])  # pad
print(f'_row_from_cells 7+pad -> {row.index if row else None}')

print('=== all tests done ===')
