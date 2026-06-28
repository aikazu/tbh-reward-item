# tbh_desktop/linux_elevation.py
"""Handle root requirement for ``--mode local`` on Linux.

mitmproxy's local redirector (``--mode local:NAME``) uses a setuid helper
(``mitmproxy-linux-redirector``) that prompts for ``sudo`` at startup. When
launched from the GUI via ``subprocess.Popen`` there's no TTY, so the
prompt hangs and mitmdump never starts.

The cleanest fix: detect this case BEFORE the GUI even creates its main
window. If we're on Linux, ``mode=local`` is set in ``config.json``, and
the user is not root, re-exec the entire app under ``pkexec`` (polkit
password prompt). This mirrors the ``install_cert.sh`` /
``install_cert.bat`` pattern of auto-elevating privileged work, so the
user sees ONE familiar polkit dialog and the GUI launches fully working.

``pkexec`` is preferred over ``sudo`` because:
  - It uses polkit's native prompt (no terminal dependency)
  - KDE/GNOME users already have it integrated with their screen locker
  - It preserves ``$DISPLAY`` / ``$XAUTHORITY`` / ``$DBUS_SESSION_BUS_ADDRESS``
    so the elevated Qt process can attach to the existing desktop session
  - It is the standard pattern for desktop app elevation on Linux

If ``pkexec`` is unavailable (very rare — all major distros ship it),
fall back to a hard error pointing the user at the manual command from
README. We do NOT fall back to ``sudo`` because ``sudo`` without a TTY
is the exact bug we're trying to avoid.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        # Windows has no geteuid — treat as non-root (no elevation needed).
        return False


def _config_says_local_mode(config_path: Path) -> bool:
    """True if config.json's mode field is ``'local'`` with a process name."""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return False
    mode = str(data.get("mode", "regular")).strip().lower()
    if mode != "local":
        return False
    name = data.get("local_process_name")
    return isinstance(name, str) and bool(name.strip())


def needs_elevation(config_path: Path) -> bool:
    """Return True if the current process must re-exec under pkexec.

    Used at GUI launch time only. Reads ``config.json`` on disk.
    """
    if not _is_linux():
        return False
    if _is_root():
        return False
    if not _config_says_local_mode(config_path):
        return False
    return True


def runtime_needs_elevation(mode: str, name: str) -> bool:
    """Return True if a (mode, name) pair requires elevated execution.

    Used at Start-button-click time — the mode/name values come from
    the live editor, not from on-disk config. This is the right check
    to call from main_window._start() because the user may have
    switched from regular to local since launch, in which case
    on-disk config still says regular and needs_elevation() (which
    reads config.json) returns False.

    A pair needs elevation iff:
      - host is Linux
      - current process is not root
      - mode == "local"
      - name is non-empty (mitmdump needs a target process to spawn)
    """
    if not _is_linux():
        return False
    if _is_root():
        return False
    if mode != "local":
        return False
    if not name or not name.strip():
        return False
    return True


def request_elevation(repo_root: Path) -> int:
    """Re-exec the GUI under pkexec. Returns the child's exit code.

    This function is called from ``main.py`` BEFORE ``QApplication`` is
    created — we exec into a new Python process and never return unless
    pkexec failed.

    On success: pkexec replaces this process with the elevated one,
    and the elevated process's exit code is returned (caller should
    ``sys.exit(rc)`` with it).

    On failure: prints a clear error to stderr and returns 126 (or
    whatever pkexec itself returned).
    """
    pkexec = shutil.which("pkexec")
    if not pkexec:
        print(
            "[ERR] mode='local' on Linux requires root for mitmproxy's setuid helper,\n"
            "      but pkexec was not found on PATH. Install polkit (Arch: pacman -S polkit)\n"
            "      or run manually from a terminal:\n"
            f"        sudo -E {repo_root}/scripts/launch_desktop.sh",
            file=sys.stderr,
        )
        return 126

    # Re-exec under pkexec. NOTE: pkexec does NOT have a --env flag
    # (that was sudo's --preserve-env). pkexec sets a minimal safe
    # environment by design to prevent LD_LIBRARY_PATH / similar
    # injection attacks. To get our env back, wrap the call in `env`:
    #
    #   pkexec env VAR1="$VAR1" VAR2="$VAR2" -- python -m tbh_desktop.main
    #
    # `env` is coreutils and reads the shell's current values for the
    # named variables — they don't need to be quoted as literal strings,
    # they're expanded by env itself before exec.
    #
    # For run_proxy.py we only need HOME (CA cert at ~/.mitmproxy/),
    # PATH (so shebang / subprocess can find mitmdump), and Python's
    # own locations. We deliberately do NOT forward DISPLAY — pkexec
    # refuses GUI apps unless the polkit policy has
    # org.freedesktop.policykit.exec.allow_gui set, and we don't need
    # a display in run_proxy.py anyway.
    home = os.environ.get("HOME", "/root")
    path = os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    cmd = [
        pkexec,
        "env",
        f"HOME={home}",
        f"PATH={path}",
        sys.executable,
        "-m",
        "tbh_desktop.main",
    ]
    try:
        # Replace this process; the elevated child becomes the new GUI.
        # execvp replaces without fork on success, so this is safe before
        # any Qt resource has been created.
        os.execvp(cmd[0], cmd)
    except OSError as exc:
        print(f"[ERR] pkexec failed to launch: {exc}", file=sys.stderr)
        return 126

    # Unreachable: execvp only returns on failure.
    return 126  # pragma: no cover