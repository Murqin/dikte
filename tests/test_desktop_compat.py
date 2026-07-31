import os
import unittest
from unittest import mock

import audio
import hotkey
import paste


class AudioBackendTests(unittest.TestCase):
    def test_parec_is_preferred(self):
        with mock.patch.object(audio.shutil, "which", side_effect=lambda cmd: f"/usr/bin/{cmd}"):
            self.assertEqual(audio.recording_command()[0], "parec")

    def test_pw_record_remains_the_fallback(self):
        with mock.patch.object(
            audio.shutil, "which", side_effect=lambda cmd: "/usr/bin/pw-record"
            if cmd == "pw-record" else None,
        ):
            self.assertEqual(audio.recording_command()[0], "pw-record")


class DesktopBackendTests(unittest.TestCase):
    def test_x11_uses_xclip(self):
        result = mock.Mock(returncode=0)
        with mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"}), \
             mock.patch.object(paste.shutil, "which", return_value="/usr/bin/xclip"), \
             mock.patch.object(paste.subprocess, "run", return_value=result) as run:
            paste.copy("hello")
        self.assertEqual(run.call_args.args[0][:3],
                         ["xclip", "-selection", "clipboard"])

    def test_x11_uses_xdotool(self):
        result = mock.Mock(returncode=0, stderr="")
        with mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"}), \
             mock.patch.object(paste.shutil, "which", return_value="/usr/bin/xdotool"), \
             mock.patch.object(paste.time, "sleep"), \
             mock.patch.object(paste.subprocess, "run", return_value=result) as run:
            paste.press("ctrl+shift+v")
        self.assertEqual(run.call_args.args[0],
                         ["xdotool", "key", "--clearmodifiers", "ctrl+shift+v"])


class GnomeShortcutTests(unittest.TestCase):
    def test_accelerator_round_trip(self):
        accelerator = hotkey.gnome_accelerator("Ctrl+Alt+A")
        self.assertEqual(accelerator, "<Primary><Alt>a")
        self.assertEqual(hotkey.display_accelerator(accelerator), "Ctrl+Alt+A")

    def test_empty_gsettings_array(self):
        self.assertEqual(hotkey._gsettings_array("@as []"), [])


if __name__ == "__main__":
    unittest.main()
