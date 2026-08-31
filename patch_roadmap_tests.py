import pathlib
p = pathlib.Path('tests/unit/test_roadmap_orchestrator.py')
t = p.read_text(encoding='utf-8')
# Find and replace the two occurrences of sessions == 2 for roadmap
old = '''        assert fake_controller["sessions"] == 2
        assert len(fake_controller["injections"]) == 2'''
new = '''        assert fake_controller["sessions"] == 1
        assert len(fake_controller["injections"]) == 2'''
if old in t:
    t = t.replace(old, new)
    print('roadmap test1 patched')
else:
    print('roadmap test1 not found')

old2 = '''        assert fake_controller["sessions"] == 2
        assert len(fake_controller["injections"]) == 3'''
new2 = '''        assert fake_controller["sessions"] == 1
        assert len(fake_controller["injections"]) == 3'''
if old2 in t:
    t = t.replace(old2, new2)
    print('roadmap test2 patched')
else:
    print('roadmap test2 not found')

p.write_text(t, encoding='utf-8')
print('roadmap tests patched')
