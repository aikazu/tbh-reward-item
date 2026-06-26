from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
ADDON_PATH = ROOT / "tbh_reward_hook.py"


def load_port() -> int:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return 8877
    return int(data.get("listen_port", data.get("ListenPort", 8877)))


def _terminate(proc: subprocess.Popen) -> None:
    # Send SIGTERM to the whole process group so mitmdump + any child
    # threads release the listening socket. Escalate to SIGKILL if needed.
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
    def _handler(_signum: int, _frame: object) -> None:  # noqa: ARG001
        _terminate(proc)
        # Restore default so a second signal still hard-kills if cleanup hangs.
        signal.signal(_signum, signal.SIG_DFL)
        os.kill(os.getpid(), _signum)

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def main() -> int:
    from config_setup import ensure_config
    ensure_config(CONFIG_PATH)
    port = load_port()
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

    print(f"Starting quiet mitmproxy on 127.0.0.1:{port}")
    print("Only [TBH] addon messages are shown. Press Ctrl+C to stop.")

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