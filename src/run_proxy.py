from __future__ import annotations
 
import json
import shutil
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
 
 
def main() -> int:
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
    return subprocess.call(command, cwd=str(ROOT))
 
 
if __name__ == "__main__":
    raise SystemExit(main())