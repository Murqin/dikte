#!/usr/bin/env python3
"""Dikte: press Ctrl+Space, talk, press again to transcribe, clean up and paste.

Usage:
  dikte.py               run in the background (tray icon)
  dikte.py toggle        start / stop recording
  dikte.py cancel        discard the current recording
  dikte.py settings      open the settings window
  dikte.py restart       reload the running instance
  dikte.py quit          shut the application down
"""

import os
import sys

# A Wayland client cannot place a window in a screen corner, so the indicator
# is drawn through XWayland.
if os.environ.get("XDG_SESSION_TYPE") == "wayland" and os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PyQt6.QtCore import QTimer, QElapsedTimer  # noqa: E402
from PyQt6.QtGui import QAction, QIcon  # noqa: E402
from PyQt6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon  # noqa: E402

import audio  # noqa: E402
import config as cfg  # noqa: E402
import hotkey  # noqa: E402
from i18n import t  # noqa: E402
from overlay import Overlay  # noqa: E402
from settings_ui import SettingsWindow  # noqa: E402
from worker import Pipeline  # noqa: E402

SERVER_NAME = "dikte-" + str(os.getuid())
IDLE, RECORDING, BUSY = "idle", "recording", "busy"


class Dikte:
    def __init__(self, app):
        self.app = app
        self.conf = cfg.Config()
        self.state = IDLE
        self.settings_window = None

        self.overlay = Overlay(self.conf["overlay_corner"])
        self.recorder = audio.Recorder()
        self.pipeline = Pipeline(self.conf)
        self.evdev = hotkey.EvdevHotkey()

        self.recorder.level.connect(self.overlay.push_level)
        self.recorder.stopped.connect(self._on_recorded)
        self.recorder.failed.connect(self._on_error)
        self.pipeline.stage.connect(self.overlay.show_busy)
        self.pipeline.finished.connect(self._on_finished)
        self.pipeline.failed.connect(self._on_error)
        self.evdev.triggered.connect(self.toggle)
        self.evdev.failed.connect(self._on_error)

        self.elapsed = QElapsedTimer()
        self.last_toggle = QElapsedTimer()
        self.ticker = QTimer()
        self.ticker.setInterval(100)
        self.ticker.timeout.connect(self._tick)

        self.tray = QSystemTrayIcon()
        self._apply_settings()
        self.tray.show()

    # ---- tray ----------------------------------------------------------

    def _build_tray(self):
        # Keep menu and actions on self: PyQt does not take ownership when they
        # are only passed to addAction(), and garbage collection eats them.
        self.menu = QMenu()
        self.toggle_action = QAction(t("Start recording"), self.menu)
        self.toggle_action.triggered.connect(self.toggle)
        self.menu.addAction(self.toggle_action)

        self.cancel_action = QAction(t("Cancel recording"), self.menu)
        self.cancel_action.triggered.connect(self.cancel)
        self.cancel_action.setEnabled(False)
        self.menu.addAction(self.cancel_action)
        self.menu.addSeparator()

        self.settings_action = QAction(t("Settings…"), self.menu)
        self.settings_action.triggered.connect(self.open_settings)
        self.menu.addAction(self.settings_action)

        self.restart_action = QAction(t("Restart"), self.menu)
        self.restart_action.triggered.connect(self.restart)
        self.menu.addAction(self.restart_action)
        self.menu.addSeparator()

        self.quit_action = QAction(t("Quit"), self.menu)
        self.quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(self.quit_action)

        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip(t("Dikte: ready"))
        self.tray.activated.connect(self._tray_clicked)
        self._set_icon("audio-input-microphone")

    def _tray_clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle()

    def _set_icon(self, name):
        icon = QIcon.fromTheme(name)
        if icon.isNull():
            icon = QIcon.fromTheme("audio-input-microphone")
        self.tray.setIcon(icon)

    # ---- state ----------------------------------------------------------

    def _set_state(self, state):
        self.state = state
        labels = {
            IDLE: ("Start recording", "audio-input-microphone", "Dikte: ready"),
            RECORDING: ("Stop and transcribe", "media-record", "Dikte: recording"),
            BUSY: ("Working…", "view-refresh", "Dikte: working"),
        }
        label, icon, tip = labels[state]
        self.toggle_action.setText(t(label))
        self.toggle_action.setEnabled(state != BUSY)
        self.cancel_action.setEnabled(state == RECORDING)
        self._set_icon(icon)
        self.tray.setToolTip(t(tip))

    # ---- actions ---------------------------------------------------------

    def toggle(self):
        # With both the KDE shortcut and the built-in listener active the key
        # arrives twice; swallow the immediate repeat.
        if self.last_toggle.isValid() and self.last_toggle.elapsed() < 400:
            return
        self.last_toggle.restart()

        if self.state == IDLE:
            self.start()
        elif self.state == RECORDING:
            self.stop()
        # requests during BUSY are ignored

    def start(self):
        if self.state != IDLE:
            return
        self.overlay.show_recording()
        self.elapsed.restart()
        self.ticker.start()
        self._set_state(RECORDING)
        self.recorder.start(self.conf["mic_target"], self.conf["max_seconds"])

    def stop(self):
        if self.state != RECORDING:
            return
        self.ticker.stop()
        self._set_state(BUSY)
        self.overlay.show_busy(t("Transcribing…"))
        self.recorder.stop()

    def cancel(self):
        if self.state != RECORDING:
            return
        self.ticker.stop()
        self.recorder.cancel()
        self.overlay.dismiss()
        self._set_state(IDLE)

    def _tick(self):
        seconds = self.elapsed.elapsed() / 1000.0
        self.overlay.set_seconds(seconds)
        if seconds >= self.conf["max_seconds"]:
            self.stop()

    def _on_recorded(self, wav_path, duration, rms_values):
        self.pipeline.run(wav_path, duration, rms_values)

    def _on_finished(self, _raw, text, warning):
        if warning:
            # The text was still pasted, but cleanup did not run. Say so loudly:
            # a rejected key otherwise looks exactly like working dictation.
            self.overlay.show_warning(
                t("Pasted raw, cleanup failed: {error}", error=warning.splitlines()[0])
            )
            self.tray.showMessage(
                t("Dikte: cleanup failed"), warning,
                QSystemTrayIcon.MessageIcon.Warning, 10000,
            )
        else:
            preview = text.replace("\n", " ")
            preview = preview[:48] + ("…" if len(preview) > 48 else "")
            action = t("Pasted") if self.conf["auto_paste"] else t("Copied")
            self.overlay.show_done(t("{action}: {preview}", action=action, preview=preview))
        self._set_state(IDLE)

    def _on_error(self, message):
        first_line = message.strip().splitlines()[0]
        self.overlay.show_error(first_line)
        if len(message) > len(first_line):
            self.tray.showMessage("Dikte", message, QSystemTrayIcon.MessageIcon.Warning, 8000)
        if self.state == RECORDING:
            self.ticker.stop()
        self._set_state(IDLE)

    # ---- settings ---------------------------------------------------------

    def open_settings(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self.conf, launch_command())
            self.settings_window.applied.connect(self._apply_settings)
            self.settings_window.finished.connect(self._settings_closed)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _settings_closed(self, *_):
        # Don't drop the object while its own signal is still being delivered.
        QTimer.singleShot(0, lambda: setattr(self, "settings_window", None))

    def _apply_settings(self):
        self.overlay.corner = self.conf["overlay_corner"]
        self._build_tray()
        self._set_state(self.state)
        if self.conf["evdev_hotkey"]:
            self.evdev.start(self.conf["shortcut"])
        else:
            self.evdev.stop()

    def restart(self):
        """Replace this process with a fresh one, picking up code and settings."""
        if self.settings_window is not None:
            self.settings_window.close()
        self.shutdown()
        QLocalServer.removeServer(SERVER_NAME)
        script = os.path.realpath(__file__)
        os.execv(sys.executable, [sys.executable, script])

    def shutdown(self):
        self.evdev.stop()
        if self.state == RECORDING:
            self.recorder.cancel()
        self.overlay.dismiss()
        self.tray.hide()


