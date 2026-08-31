import pathlib
p = pathlib.Path('gemini_controller.py')
t = p.read_text(encoding='utf-8')
old = '''from gemini_utils import (
    RESPONSE_SELECTOR,
    check_gemini_error_state,
    find_input_box,
    find_send_button,
    is_gemini_generating,
    select_gemini_model,
)'''
new = '''from gemini_utils import (
    RESPONSE_SELECTOR,
    check_gemini_error_state,
    find_input_box,
    find_send_button,
    is_gemini_generating,
    select_gemini_model,
)

try:
    from utils import get_config_value
except Exception:
    import os as _os
    def get_config_value(k, d=""):
        v = _os.getenv(k)
        return v if v is not None else d'''
if old in t:
    t = t.replace(old, new)
    print('import patched2')
else:
    print('import not found2')
    # debug
    print(repr(t[t.find('from gemini_utils'):t.find('from gemini_utils')+300]))

p.write_text(t, encoding='utf-8')
print('written')
