import json, pathlib
from validator import verify_pipeline_integrity
p=pathlib.Path(r'youtube_runs\Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!\flow_prompts.json')
data=json.loads(p.read_text(encoding='utf-8'))
print('before fix: len', len(data))
# Try verify with old logic would fail, new should pass
try:
    verify_pipeline_integrity(data, 118)
    print('VERIFY PASS after patch')
except Exception as e:
    print('VERIFY FAIL', e)
    print(e.violations if hasattr(e,'violations') else '')
# Check items 86 and 113
for idx in [86,113]:
    item = next(x for x in data if x['index']==idx)
    print(f\"idx {idx} action: {item['visual_prompt']['subject_action_increment'][:120]}\")