def launch_command():
    """The command the KDE shortcut will run."""
    return f"{sys.executable} {os.path.realpath(__file__)} toggle"


def send_command(command, timeout=800):
    """Hand a command to the running instance; False when there is none."""
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(timeout):
        return False
    socket.write(command.encode("utf-8"))
    socket.flush()
    socket.waitForBytesWritten(timeout)
    socket.disconnectFromServer()
    return True


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    command = args[0] if args else ""

    if command and command not in ("toggle", "cancel", "settings", "restart",
                                   "quit", "start", "stop"):
        print(__doc__)
        return 2

    app = QApplication(sys.argv)
    app.setApplicationName("Dikte")
    app.setDesktopFileName("dikte")
    app.setQuitOnLastWindowClosed(False)

    # No command and an instance already running: bring its settings forward.
    if send_command(command or "settings"):
        return 0

    if command in ("cancel", "quit", "stop", "restart"):
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("dikte: no system tray found, running anyway")

    dikte = Dikte(app)

    server = QLocalServer()
    # Qt puts the socket in /tmp, so keep it to this user: commands like
    # "quit" should not be reachable by anyone else on the machine.
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    QLocalServer.removeServer(SERVER_NAME)
    if not server.listen(SERVER_NAME):
        print(f"dikte: could not open the IPC socket: {server.errorString()}")

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def read():
            payload = bytes(conn.readAll()).decode("utf-8", "replace").strip()
            handler = {
                "toggle": dikte.toggle,
                "start": dikte.start,
                "stop": dikte.stop,
                "cancel": dikte.cancel,
                "settings": dikte.open_settings,
                "restart": dikte.restart,
                "quit": app.quit,
            }.get(payload)
            if handler:
                handler()
            conn.disconnectFromServer()

        conn.readyRead.connect(read)

    server.newConnection.connect(on_connection)
    app.aboutToQuit.connect(dikte.shutdown)

    if command == "settings" or not dikte.conf.openai_key():
        dikte.open_settings()
    elif command == "toggle":
        QTimer.singleShot(0, dikte.toggle)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
