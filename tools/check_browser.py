import sys


def main() -> None:
    sys.path.insert(0, "src")
    from youtube_automation.core.utils import (
        _browser_process_facts,
        _listener_pids,
        _owned_browser_is_current,
        _read_owned_browsers,
    )

    r = _read_owned_browsers()
    print("Owned record:", r)
    listeners = _listener_pids(9222)
    print("Listener PIDs for 9222:", listeners)
    rec = r.get("9222", {})
    pid = rec.get("pid")
    if pid in listeners:
        facts = _browser_process_facts(pid)
        print("Process facts for", pid, ":", facts)
        print("Is current:", _owned_browser_is_current(rec, 9222))

if __name__ == "__main__":
    main()
