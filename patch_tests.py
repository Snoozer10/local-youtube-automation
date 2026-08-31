import pathlib
p = pathlib.Path('tests/unit/test_prompt_planner.py')
t = p.read_text(encoding='utf-8')
# Update test_two_chunks to expect 1 (threshold 100, so 2 chunks share same chat)
old1 = '''        assert fake_controller["sessions"] == 2
        assert fake_controller["models"] == ["Flash-Lite", "Flash-Lite"]'''
new1 = '''        assert fake_controller["sessions"] == 1
        assert fake_controller["models"] == ["Flash-Lite"]'''
if old1 in t:
    t = t.replace(old1, new1)
    print('test_two_chunks patched')
else:
    print('test_two_chunks not found')

old2 = '''        assert fake_controller["sessions"] == 2
        assert len(result) == 30
        saved = json.loads((tmp_path / "flow_prompts.json").read_text(encoding="utf-8"))
        assert [frame["index"] for frame in saved] == list(range(1, 31))'''
# This is for test_corrupt_baseline - need to be more specific
# Find the second occurrence
import re
# Find all occurrences of that pattern and replace the last one (corrupt baseline)
# Simpler: replace only when it's in test_corrupt_baseline context
old_corrupt = '''        assert fake_controller["sessions"] == 2
        assert len(result) == 30
        saved = json.loads((tmp_path / "flow_prompts.json").read_text(encoding="utf-8"))
        assert [frame["index"] for frame in saved] == list(range(1, 31))
'''
# The file has this pattern twice (once for test_two_chunks? Actually test_two_chunks has models check, not this)
# For corrupt baseline, it should also be 1
if t.count(old_corrupt) >= 1:
    # Replace the last occurrence (which is corrupt baseline)
    # Find the position of the last occurrence
    idx = t.rfind(old_corrupt)
    t = t[:idx] + '''        assert fake_controller["sessions"] == 1
        assert len(result) == 30
        saved = json.loads((tmp_path / "flow_prompts.json").read_text(encoding="utf-8"))
        assert [frame["index"] for frame in saved] == list(range(1, 31))
''' + t[idx+len(old_corrupt):]
    print('corrupt baseline patched')

p.write_text(t, encoding='utf-8')
print('tests patched')
