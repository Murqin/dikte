"""Clipboard (wl-clipboard) and key injection (ydotool)."""

import shutil
import subprocess
import time

from i18n import t

# Linux input event codes (linux/input-event-codes.h)
KEYCODES = {
    "ctrl": 29, "control": 29, "shift": 42, "alt": 56, "super": 125, "meta": 125,
    "v": 47, "insert": 110, "enter": 28, "return": 28,
}


class PasteError(Exception):
    pass


def read_clipboard():
    if not shutil.which("wl-paste"):
        return None
    try:
        res = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, timeout=5)
    except (subprocess.SubprocessError, OSError):
        return None
    return res.stdout if res.returncode == 0 else None


def _run_wl_copy(payload):
    """wl-copy forks to keep owning the selection; leaving its pipes open makes
    subprocess.run wait for EOF forever, hence DEVNULL."""
    return subprocess.run(
        ["wl-copy"],
        input=payload,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )


def copy(text):
    if not shutil.which("wl-copy"):
        raise PasteError(t("wl-copy not found. Install wl-clipboard."))
    try:
        res = _run_wl_copy(text.encode("utf-8"))
    except (subprocess.SubprocessError, OSError) as exc:
        raise PasteError(t("Could not copy to clipboard: {error}", error=exc)) from exc
    if res.returncode != 0:
        raise PasteError(t("wl-copy exited with code {code}.", code=res.returncode))


def copy_bytes(data):
    if data is None or not shutil.which("wl-copy"):
        return
    try:
        _run_wl_copy(data)
    except (subprocess.SubprocessError, OSError):
        pass


def ydotool_ready():
    return shutil.which("ydotool") is not None


def press(shortcut="ctrl+v", delay=0.12):
    """Press a key combination through ydotool, e.g. 'ctrl+v'."""
    if not ydotool_ready():
        raise PasteError(t("ydotool not found — cannot paste automatically."))

    codes = []
    for key in (k.strip().lower() for k in shortcut.split("+") if k.strip()):
        code = KEYCODES.get(key)
        if code is None:
            raise PasteError(t("Unknown key: {key}", key=key))
        codes.append(code)

    seq = [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
    time.sleep(delay)  # let the selection settle and focus come back
    try:
        res = subprocess.run(["ydotool", "key", *seq], capture_output=True,
                             text=True, timeout=10)
    except (subprocess.SubprocessError, OSError) as exc:
        raise PasteError(t("Could not run ydotool: {error}", error=exc)) from exc
    if res.returncode != 0:
        raise PasteError(t(
            "ydotool failed: {error}\nIs ydotoold running? "
            "(systemctl --user status ydotool)",
            error=res.stderr.strip() or "unknown error",
        ))
