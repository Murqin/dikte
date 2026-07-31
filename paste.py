"""Clipboard and key injection for Wayland and X11."""

import os
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
    command = (["xclip", "-selection", "clipboard", "-out"] if _x11()
               else ["wl-paste", "--no-newline"])
    if not shutil.which(command[0]):
        return None
    try:
        res = subprocess.run(command, capture_output=True, timeout=5)
    except (subprocess.SubprocessError, OSError):
        return None
    return res.stdout if res.returncode == 0 else None


def _run_copy(payload):
    """The clipboard owner may fork; do not leave inherited pipes open."""
    command = (["xclip", "-selection", "clipboard", "-in"] if _x11()
               else ["wl-copy"])
    return subprocess.run(
        command,
        input=payload,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )


def copy(text):
    tool = "xclip" if _x11() else "wl-copy"
    if not shutil.which(tool):
        raise PasteError(t("{tool} not found; clipboard copy is unavailable.", tool=tool))
    try:
        res = _run_copy(text.encode("utf-8"))
    except (subprocess.SubprocessError, OSError) as exc:
        raise PasteError(t("Could not copy to clipboard: {error}", error=exc)) from exc
    if res.returncode != 0:
        raise PasteError(t("{tool} exited with code {code}.",
                           tool=tool, code=res.returncode))


def copy_bytes(data):
    tool = "xclip" if _x11() else "wl-copy"
    if data is None or not shutil.which(tool):
        return
    try:
        _run_copy(data)
    except (subprocess.SubprocessError, OSError):
        pass


def ydotool_ready():
    tool = "xdotool" if _x11() else "ydotool"
    return shutil.which(tool) is not None


def _x11():
    return (os.environ.get("XDG_SESSION_TYPE") == "x11"
            or bool(os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")))


def press(shortcut="ctrl+v", delay=0.12):
    """Press a key combination through xdotool or ydotool."""
    if not ydotool_ready():
        tool = "xdotool" if _x11() else "ydotool"
        raise PasteError(t("{tool} not found, cannot paste automatically.", tool=tool))

    if _x11():
        key = shortcut.lower().replace("control", "ctrl")
        time.sleep(delay)
        try:
            res = subprocess.run(
                ["xdotool", "key", "--clearmodifiers", key],
                capture_output=True, text=True, timeout=10,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise PasteError(t("Could not run xdotool: {error}", error=exc)) from exc
        if res.returncode != 0:
            raise PasteError(t("xdotool failed: {error}",
                               error=res.stderr.strip() or "unknown error"))
        return

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
