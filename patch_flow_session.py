import pathlib
p = pathlib.Path('flow_image_generator.py')
t = p.read_text(encoding='utf-8')
old_import = '''from pipeline_manifest import PhaseStatus, PipelineManifest, compute_script_hash
from prompt_planner import build_compact_preamble, plan_all_chunks
from roadmap_orchestrator import generate_master_roadmap, load_or_migrate_roadmap
from utils import (
    get_config_value,
    kill_cdp_chrome,
    launch_browser_with_profile,
    rotate_profile_index,
)
from validator import (
    enforce_arabic_in_prompt,
    flatten_visual_prompt_to_diffusion_text,
    verify_pipeline_integrity,
)'''
new_import = '''from pipeline_manifest import PhaseStatus, PipelineManifest, compute_script_hash
from prompt_planner import build_compact_preamble, plan_all_chunks
from roadmap_orchestrator import generate_master_roadmap, load_or_migrate_roadmap
from utils import (
    get_config_value,
    kill_cdp_chrome,
    launch_browser_with_profile,
    rotate_profile_index,
)
from validator import (
    enforce_arabic_in_prompt,
    flatten_visual_prompt_to_diffusion_text,
    verify_pipeline_integrity,
)

try:
    from gemini_controller import reset_session_tracker
except Exception:
    def reset_session_tracker():
        pass'''
if old_import in t:
    t = t.replace(old_import, new_import)
    print('import patched flow')
else:
    print('import not found flow')

old_retry = '''    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            last_exc = e
            print(
                f"  \\u26a0\\ufe0f {label} failed (attempt {attempt}/{retries}): {e}. "
                "Reloading Gemini page and retrying..."
            )
            try:
                gemini_page.bring_to_front()
                gemini_page.reload(wait_until="domcontentloaded", timeout=45000)
                gemini_page.bring_to_front()
                time.sleep(3)
            except Exception as reload_err:
                print(f"  \\u26a0\\ufe0f Gemini page reload during retry failed: {reload_err}")
    raise RuntimeError(f"{label} failed after {retries} attempts: {last_exc}")'''
new_retry = '''    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            last_exc = e
            # Distinguish validation/parsing errors (same-session retry) from browser crashes (reload)
            err_msg = str(e).lower()
            is_validation = any(k in err_msg for k in ["missing", "exhausted", "validation", "schema violation", "forbidden term", "chunkplanningerror"])
            if is_validation:
                print(
                    f"  \\u26a0\\ufe0f {label} failed (attempt {attempt}/{retries}): {e}. "
                    "Retrying in same chat (no new chat, preserves context)..."
                )
                # Same-session retry: keep chat, just jitter and retry
                try:
                    gemini_page.bring_to_front()
                    time.sleep(2)
                except Exception:
                    pass
            else:
                print(
                    f"  \\u26a0\\ufe0f {label} failed (attempt {attempt}/{retries}): {e}. "
                    "Reloading Gemini page and retrying..."
                )
                try:
                    gemini_page.bring_to_front()
                    gemini_page.reload(wait_until="domcontentloaded", timeout=45000)
                    gemini_page.bring_to_front()
                    time.sleep(3)
                except Exception as reload_err:
                    print(f"  \\u26a0\\ufe0f Gemini page reload during retry failed: {reload_err}")
    raise RuntimeError(f"{label} failed after {retries} attempts: {last_exc}")'''
if old_retry in t:
    t = t.replace(old_retry, new_retry)
    print('retry patched')
else:
    print('retry not found')
    # debug
    import re
    m=re.search(r"last_exc.*raise RuntimeError", t, re.S)
    print(m.group(0)[:500] if m else 'not found')

# Also add reset_session_tracker at start of each subfolder processing
old_sub = '''                for _folder_idx, subfolder in enumerate(batch_queue, 1):
                    print("\\n==================================================")
                    print(f"PROCESSING TOPIC: {subfolder}")
                    print("==================================================")'''
new_sub = '''                for _folder_idx, subfolder in enumerate(batch_queue, 1):
                    print("\\n==================================================")
                    print(f"PROCESSING TOPIC: {subfolder}")
                    print("==================================================")
                    # Reset persistent session tracker for new topic (fresh chat at index 1, then reuse within threshold)
                    try:
                        reset_session_tracker()
                        from gemini_controller import get_session_reset_threshold
                        print(f"[SESSION] New topic, threshold={get_session_reset_threshold()} lines, will reuse chat within window")
                    except Exception:
                        pass'''
if old_sub in t:
    t = t.replace(old_sub, new_sub)
    print('subfolder patched')
else:
    print('subfolder not found')

p.write_text(t, encoding='utf-8')
print('flow_image_generator patched')
