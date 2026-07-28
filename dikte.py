#!/usr/bin/env python3
"""Dikte: press Ctrl+Space, talk, press again to transcribe, clean up and paste.

Usage:
  dikte.py               run in the background (tray icon)
  dikte.py toggle        start / stop recording
  dikte.py cancel        discard the current recording
  dikte.py ask           start / stop recording a command for Claude Code
  dikte.py ask-reset     forget the conversation Claude has been following
  dikte.py meeting       start / end a meeting recording
  dikte.py meeting-cancel  discard the meeting being recorded
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

import assistant  # noqa: E402
import audio  # noqa: E402
import config as cfg  # noqa: E402
import hotkey  # noqa: E402
import i18n  # noqa: E402
import meeting  # noqa: E402
from i18n import t  # noqa: E402
from meeting import MeetingPipeline  # noqa: E402
from overlay import Overlay  # noqa: E402
from settings_ui import SettingsWindow  # noqa: E402
from worker import Pipeline  # noqa: E402

SERVER_NAME = "dikte-" + str(os.getuid())
IDLE, RECORDING, BUSY = "idle", "recording", "busy"
# A meeting runs alongside dictation rather than through it: writing up an hour
# of audio takes minutes, and dictation should not be held hostage to it.
M_IDLE, M_RECORDING, M_WORKING = "idle", "recording", "working"

# The KDE shortcut answers a key press by launching a whole Python process, so
# its toggle lands well after the built-in listener has handled the same press.
# Anything arriving inside this window is that echo, not a second press.
ECHO_MS = 2000

# How long the indicator stays up at the start of a meeting. Long enough to see
# both halves of the waveform move, which is the one check that matters, and
# short enough not to sit in the corner for the rest of the hour.
PEEK_MS = 12000


class Dikte:
    def __init__(self, app):
        self.app = app
        self.conf = cfg.Config()
        self.state = IDLE
        # Dictation and a command for Claude share the recorder and the state
        # machine; which of the two is being recorded is decided when the
        # recording starts, and holds until it is finished with.
        self.ask_mode = False
        self.meeting_state = M_IDLE
        self.meeting_base = ""
        self.meeting_message = ""
        self.settings_window = None
        self._quitting = False

        self.overlay = Overlay(self.conf["overlay_corner"])
        self.recorder = audio.Recorder()
        self.pipeline = Pipeline(self.conf)
        self.meeting_recorder = audio.MeetingRecorder()
        self.meetings = MeetingPipeline(self.conf)
        self.evdev = hotkey.EvdevHotkey()

        self.recorder.level.connect(self.overlay.push_level)
        self.recorder.stopped.connect(self._on_recorded)
        self.recorder.failed.connect(self._on_error)
        self.pipeline.stage.connect(self.overlay.show_busy)
        self.pipeline.finished.connect(self._on_finished)
        self.pipeline.failed.connect(self._on_error)
        self.pipeline.cancelled.connect(self._on_cancelled)
        self.meeting_recorder.levels.connect(self._on_meeting_levels)
        self.meeting_recorder.stopped.connect(self._on_meeting_recorded)
        self.meeting_recorder.died.connect(self._on_meeting_died)
        self.meeting_recorder.failed.connect(self._on_meeting_error)
        self.meetings.progress.connect(self._on_meeting_progress)
        self.meetings.finished.connect(self._on_meeting_finished)
        self.meetings.failed.connect(self._on_meeting_failed)
        self.evdev.triggered.connect(self._on_evdev)
        self.evdev.failed.connect(self._on_error)

        self.elapsed = QElapsedTimer()
        self.meeting_elapsed = QElapsedTimer()
        self.last_toggle = QElapsedTimer()
        self.last_evdev = {}
        self.ticker = QTimer()
        self.ticker.setInterval(100)
        self.ticker.timeout.connect(self._tick)
        self.meeting_ticker = QTimer()
        self.meeting_ticker.setInterval(500)
        self.meeting_ticker.timeout.connect(self._meeting_tick)

        self.tray = QSystemTrayIcon()
        self._apply_settings()
        self.tray.show()

    # ---- tray ----------------------------------------------------------

    def _build_tray(self):
        # Keep menu and actions on self: PyQt does not take ownership when they
        # are only passed to addAction(), and garbage collection eats them.
        self.menu = QMenu()
        self.toggle_action = QAction(t("Start recording"), self.menu)
        self.toggle_action.triggered.connect(self._toggle)
        self.menu.addAction(self.toggle_action)

        self.ask_action = QAction(t("Ask Claude"), self.menu)
        self.ask_action.triggered.connect(self._toggle_ask)
        self.menu.addAction(self.ask_action)

        self.reset_action = QAction(t("Start a new conversation"), self.menu)
        self.reset_action.triggered.connect(self.reset_conversation)
        self.menu.addAction(self.reset_action)

        self.cancel_action = QAction(t("Cancel recording"), self.menu)
        self.cancel_action.triggered.connect(self.cancel)
        self.cancel_action.setEnabled(False)
        self.menu.addAction(self.cancel_action)
        self.menu.addSeparator()

        self.meeting_action = QAction(t("Record a meeting"), self.menu)
        self.meeting_action.triggered.connect(self._toggle_meeting)
        self.menu.addAction(self.meeting_action)

        self.meeting_cancel_action = QAction(t("Discard the meeting"), self.menu)
        self.meeting_cancel_action.triggered.connect(self.cancel_meeting)
        self.meeting_cancel_action.setEnabled(False)
        self.menu.addAction(self.meeting_cancel_action)
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
        if reason != QSystemTrayIcon.ActivationReason.Trigger:
            return
        # The icon ends whatever is being recorded rather than only a dictation.
        # The two shortcuts are each tied to their own mode, on purpose, but the
        # icon is one button: having it refuse to stop a recording it can see is
        # just a button that does nothing.
        if self.state == RECORDING and self.ask_mode:
            self._toggle_ask()
        else:
            self._toggle()

    def _set_icon(self, name):
        icon = QIcon.fromTheme(name)
        if icon.isNull():
            icon = QIcon.fromTheme("audio-input-microphone")
        self.tray.setIcon(icon)

    # ---- state ----------------------------------------------------------

    def _set_state(self, state):
        self.state = state
        if state == IDLE:
            self.ask_mode = False
        self._refresh_tray()

    def _set_meeting_state(self, state):
        self.meeting_state = state
        if state != M_WORKING:
            self.meeting_message = ""
        self._refresh_tray()

    def _refresh_tray(self):
        labels = {
            IDLE: ("Start recording", "audio-input-microphone", "Dikte: ready"),
            RECORDING: ("Stop and transcribe", "media-record", "Dikte: recording"),
            BUSY: ("Working…", "view-refresh", "Dikte: working"),
        }
        label, icon, tip = labels[self.state]
        agent = assistant.display_name(self.conf)
        if self.ask_mode:
            tip = "Dikte: talking to Claude"
            if self.state == RECORDING:
                label, tip = "Start recording", "Dikte: recording for Claude"
        self.toggle_action.setText(t(label))
        # Each of the two owns its own entry, so the one that is not recording
        # goes grey rather than offering to end a recording it did not start.
        self.toggle_action.setEnabled(
            self.state == IDLE or (self.state == RECORDING and not self.ask_mode)
        )
        asked = i18n.name(agent, "dative")
        self.ask_action.setText(
            t("Stop and ask {name}", name=asked)
            if self.state == RECORDING and self.ask_mode
            else t("Ask {name}", name=asked)
        )
        self.ask_action.setEnabled(
            self.state == IDLE or (self.state == RECORDING and self.ask_mode)
        )
        self.reset_action.setEnabled(self.state != BUSY)
        # A Claude command is the one job long enough to be worth calling off
        # once it is already running.
        self.cancel_action.setText(
            t("Stop {name}", name=i18n.name(agent, "accusative"))
            if self.state == BUSY and self.ask_mode
            else t("Cancel recording")
        )
        self.cancel_action.setEnabled(
            self.state == RECORDING or (self.state == BUSY and self.ask_mode)
        )

        meeting_labels = {
            M_IDLE: "Record a meeting",
            M_RECORDING: "End the meeting and write it up",
            M_WORKING: "Writing the meeting up…",
        }
        self.meeting_action.setText(t(meeting_labels[self.meeting_state]))
        self.meeting_action.setEnabled(self.meeting_state != M_WORKING)
        self.meeting_cancel_action.setEnabled(self.meeting_state == M_RECORDING)

        # Dictation owns the icon while it is doing something, because it is the
        # one you are waiting on; otherwise the meeting gets to speak.
        if self.state == IDLE and self.meeting_state != M_IDLE:
            if self.meeting_state == M_RECORDING:
                icon, tip = "media-record", t("Dikte: in a meeting")
            else:
                icon = "view-refresh"
                tip = self.meeting_message or t("Dikte: writing the meeting up")
            self._set_icon(icon)
            self.tray.setToolTip(tip)
            return
        self._set_icon(icon)
        self.tray.setToolTip(t(tip))

    # ---- actions ---------------------------------------------------------

    def toggle(self):
        """A toggle from outside this process: the KDE shortcut, or the CLI."""
        self._external("toggle", self._toggle)

    def toggle_ask(self):
        self._external("ask", self._toggle_ask)

    def toggle_meeting(self):
        self._external("meeting", self._toggle_meeting)

    def _external(self, name, handler):
        # The built-in listener sees the key press the instant it happens, so a
        # toggle arriving right behind one is the KDE shortcut catching up on
        # that same press. Its lateness is also the proof we were waiting for
        # that the shortcut is live, which leaves the listener with nothing to
        # do but double every press.
        timer = self.last_evdev.get(name)
        if self.evdev.running and timer is not None and timer.elapsed() < ECHO_MS:
            self._retire_listener()
            return
        handler()

    def _on_evdev(self, name):
        timer = self.last_evdev.get(name)
        if timer is None:
            timer = self.last_evdev[name] = QElapsedTimer()
        timer.restart()
        handlers = {"meeting": self._toggle_meeting, "ask": self._toggle_ask}
        handlers.get(name, self._toggle)()

    def _retire_listener(self):
        self.evdev.stop()
        self.conf["evdev_hotkey"] = False
        self.conf.save()
        self.tray.showMessage(
            "Dikte",
            t("The KDE shortcut is live now, so the built-in listener has been "
              "turned off. It was doubling every key press."),
            QSystemTrayIcon.MessageIcon.Information, 8000,
        )

    def _toggle(self):
        # Two /dev/input nodes can carry the same keyboard, and a menu click can
        # land on top of a key press; swallow the immediate repeat.
        if self._repeated():
            return
        if self.state == IDLE:
            self.start()
        elif self.state == RECORDING and not self.ask_mode:
            self.stop()
        # requests during BUSY, or for the other mode's recording, are ignored

    def _toggle_ask(self):
        if self._repeated():
            return
        if self.state == IDLE:
            self.start(ask=True)
        elif self.state == RECORDING and self.ask_mode:
            self.stop()

    def _repeated(self):
        if self.last_toggle.isValid() and self.last_toggle.elapsed() < 400:
            return True
        self.last_toggle.restart()
        return False

    def start(self, ask=False):
        if self.state != IDLE:
            return
        self.ask_mode = ask
        self.overlay.show_recording(asking=ask)
        self.elapsed.restart()
        self.ticker.start()
        self._set_state(RECORDING)
        self.recorder.start(self.conf["mic_target"], self.conf["max_seconds"])

    def start_ask(self):
        self.start(ask=True)

    def stop(self):
        if self.state != RECORDING:
            return
        self.ticker.stop()
        self._set_state(BUSY)
        self.overlay.show_busy(t("Transcribing…"))
        self.recorder.stop()

    def cancel(self):
        if self.state == BUSY:
            # Only a Claude command can be called off once it is under way, and
            # it says so itself when it lets go.
            if self.ask_mode:
                self.overlay.show_busy(t("Stopping…"))
                self.pipeline.cancel()
            return
        if self.state != RECORDING:
            return
        self.ticker.stop()
        self.recorder.cancel()
        self.overlay.dismiss()
        self._set_state(IDLE)

    def reset_conversation(self):
        """Drop the thread Claude has been following, so the next command starts
        a conversation of its own."""
        assistant.clear_session()
        self.overlay.show_done(
            t("{name} starts fresh next time.",
              name=assistant.display_name(self.conf)), 2500
        )

    def _tick(self):
        seconds = self.elapsed.elapsed() / 1000.0
        self.overlay.set_seconds(seconds)
        if seconds >= self.conf["max_seconds"]:
            self.stop()

    # ---- meetings ---------------------------------------------------------

    def _toggle_meeting(self):
        if self.meeting_state == M_IDLE:
            self.start_meeting()
        elif self.meeting_state == M_RECORDING:
            self.stop_meeting()

    def start_meeting(self):
        if self.meeting_state != M_IDLE:
            return
        base = meeting.new_base()
        _, wav_path = cfg.meeting_paths(base)
        self.meeting_recorder.start(
            str(wav_path),
            self.conf["meeting_mic_target"] or self.conf["mic_target"],
            self.conf["meeting_system_target"],
            self.conf["meeting_max_seconds"],
        )
        if not self.meeting_recorder.active:
            return  # start() has already said what went wrong
        self.meeting_base = base
        self.meeting_elapsed.restart()
        self.meeting_ticker.start()
        self.overlay.show_meeting()
        QTimer.singleShot(PEEK_MS, self._conceal_meeting_overlay)
        self._set_meeting_state(M_RECORDING)

    def stop_meeting(self):
        if self.meeting_state != M_RECORDING:
            return
        self.meeting_ticker.stop()
        self._set_meeting_state(M_WORKING)
        self.overlay.show_busy(t("Ending the meeting…"))
        self.meeting_recorder.stop()

    def cancel_meeting(self):
        if self.meeting_state != M_RECORDING:
            return
        self.meeting_ticker.stop()
        self.meeting_recorder.cancel()
        if self.overlay.state == "meeting":
            self.overlay.dismiss()
        self._set_meeting_state(M_IDLE)

    def _conceal_meeting_overlay(self):
        if self.overlay.state == "meeting":
            self.overlay.dismiss()

    def _on_meeting_levels(self, mine, theirs):
        self.overlay.push_levels(mine, theirs)

    def _meeting_tick(self):
        seconds = self.meeting_elapsed.elapsed() / 1000.0
        if self.overlay.state == "meeting":
            self.overlay.set_seconds(seconds)
        if self.state == IDLE:
            self.tray.setToolTip(
                t("Dikte: in a meeting ({time})", time=_clock(seconds))
            )
        if seconds >= self.conf["meeting_max_seconds"]:
            self.stop_meeting()

    def _on_meeting_recorded(self, path, duration):
        entry = meeting.new_entry(self.meeting_base, duration)
        try:
            cfg.save_meeting(entry)
        except OSError as exc:
            self._on_meeting_failed(entry["base"], str(exc))
            return
        # On the way out there is no time to write anything up; the recording is
        # on disk and listed, and the Minutes tab can pick it up next time.
        if self._quitting:
            return
        if not self.meetings.run(entry):
            self._set_meeting_state(M_IDLE)
            self.tray.showMessage(
                "Dikte",
                t("Recording saved. The previous meeting is still being written "
                  "up, so start this one from Settings → Minutes when it is done."),
                QSystemTrayIcon.MessageIcon.Information, 10000,
            )
            return
        self.overlay.show_done(t("Meeting recorded, writing it up…"), 4000)

    def _on_meeting_progress(self, _base, message):
        self.meeting_message = message
        if self.state == IDLE and self.meeting_state == M_WORKING:
            self.tray.setToolTip(message)

    def _on_meeting_finished(self, base, title):
        self._set_meeting_state(M_IDLE)
        doc_path, _ = cfg.meeting_paths(base)
        self.overlay.show_done(t("Meeting written up: {title}", title=title), 5000)
        self.tray.showMessage(
            t("Dikte: the meeting is written up"), f"{title}\n{doc_path}",
            QSystemTrayIcon.MessageIcon.Information, 10000,
        )

    def _on_meeting_failed(self, _base, error):
        self._set_meeting_state(M_IDLE)
        first_line = error.strip().splitlines()[0]
        self.overlay.show_error(t("Meeting failed: {error}", error=first_line))
        self.tray.showMessage(
            t("Dikte: the meeting could not be written up"),
            t("{error}\n\nThe recording has been kept. Settings → Minutes can "
              "try again.", error=error),
            QSystemTrayIcon.MessageIcon.Warning, 12000,
        )

    def _on_meeting_error(self, message):
        """The recorder itself could not run."""
        self.meeting_ticker.stop()
        if self.overlay.state == "meeting":
            self.overlay.dismiss()
        self._set_meeting_state(M_IDLE)
        self._on_error(message)

    def _on_meeting_died(self):
        if self.meeting_state != M_RECORDING:
            return
        self.tray.showMessage(
            "Dikte",
            t("The recording stopped on its own; the sound device may have gone "
              "away. Keeping what was captured."),
            QSystemTrayIcon.MessageIcon.Warning, 10000,
        )
        self.stop_meeting()

    def _on_recorded(self, wav_path, duration, rms_values):
        self.pipeline.run(wav_path, duration, rms_values, ask=self.ask_mode)

    def _on_finished(self, _raw, text, warning):
        asked = self.ask_mode
        agent = assistant.display_name(self.conf)
        if warning:
            # The text was still pasted, but something on the way did not run.
            # Say so loudly: a rejected key, or a tool Claude was not allowed to
            # touch, otherwise looks exactly like a job that worked.
            first_line = warning.splitlines()[0]
            self.overlay.show_warning(
                t("{name} answered, but: {error}", name=agent, error=first_line)
                if asked
                else t("Pasted raw, cleanup failed: {error}", error=first_line)
            )
            self.tray.showMessage(
                t("Dikte: {name} could not do all of it", name=agent) if asked
                else t("Dikte: cleanup failed"),
                f"{warning}\n\n{text}" if asked else warning,
                QSystemTrayIcon.MessageIcon.Warning, 10000,
            )
        else:
            preview = text.replace("\n", " ")
            preview = preview[:48] + ("…" if len(preview) > 48 else "")
            if asked:
                # Longer than a dictation's flash: this one is an answer, and
                # it is worth being able to read the start of it in the corner.
                self.overlay.show_done(
                    t("{name}: {preview}", name=agent, preview=preview), 6000
                )
            else:
                action = t("Pasted") if self.conf["auto_paste"] else t("Copied")
                self.overlay.show_done(
                    t("{action}: {preview}", action=action, preview=preview)
                )
        self._set_state(IDLE)

    def _on_cancelled(self):
        self.overlay.show_done(t("Stopped."), 2000)
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
            self.settings_window = SettingsWindow(
                self.conf, launch_command(), meeting_command(), self.meetings,
                ask_command(),
            )
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
        self._refresh_tray()
        if self.conf["evdev_hotkey"]:
            self.evdev.start({"toggle": self.conf["shortcut"],
                              "ask": self.conf["assistant_shortcut"],
                              "meeting": self.conf["meeting_shortcut"]})
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
        self._quitting = True
        self.evdev.stop()
        if self.state == RECORDING:
            self.recorder.cancel()
        # A meeting in progress is closed properly rather than thrown away: the
        # WAV ends up valid and listed, ready to be written up after the restart.
        if self.meeting_state == M_RECORDING:
            self.meeting_ticker.stop()
            self.meeting_recorder.stop()
        self.overlay.dismiss()
        self.tray.hide()


def _clock(seconds):
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return (f"{hours}:{minutes:02d}:{secs:02d}" if hours
            else f"{minutes}:{secs:02d}")


def launch_command():
    """The command the KDE shortcut will run."""
    return f"{sys.executable} {os.path.realpath(__file__)} toggle"


def meeting_command():
    return f"{sys.executable} {os.path.realpath(__file__)} meeting"


def ask_command():
    return f"{sys.executable} {os.path.realpath(__file__)} ask"


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
                                   "quit", "start", "stop", "ask", "ask-reset",
                                   "meeting", "meeting-cancel"):
        print(__doc__)
        return 2

    app = QApplication(sys.argv)
    app.setApplicationName("Dikte")
    app.setDesktopFileName("dikte")
    app.setQuitOnLastWindowClosed(False)

    # No command and an instance already running: bring its settings forward.
    if send_command(command or "settings"):
        return 0

    if command in ("cancel", "quit", "stop", "restart", "meeting-cancel",
                   "ask-reset"):
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
                "ask": dikte.toggle_ask,
                "ask-reset": dikte.reset_conversation,
                "meeting": dikte.toggle_meeting,
                "meeting-cancel": dikte.cancel_meeting,
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

    # No key for the chosen transcription provider means nothing can work yet,
    # so the settings window is the only useful thing to open.
    if command == "settings" or not dikte.conf.transcribe_target().api_key:
        dikte.open_settings()
    elif command == "toggle":
        QTimer.singleShot(0, dikte.toggle)
    elif command == "ask":
        QTimer.singleShot(0, dikte.toggle_ask)
    elif command == "meeting":
        QTimer.singleShot(0, dikte.toggle_meeting)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
