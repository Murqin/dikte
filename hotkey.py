"""Global shortcut: KDE custom-shortcut installation plus a built-in evdev listener."""

import glob
import os
import pathlib
import re
import select
import struct
import subprocess
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from i18n import t

DESKTOP_ID = "dikte-toggle.desktop"
DESKTOP_FILE = pathlib.Path.home() / ".local/share/applications" / DESKTOP_ID
SHORTCUTS_FILE = pathlib.Path.home() / ".config/kglobalshortcutsrc"

# --- evdev key codes (linux/input-event-codes.h) --------------------------

EV_KEY = 0x01
KEYS = {
    "space": 57, "tab": 15, "enter": 28, "return": 28, "esc": 1, "escape": 1,
    "backspace": 14, "insert": 110, "delete": 111, "home": 102, "end": 107,
    "pgup": 104, "pgdown": 109, "up": 103, "down": 108, "left": 105, "right": 106,
    "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
    "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22, "i": 23, "o": 24,
    "p": 25, "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35, "j": 36, "k": 37,
    "l": 38, "z": 44, "x": 45, "c": 46, "v": 47, "b": 48, "n": 49, "m": 50,
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64, "f7": 65, "f8": 66,
    "f9": 67, "f10": 68, "f11": 87, "f12": 88,
}
MODS = {
    "ctrl": (29, 97), "control": (29, 97),
    "shift": (42, 54),
    "alt": (56, 100),
    "meta": (125, 126), "super": (125, 126),
}
ALL_MOD_CODES = {code for pair in MODS.values() for code in pair}


def parse_shortcut(text):
    """'Ctrl+Space' -> ({'ctrl'}, 57), or (None, None) when unparsable."""
    parts = [p.strip().lower() for p in str(text).split("+") if p.strip()]
    if not parts:
        return None, None
    mods, key = set(), None
    for part in parts:
        if part in MODS:
            mods.add("ctrl" if part == "control" else "super" if part == "meta" else part)
        else:
            key = KEYS.get(part)
            if key is None:
                return None, None
    if key is None:
        return None, None
    return mods, key


# --- built-in listener ----------------------------------------------------

class EvdevHotkey(QObject):
    """Catches a global shortcut by reading /dev/input directly.

    It does not swallow the key; the focused application sees the combination
    too. This is the fallback that works before the KDE shortcut goes live.
    """

    triggered = pyqtSignal()
    failed = pyqtSignal(str)

    EVENT_FMT = "llHHi"
    EVENT_SIZE = struct.calcsize(EVENT_FMT)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._stop = threading.Event()
        self._mods = set()
        self._key = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, shortcut):
        self.stop()
        mods, key = parse_shortcut(shortcut)
        if key is None:
            self.failed.emit(t("Could not parse the shortcut: {shortcut}", shortcut=shortcut))
            return False
        devices = self._open_devices()
        if not devices:
            self.failed.emit(t(
                "Cannot read /dev/input. Your user needs to be in the 'input' group:\n"
                "  sudo usermod -aG input $USER   (then log out and back in)"
            ))
            return False
        self._mods, self._key = mods, key
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, args=(devices,), daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.5)
        self._thread = None

    def _open_devices(self):
        fds = []
        for path in sorted(glob.glob("/dev/input/event*")):
            try:
                fds.append(os.open(path, os.O_RDONLY | os.O_NONBLOCK))
            except OSError:
                continue
        return fds

    def _loop(self, fds):
        held = set()
        try:
            while not self._stop.is_set():
                ready, _, _ = select.select(fds, [], [], 0.4)
                for fd in ready:
                    try:
                        data = os.read(fd, self.EVENT_SIZE * 64)
                    except (BlockingIOError, OSError):
                        continue
                    for offset in range(0, len(data) - self.EVENT_SIZE + 1, self.EVENT_SIZE):
                        _s, _us, etype, code, value = struct.unpack(
                            self.EVENT_FMT, data[offset:offset + self.EVENT_SIZE]
                        )
                        if etype != EV_KEY:
                            continue
                        if code in ALL_MOD_CODES:
                            held.add(code) if value else held.discard(code)
                        elif code == self._key and value == 1:
                            if self._mods_match(held):
                                self.triggered.emit()
        finally:
            for fd in fds:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def _mods_match(self, held):
        for name, codes in MODS.items():
            if name in ("control", "super"):
                continue
            canonical = "ctrl" if name == "control" else name
            pressed = any(code in held for code in codes)
            if pressed != (canonical in self._mods):
                return False
        return True


# --- KDE custom shortcut --------------------------------------------------

def install_kde_shortcut(shortcut, exec_command, name="Dikte: start/stop recording"):
    """Write the desktop file and the kglobalshortcutsrc entry.

    KWin only reads that file at startup, so the entry goes live after the next
    login. Returns (True, message) or (False, error).
    """
    try:
        DESKTOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        DESKTOP_FILE.write_text(
            "[Desktop Entry]\n"
            f"Exec={exec_command}\n"
            f"Name={name}\n"
            "NoDisplay=true\n"
            "StartupNotify=false\n"
            "Type=Application\n"
            "X-KDE-GlobalAccel-CommandShortcut=true\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return False, t("Could not write the desktop file: {error}", error=exc)

    try:
        subprocess.run(
            ["kwriteconfig6", "--notify", "--file", "kglobalshortcutsrc",
             "--group", "services", "--group", DESKTOP_ID,
             "--key", "_launch", shortcut],
            capture_output=True, text=True, timeout=10, check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return False, t("Could not write kglobalshortcutsrc: {error}", error=exc)

    return True, t(
        "Shortcut saved: {shortcut}\nKWin only reads this file at startup, so it "
        "will not fire until you log out and back in. To use it right away, turn "
        "on the built-in listener.",
        shortcut=shortcut,
    )


def remove_kde_shortcut():
    try:
        DESKTOP_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        subprocess.run(
            ["kwriteconfig6", "--notify", "--file", "kglobalshortcutsrc",
             "--group", "services", "--group", DESKTOP_ID, "--key", "_launch", "--delete"],
            capture_output=True, timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        pass


def kde_shortcut_status():
    """The registered shortcut, or None."""
    if not DESKTOP_FILE.exists():
        return None
    try:
        text = SHORTCUTS_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(
        r"\[services\]\[" + re.escape(DESKTOP_ID) + r"\]\n_launch=([^\n]*)", text
    )
    if not match:
        return None
    value = match.group(1).split("\t")[0].strip()
    return value or None


def conflicting_shortcuts(shortcut):
    """Names of other KDE entries bound to the same combination."""
    try:
        text = SHORTCUTS_FILE.read_text(encoding="utf-8")
    except OSError:
        return []
    hits, section = [], ""
    for line in text.splitlines():
        if line.startswith("["):
            section = line.strip("[]").replace("][", " / ")
            continue
        if "=" not in line or DESKTOP_ID in section:
            continue
        key, _, value = line.partition("=")
        if shortcut.lower() in value.lower().split(","):
            hits.append(f"{section} → {key}")
        elif any(shortcut.lower() == part.strip().lower()
                 for part in re.split(r"[,\t]", value)):
            hits.append(f"{section} → {key}")
    return hits
