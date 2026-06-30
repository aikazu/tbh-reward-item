from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import cast


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
ADDON_PATH = ROOT / "tbh_reward_hook.py"


def load_port() -> int:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return 8877
    return int(data.get("listen_port", data.get("ListenPort", 8877)))


def load_mode(cli_mode: str | None = None, cli_name: str | None = None) -> tuple[str, str | None]:
    """Return ``(mode, process_name)`` from CLI overrides or config.json.

    mode is ``"regular"`` (default) or ``"local"``. For ``"local"`` the
    runner forwards ``--mode local:<process_name>`` to mitmdump, which
    spawns the named process and only intercepts its traffic.
    CLI args override config.json values.
    """
    if cli_mode is not None:
        if cli_mode == "local" and not (cli_name and cli_name.strip()):
            print("[warn] --mode local requires --name <process>; falling back to regular")
            return "regular", None
        return cli_mode, cli_name
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return "regular", None
    raw = str(data.get("mode", "regular")).strip().lower() or "regular"
    if raw not in {"regular", "local"}:
        print(f"[warn] config.json: unknown mode={raw!r}, falling back to regular")
        raw = "regular"
    name = data.get("local_process_name")
    if isinstance(name, str):
        name = name.strip() or None
    else:
        name = None
    if raw == "local" and not name:
        print("[warn] config.json: mode=local requires local_process_name; falling back to regular")
        raw = "regular"
    return raw, name


def _terminate(proc: subprocess.Popen) -> None:
    # Send SIGTERM to the whole process group so mitmdump + any child
    # threads release the listening socket. Escalate to SIGKILL if needed.
    #
    # Windows note: ``os.killpg`` is POSIX-only — calling it on Windows
    # raises NotImplementedError and would crash the signal handler that
    # invokes this function. The desktop app's Stop button uses
    # ``taskkill /T /F`` directly on this process's PID (see
    # ``tbh_desktop/proxy_runner.py``), so by the time any signal lands
    # here the tree is already gone. The only path that actually reaches
    # this function on Windows is Ctrl+C from a console, in which case
    # ``taskkill /T /F`` is the right primitive anyway.
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True,
            text=True,
        )
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _install_signal_handlers(proc: subprocess.Popen) -> None:
    # Default SIGTERM aborts the interpreter immediately, skipping `finally`
    # blocks — so when the desktop kills our process group, _terminate never
    # runs and mitmdump is left orphaned holding the port. Convert SIGTERM
    # and SIGINT into a clean KeyboardInterrupt-style exit instead.
    def _handler(*_args: object) -> None:
        signum = int(cast(int, _args[0])) if _args else int(signal.SIGTERM)
        _terminate(proc)
        # Restore default so a second signal still hard-kills if cleanup hangs.
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def main() -> int:
    from config_setup import ensure_config
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", choices=("regular", "local"), default=None)
    parser.add_argument("--name", default=None, help="process name for mode=local")
    args, _ = parser.parse_known_args()
    ensure_config(CONFIG_PATH)
    port = load_port()
    mode, local_name = load_mode(args.mode, args.name)
    common_args = [
        "-q",
        "-s",
        str(ADDON_PATH),
        "--listen-port",
        str(port),
        "--flow-detail",
        "0",
        "--set",
        "block_global=false",
    ]
    if mode == "local" and local_name:
        common_args[1:1] = ["--mode", f"local:{local_name}"]
        print(f"Spawning {local_name!r} with proxy auto-injected (mode=local)")
    else:
        print(f"Starting quiet mitmproxy on 127.0.0.1:{port}")
        print("Configure your client HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:8877")
    print("Only [TBH] addon messages are shown. Press Ctrl+C to stop.")

    mitmdump = shutil.which("mitmdump")
    if mitmdump:
        command = [mitmdump, *common_args]
    else:
        command = [
            sys.executable,
            "-c",
            "from mitmproxy.tools.main import mitmdump; mitmdump()",
            *common_args,
        ]

    # New session so mitmdump + its threads share a process group we can
    # signal together; otherwise Ctrl+C leaves a zombie holding the port.
    proc = subprocess.Popen(
        command,
        cwd=str(ROOT),
        start_new_session=True,
    )
    _install_signal_handlers(proc)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        return 130
    finally:
        _terminate(proc)
 
 
if __name__ == "__main__":
    raise SystemExit(main())