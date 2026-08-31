import pathlib, re
p = pathlib.Path('flow_image_generator.py')
t = p.read_text(encoding='utf-8')
# Find the retry function and patch it via regex
pattern = r"    last_exc: Exception \| None = None\s+for attempt in range\(1, retries \+ 1\):\s+try:\s+return fn\(\)\s+except KeyboardInterrupt:\s+raise\s+except Exception as e:\s+last_exc = e\s+print\(.*?Reloading Gemini page and retrying.*?\".*?\)\s+try:\s+gemini_page\.bring_to_front\(\)\s+gemini_page\.reload\(.*?\)\s+gemini_page\.bring_to_front\(\)\s+time\.sleep\(3\)\s+except Exception as reload_err:\s+print\(.*?reload_err.*?\)\s+raise RuntimeError"
# Use a simpler approach: just replace the whole function via searching for def and next def
import re
# Find def _retry_gemini_call and replace its body
old_func = re.search(r"def _retry_gemini_call\(.*?raise RuntimeError\(f\"\{label\} failed after.*?last_exc.*?\n", t, re.S)
if old_func:
    old_text = old_func.group(0)
    print('found old func len', len(old_text))
    new_func = '''def _retry_gemini_call(
    gemini_page: Any, fn: Callable[..., Any], label: str, retries: int = 3
) -> Any:
    \"\"\"Run a Gemini planning operation with bounded retries.

    Retries recover a lost browser turn (e.g. TargetClosedError during planning)
    without reconnecting the whole CDP browser: reload the Gemini page, wake it,
    and re-invoke the callable. Keeps planning idempotent via the manifest.
    For validation/parsing errors (missing indices, schema violations), retry in same chat
    to preserve context and avoid duplicate Control+Shift+O chats.
    \"\"\"
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            last_exc = e
            err_msg = str(e).lower()
            is_validation = any(k in err_msg for k in ["missing", "exhausted", "validation", "schema violation", "forbidden term", "chunkplanningerror"])
            if is_validation:
                print(
                    f"  [RETRY VALIDATION] {label} failed (attempt {attempt}/{retries}): {e}. "
                    "Retrying in same chat (no new chat, preserves context)..."
                )
                try:
                    gemini_page.bring_to_front()
                    time.sleep(2)
                except Exception:
                    pass
            else:
                print(
                    f"  [RETRY BROWSER] {label} failed (attempt {attempt}/{retries}): {e}. "
                    "Reloading Gemini page and retrying..."
                )
                try:
                    gemini_page.bring_to_front()
                    gemini_page.reload(wait_until="domcontentloaded", timeout=45000)
                    gemini_page.bring_to_front()
                    time.sleep(3)
                except Exception as reload_err:
                    print(f"  Gemini page reload during retry failed: {reload_err}")
    raise RuntimeError(f"{label} failed after {retries} attempts: {last_exc}")
'''
    t = t.replace(old_text, new_func)
    print('replaced via regex')
else:
    print('not found via regex')
    # fallback: try simpler
    if 'is_validation' not in t:
        print('is_validation not in file, need patch')
    else:
        print('already patched')

p.write_text(t, encoding='utf-8')
print('written')
