"""Controller and isolated worker for the separately approved one-Help probe.

Default invocation is inert. The controller validates a fresh, run-bound grant,
holds the installation Audacity lease, then invokes the killable supervisor.
Only its private worker mode can start the packet-pinned Audacity executable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from youtube_automation.audio.audacity_readiness_probe import (  # noqa: E402
    AUDACITY_EXE,
    AUDACITY_EXE_SHA256,
    ProbeAbort,
    run_worker_request,
    validate_live_authorization,
)
from youtube_automation.core.process_supervisor import _direct_python_executable  # noqa: E402

_WORKER_BOOTSTRAP = r"""
import json, os, sys, time
site_packages = os.path.abspath(sys.argv[1])
script = os.path.abspath(sys.argv[2])
worker_args = sys.argv[3:]
try:
    run_dir = worker_args[worker_args.index("--run-dir") + 1]
except (ValueError, IndexError):
    raise SystemExit("worker_run_dir_missing")
ready_path = os.path.join(run_dir, "job_ready")
deadline = time.monotonic() + 5.0
while not os.path.exists(ready_path):
    if time.monotonic() >= deadline:
        raise SystemExit("worker_startup_ack_timeout")
    time.sleep(0.01)
if os.path.islink(ready_path) or os.path.getsize(ready_path) > 4096:
    raise SystemExit("worker_startup_ack_invalid")
with open(ready_path, "rb") as stream:
    ready = json.loads(stream.read(4097))
if (not isinstance(ready, dict) or type(ready.get("schema")) is not int
        or ready["schema"] != 1 or type(ready.get("worker_pid")) is not int
        or ready["worker_pid"] != os.getpid()):
    raise SystemExit("worker_startup_identity_mismatch")
venv_root = os.path.dirname(os.path.dirname(site_packages))
base_prefix = sys.base_prefix
if not os.path.isfile(os.path.join(venv_root, "pyvenv.cfg")):
    raise SystemExit("worker_venv_config_missing")
sys.prefix = sys.exec_prefix = venv_root
system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
if not system_root or not os.path.isabs(system_root):
    raise SystemExit("worker_system_root_missing")
environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE")
               if key in os.environ}
environment["SystemRoot"] = environment["WINDIR"] = system_root
safe_path = [os.path.dirname(sys.executable), os.path.join(venv_root, "Scripts"),
             os.path.join(system_root, "System32"), system_root]
environment["PATH"] = os.pathsep.join(path for path in safe_path if os.path.isdir(path))
os.environ.clear()
os.environ.update(environment)
import site
base_site = os.path.normcase(os.path.realpath(os.path.join(base_prefix, "Lib", "site-packages")))
sys.path[:] = [path for path in sys.path
               if os.path.normcase(os.path.realpath(path or os.curdir)) != base_site]
site.addsitedir(site_packages)
if os.path.normcase(os.path.realpath(site_packages)) not in {
    os.path.normcase(os.path.realpath(path)) for path in sys.path
}:
    raise SystemExit("worker_venv_site_missing")
sys.argv = [script, *worker_args]
import runpy
runpy.run_path(script, run_name="__main__")
"""


def _worker_launch_diagnostic() -> int:
    import importlib

    dependencies = {}
    for name in ("psutil", "numpy"):
        try:
            module = importlib.import_module(name)
            dependencies[name] = {
                "file": getattr(module, "__file__", None),
                "version": getattr(module, "__version__", None),
            }
        except Exception as exc:
            dependencies[name] = {"error": type(exc).__name__}
    print(json.dumps({
        "pid": os.getpid(),
        "executable": sys.executable,
        "prefix": sys.prefix,
        "exec_prefix": sys.exec_prefix,
        "base_prefix": sys.base_prefix,
        "base_exec_prefix": sys.base_exec_prefix,
        "dependencies": dependencies,
    }, sort_keys=True))
    return 0


def _read_run_id(authorization_file: str | Path) -> str:
    path = Path(authorization_file)
    try:
        if path.is_symlink() or path.stat().st_size > 16_384:
            raise ValueError
        value = json.loads(path.read_text(encoding="utf-8"))
        run_id = value.get("run_id") if isinstance(value, dict) else None
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{7,95}", run_id):
            raise ValueError
        return run_id
    except Exception:
        raise ProbeAbort("authorization_file_invalid") from None


def _worker_command(run_dir: Path, request_json: str) -> list[str]:
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    venv_config = Path(sys.prefix) / "pyvenv.cfg"
    if not site_packages.is_dir() or not venv_config.is_file():
        raise ProbeAbort("worker_environment_invalid")
    try:
        config = venv_config.read_text(encoding="utf-8")
    except OSError:
        raise ProbeAbort("worker_environment_invalid") from None
    if any(line.strip().lower() == "include-system-site-packages = true"
           for line in config.splitlines()):
        raise ProbeAbort("worker_environment_invalid")
    return [
        _direct_python_executable(),
        "-I",
        "-S",
        "-B",
        "-c",
        _WORKER_BOOTSTRAP,
        str(site_packages),
        str(Path(__file__).resolve()),
        "--worker",
        "--run-dir",
        str(run_dir),
        "--request-json",
        request_json,
    ]


def _controller(args: argparse.Namespace) -> int:
    if not args.execute_live or not args.authorization_file:
        print(json.dumps({"ok": False, "reason": "live_execution_not_authorized"}))
        return 2
    try:
        run_id = _read_run_id(args.authorization_file)
        validate_live_authorization(
            args.authorization_file,
            run_id=run_id,
            executable_sha256=AUDACITY_EXE_SHA256,
        )
        if args.executable and Path(args.executable).resolve() != AUDACITY_EXE.resolve():
            raise ProbeAbort("executable_path_not_packet_target")
        if os.name != "nt":
            raise ProbeAbort("native_audacity_probe_requires_windows")

        run_dir = ROOT / ".runtime" / "a4_audacity_help_once" / run_id
        request = {
            "schema": 1,
            "run_id": run_id,
            "authorized_by_parent": True,
            "executable": str(AUDACITY_EXE),
            "executable_sha256": AUDACITY_EXE_SHA256,
        }
        request_json = json.dumps(request, sort_keys=True, separators=(",", ":"))

        from youtube_automation.core.process_supervisor import supervise_one_help
        from youtube_automation.production.ledger import leased_resource, resource_database

        with leased_resource(resource_database(), "audacity"):
            receipt = supervise_one_help(_worker_command(run_dir, request_json), run_dir)
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt.get("outcome") == "success" else 2
    except ProbeAbort as exc:
        print(json.dumps({"ok": False, "command_count": exc.command_count, "reason": exc.reason}))
        return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": f"controller_error:{type(exc).__name__}"}))
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one separately authorized Audacity Help probe")
    parser.add_argument("--execute-live", action="store_true", help="requires a separate one-launch/one-Help grant")
    parser.add_argument("--authorization-file")
    parser.add_argument("--executable")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--launcher-diagnostic", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-dir")
    parser.add_argument("--request-json")
    args = parser.parse_args(argv)
    if args.worker:
        if not args.run_dir or not args.request_json:
            print(json.dumps({"ok": False, "reason": "worker_arguments_missing"}))
            return 2
        return run_worker_request(args.run_dir, args.request_json)
    if args.launcher_diagnostic:
        return _worker_launch_diagnostic()
    return _controller(args)


if __name__ == "__main__":
    raise SystemExit(main())
