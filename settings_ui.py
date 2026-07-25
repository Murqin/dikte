"""Settings window."""

import os
import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

import api
import audio
import config as cfg
import hotkey
from filetranscribe import FileTranscriber
from i18n import t

UI_LANGUAGES = [("Automatic (system)", "auto"), ("Turkish", "tr"), ("English", "en")]
LANGUAGES = [
    ("Detect automatically", "auto"), ("Turkish", "tr"), ("English", "en"),
    ("German", "de"), ("French", "fr"), ("Spanish", "es"), ("Arabic", "ar"),
]
CORNERS = ["bottom-left", "bottom-right", "top-left", "top-right"]
TRANSCRIBE_MODELS = ["gpt-4o-transcribe", "gpt-4o-mini-transcribe", "whisper-1"]
CLEANUP_MODELS = [
    "google/gemini-3.5-flash-lite", "google/gemini-3.1-flash-lite",
    "google/gemini-2.5-flash-lite", "anthropic/claude-haiku-4.5",
    "openai/gpt-5-mini", "meta-llama/llama-3.3-70b-instruct",
]
PASTE_SHORTCUTS = ["ctrl+v", "ctrl+shift+v", "shift+insert"]
AUDIO_FILTER = ("*.mp3 *.wav *.m4a *.ogg *.opus *.flac *.aac *.wma "
                "*.mp4 *.mkv *.webm *.mov *.avi")


class SettingsWindow(QDialog):
    applied = pyqtSignal()

    _models_loaded = pyqtSignal(list, str)
    _test_done = pyqtSignal(bool, str)

    def __init__(self, conf, launch_command, parent=None):
        super().__init__(parent)
        self.conf = conf
        self.launch_command = launch_command
        self.transcriber = FileTranscriber(conf, self)
        self.setWindowTitle(t("Dikte Settings"))
        self.resize(680, 640)

        tabs = QTabWidget(self)
        tabs.addTab(self._general_tab(), t("General"))
        tabs.addTab(self._api_tab(), t("API and models"))
        tabs.addTab(self._prompt_tab(), t("Cleanup rules"))
        tabs.addTab(self._file_tab(), t("Audio file"))
        tabs.addTab(self._shortcut_tab(), t("Shortcut"))
        tabs.addTab(self._history_tab(), t("History"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(t("Save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("Cancel"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

        self._models_loaded.connect(self._on_models_loaded)
        self._test_done.connect(self._on_test_done)
        self.transcriber.progress.connect(self._on_file_progress)
        self.transcriber.finished.connect(self._on_file_finished)
        self.transcriber.failed.connect(self._on_file_failed)
        self._load()

    # ---- tabs ----------------------------------------------------------

    def _general_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        self.ui_language = QComboBox()
        for label, code in UI_LANGUAGES:
            self.ui_language.addItem(t(label), code)
        self.ui_language.setToolTip(
            t("Restart Dikte for the language change to reach every window.")
        )
        form.addRow(t("Interface language"), self.ui_language)

        self.mic = QComboBox()
        self.mic.addItem(t("Default microphone"), "")
        for name, desc in audio.list_sources():
            self.mic.addItem(desc, name)
        form.addRow(t("Microphone"), self.mic)

        self.language = QComboBox()
        for label, code in LANGUAGES:
            self.language.addItem(t(label), code)
        form.addRow(t("Speech language"), self.language)

        self.auto_paste = QCheckBox(t("Paste the text into the focused window"))
        form.addRow("", self.auto_paste)

        self.paste_shortcut = QComboBox()
        self.paste_shortcut.addItems(PASTE_SHORTCUTS)
        self.paste_shortcut.setToolTip(
            t("Terminals usually want ctrl+shift+v. Change this if pasting does nothing.")
        )
        form.addRow(t("Paste key"), self.paste_shortcut)

        self.restore_clipboard = QCheckBox(t("Restore the previous clipboard after pasting"))
        form.addRow("", self.restore_clipboard)

        self.corner = QComboBox()
        for value in CORNERS:
            self.corner.addItem(t(value), value)
        form.addRow(t("Indicator corner"), self.corner)

        self.max_seconds = QSpinBox()
        self.max_seconds.setRange(10, 3600)
        self.max_seconds.setSuffix(t(" s"))
        form.addRow(t("Longest recording"), self.max_seconds)

        self.skip_silent = QCheckBox(t("Skip silent recordings (don't call the API)"))
        form.addRow("", self.skip_silent)

        self.silence_db = QSpinBox()
        self.silence_db.setRange(-80, -20)
        self.silence_db.setSuffix(" dB")
        self.silence_db.setToolTip(t(
            "Speech also has to rise {margin} dB above the recording's own noise "
            "floor, so this absolute floor rarely needs touching. Lower it if quiet "
            "speech gets dropped; raise it if noise still gets through.",
            margin=10,
        ))
        form.addRow(t("Silence threshold"), self.silence_db)

        self.filter_hallucinations = QCheckBox(
            t("Discard stock phrases models invent for near-silent audio")
        )
        self.filter_hallucinations.setToolTip(
            t("Whisper answers silence with things like “Thanks for watching”.")
        )
        form.addRow("", self.filter_hallucinations)

        self.keep_audio = QCheckBox(t("Keep audio files (~/.local/share/dikte/recordings)"))
        form.addRow("", self.keep_audio)
        return page

    def _api_tab(self):
        page = QWidget()
        outer = QVBoxLayout(page)

        oai = QGroupBox(t("OpenAI: speech to text"))
        oai_form = QFormLayout(oai)
        self.openai_key = QLineEdit()
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key.setPlaceholderText(t("sk-… (falls back to OPENAI_API_KEY)"))
        oai_form.addRow(t("API key"), self.openai_key)

        self.transcribe_model = QComboBox()
        self.transcribe_model.setEditable(True)
        self.transcribe_model.addItems(TRANSCRIBE_MODELS)
        oai_form.addRow(t("Model"), self.transcribe_model)

        self.test_button = QPushButton(t("Test key"))
        self.test_button.clicked.connect(self._test_openai)
        self.test_label = QLabel("")
        self.test_label.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(self.test_button)
        row.addWidget(self.test_label, 1)
        oai_form.addRow("", self._wrap(row))
        outer.addWidget(oai)

        orr = QGroupBox(t("OpenRouter: transcript cleanup"))
        orr_form = QFormLayout(orr)
        self.cleanup_enabled = QCheckBox(t("Clean the transcript with a model"))
        orr_form.addRow("", self.cleanup_enabled)

        self.openrouter_key = QLineEdit()
        self.openrouter_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openrouter_key.setPlaceholderText(t("sk-or-… (falls back to OPENROUTER_API_KEY)"))
        orr_form.addRow(t("API key"), self.openrouter_key)

        self.cleanup_model = QComboBox()
        self.cleanup_model.setEditable(True)
        self.cleanup_model.addItems(CLEANUP_MODELS)
        self.refresh_models = QPushButton(t("Fetch model list"))
        self.refresh_models.clicked.connect(self._load_models)
        model_row = QHBoxLayout()
        model_row.addWidget(self.cleanup_model, 1)
        model_row.addWidget(self.refresh_models)
        orr_form.addRow(t("Model"), self._wrap(model_row))

        self.models_label = QLabel("")
        self.models_label.setWordWrap(True)
        orr_form.addRow("", self.models_label)
        outer.addWidget(orr)
        outer.addStretch(1)
        return page

    def _prompt_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel(t("System instruction given to the cleanup model. This is where "
                         "you decide how much it may touch your words."))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.cleanup_prompt = QPlainTextEdit()
        layout.addWidget(self.cleanup_prompt, 1)

        reset = QPushButton(t("Reset to default"))
        reset.clicked.connect(
            lambda: self.cleanup_prompt.setPlainText(cfg.default_cleanup_prompt())
        )
        layout.addWidget(reset, 0, Qt.AlignmentFlag.AlignRight)

        hint = QLabel(t("Transcription hint (optional): names and terms you say often. "
                        "Helps Whisper spell them correctly."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.transcribe_prompt = QPlainTextEdit()
        self.transcribe_prompt.setMaximumHeight(90)
        layout.addWidget(self.transcribe_prompt)
        return page

    def _file_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel(t("Transcribe an existing audio or video file with the same models."))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        pick = QPushButton(t("Choose file…"))
        pick.clicked.connect(self._choose_file)
        self.file_label = QLabel(t("No file selected"))
        self.file_label.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(pick)
        row.addWidget(self.file_label, 1)
        layout.addLayout(row)

        self.file_timestamps = QCheckBox(t("Add timestamps"))
        self.file_timestamps.setToolTip(
            t("Prefixes every segment with [mm:ss]. Uses whisper-1, the only model "
              "that returns segment times.")
        )
        layout.addWidget(self.file_timestamps)

        self.file_cleanup = QCheckBox(t("Run the cleanup model afterwards"))
        layout.addWidget(self.file_cleanup)

        self.file_run = QPushButton(t("Transcribe"))
        self.file_run.clicked.connect(self._run_file)
        self.file_stop = QPushButton(t("Stop"))
        self.file_stop.clicked.connect(self.transcriber.stop)
        self.file_stop.setEnabled(False)
        run_row = QHBoxLayout()
        run_row.addWidget(self.file_run)
        run_row.addWidget(self.file_stop)
        run_row.addStretch(1)
        layout.addLayout(run_row)

        self.file_status = QLabel("")
        self.file_status.setWordWrap(True)
        layout.addWidget(self.file_status)

        self.file_output = QPlainTextEdit()
        self.file_output.setPlaceholderText("…")
        layout.addWidget(self.file_output, 1)

        copy = QPushButton(t("Copy"))
        copy.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self.file_output.toPlainText())
        )
        save = QPushButton(t("Save as .txt"))
        save.clicked.connect(self._save_transcript)
        out_row = QHBoxLayout()
        out_row.addWidget(copy)
        out_row.addWidget(save)
        out_row.addStretch(1)
        layout.addLayout(out_row)
        return page

    def _shortcut_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.shortcut = QLineEdit()
        self.shortcut.setPlaceholderText("Ctrl+Space")
        form.addRow(t("Shortcut"), self.shortcut)
        layout.addLayout(form)

        install = QPushButton(t("Install as a KDE shortcut"))
        install.clicked.connect(self._install_shortcut)
        remove = QPushButton(t("Remove"))
        remove.clicked.connect(self._remove_shortcut)
        row = QHBoxLayout()
        row.addWidget(install)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)

        self.shortcut_status = QLabel("")
        self.shortcut_status.setWordWrap(True)
        layout.addWidget(self.shortcut_status)

        self.evdev_enabled = QCheckBox(t(
            "Use the built-in listener (/dev/input), for when the KDE shortcut is "
            "not active yet"
        ))
        self.evdev_enabled.setToolTip(t(
            "Works immediately, no session restart. The only difference: the key "
            "combination also reaches the focused application."
        ))
        layout.addWidget(self.evdev_enabled)

        note = QLabel(t(
            "KWin only reads shortcut settings at startup. After 'Install' the "
            "shortcut shows up under System Settings → Shortcuts, but it will not "
            "fire until you log out and back in. Until then, use the built-in listener."
        ))
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _history_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.history = QListWidget()
        self.history.setWordWrap(True)
        layout.addWidget(self.history, 1)

        copy = QPushButton(t("Copy selected to clipboard"))
        copy.clicked.connect(self._copy_history)
        reload_ = QPushButton(t("Reload"))
        reload_.clicked.connect(self._load_history)
        row = QHBoxLayout()
        row.addWidget(copy)
        row.addWidget(reload_)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    @staticmethod
    def _wrap(layout):
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    # ---- load / save ----------------------------------------------------

    def _load(self):
        conf = self.conf
        self._select_data(self.ui_language, conf["ui_language"])
        self._select_data(self.mic, conf["mic_target"])
        self._select_data(self.language, conf["language"])
        self.auto_paste.setChecked(conf["auto_paste"])
        self.paste_shortcut.setCurrentText(conf["paste_shortcut"])
        self.restore_clipboard.setChecked(conf["restore_clipboard"])
        self._select_data(self.corner, conf["overlay_corner"])
        self.max_seconds.setValue(conf["max_seconds"])
        self.skip_silent.setChecked(conf["skip_silent"])
        self.silence_db.setValue(int(conf["silence_db"]))
        self.filter_hallucinations.setChecked(conf["filter_hallucinations"])
        self.keep_audio.setChecked(conf["keep_audio"])

        self.openai_key.setText(conf["openai_api_key"])
        self.transcribe_model.setCurrentText(conf["transcribe_model"])
        self.cleanup_enabled.setChecked(conf["cleanup_enabled"])
        self.openrouter_key.setText(conf["openrouter_api_key"])
        self.cleanup_model.setCurrentText(conf["cleanup_model"])
        self.cleanup_prompt.setPlainText(conf["cleanup_prompt"] or cfg.default_cleanup_prompt())
        self.transcribe_prompt.setPlainText(conf["transcribe_prompt"])

        self.file_timestamps.setChecked(conf["file_timestamps"])
        self.file_cleanup.setChecked(conf["file_cleanup"])
        self.file_path = ""

        self.shortcut.setText(conf["shortcut"])
        self.evdev_enabled.setChecked(conf["evdev_hotkey"])

        self._refresh_shortcut_status()
        self._load_history()

    def _save(self):
        conf = self.conf
        conf["ui_language"] = self.ui_language.currentData() or "auto"
        conf["mic_target"] = self.mic.currentData() or ""
        conf["language"] = self.language.currentData() or "auto"
        conf["auto_paste"] = self.auto_paste.isChecked()
        conf["paste_shortcut"] = self.paste_shortcut.currentText().strip()
        conf["restore_clipboard"] = self.restore_clipboard.isChecked()
        conf["overlay_corner"] = self.corner.currentData() or "bottom-left"
        conf["max_seconds"] = self.max_seconds.value()
        conf["skip_silent"] = self.skip_silent.isChecked()
        conf["silence_db"] = float(self.silence_db.value())
        conf["filter_hallucinations"] = self.filter_hallucinations.isChecked()
        conf["keep_audio"] = self.keep_audio.isChecked()

        conf["openai_api_key"] = self.openai_key.text().strip()
        conf["transcribe_model"] = self.transcribe_model.currentText().strip()
        conf["cleanup_enabled"] = self.cleanup_enabled.isChecked()
        conf["openrouter_api_key"] = self.openrouter_key.text().strip()
        conf["cleanup_model"] = self.cleanup_model.currentText().strip()

        # Store an empty prompt when it matches the default, so switching the
        # interface language also switches the prompt language.
        prompt = self.cleanup_prompt.toPlainText().strip()
        conf["cleanup_prompt"] = "" if prompt == cfg.default_cleanup_prompt() else prompt
        conf["transcribe_prompt"] = self.transcribe_prompt.toPlainText().strip()

        conf["file_timestamps"] = self.file_timestamps.isChecked()
        conf["file_cleanup"] = self.file_cleanup.isChecked()

        conf["shortcut"] = self.shortcut.text().strip() or "Ctrl+Space"
        conf["evdev_hotkey"] = self.evdev_enabled.isChecked()
        conf.save()
        self.applied.emit()
        self.accept()

    @staticmethod
    def _select_data(combo, value):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    # ---- api helpers -----------------------------------------------------

    def _load_models(self):
        self.refresh_models.setEnabled(False)
        self.models_label.setText(t("Fetching model list…"))
        key = self.openrouter_key.text().strip() or self.conf.openrouter_key()

        def work():
            try:
                self._models_loaded.emit(api.openrouter_models(key), "")
            except api.ApiError as exc:
                self._models_loaded.emit([], str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_models_loaded(self, models, error):
        self.refresh_models.setEnabled(True)
        if error:
            self.models_label.setText(t("Could not fetch the list: {error}", error=error))
            return
        current = self.cleanup_model.currentText()
        self.cleanup_model.clear()
        self.cleanup_model.addItems(models)
        self.cleanup_model.setCurrentText(current)
        self.models_label.setText(t("{count} models loaded.", count=len(models)))

    def _test_openai(self):
        self.test_button.setEnabled(False)
        self.test_label.setText(t("Trying…"))
        key = self.openai_key.text().strip() or self.conf.openai_key()
        base = self.conf["openai_base_url"]

        def work():
            try:
                models = api.openai_models(key, base)
                self._test_done.emit(
                    True, t("Connection works. {count} audio models visible.", count=len(models))
                )
            except api.ApiError as exc:
                self._test_done.emit(False, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_test_done(self, ok, message):
        self.test_button.setEnabled(True)
        self.test_label.setText(("✓ " if ok else "✗ ") + message)

    # ---- audio file ------------------------------------------------------

    def _choose_file(self):
        start = self.conf["file_last_dir"] or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, t("Select an audio file"), start,
            f"{t('Audio and video files')} ({AUDIO_FILTER});;{t('All files')} (*)",
        )
        if not path:
            return
        self.file_path = path
        self.file_label.setText(os.path.basename(path))
        self.conf["file_last_dir"] = os.path.dirname(path)

    def _run_file(self):
        if not getattr(self, "file_path", "") or self.transcriber.busy:
            return
        self.file_output.clear()
        self.file_run.setEnabled(False)
        self.file_stop.setEnabled(True)
        self.transcriber.start(
            self.file_path,
            self.file_timestamps.isChecked(),
            self.file_cleanup.isChecked(),
        )

    def _on_file_progress(self, message):
        self.file_status.setText(message)
        if message == t("Stopped."):
            self._file_idle()

    def _on_file_finished(self, text):
        self.file_output.setPlainText(text)
        self.file_status.setText(t("Done: {chars} characters.", chars=len(text)))
        self._file_idle()

    def _on_file_failed(self, error):
        self.file_status.setText(t("Failed: {error}", error=error))
        self._file_idle()

    def _file_idle(self):
        self.file_run.setEnabled(True)
        self.file_stop.setEnabled(False)

    def _save_transcript(self):
        text = self.file_output.toPlainText()
        if not text:
            return
        base = os.path.splitext(os.path.basename(getattr(self, "file_path", "")))[0]
        start = os.path.join(self.conf["file_last_dir"] or os.path.expanduser("~"),
                             f"{base or 'transcript'}.txt")
        path, _ = QFileDialog.getSaveFileName(
            self, t("Save transcript"), start, f"{t('Text files')} (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            self.file_status.setText(t("Saved: {path}", path=path))
        except OSError as exc:
            self.file_status.setText(t("Failed: {error}", error=exc))

    # ---- shortcut --------------------------------------------------------

    def _install_shortcut(self):
        combo = self.shortcut.text().strip() or "Ctrl+Space"
        clashes = hotkey.conflicting_shortcuts(combo)
        if clashes:
            answer = QMessageBox.question(
                self, t("Shortcut conflict"),
                t("{shortcut} is also used by:\n\n{list}\n\nInstall anyway?",
                  shortcut=combo, list="\n".join(clashes[:6])),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        ok, message = hotkey.install_kde_shortcut(combo, self.launch_command)
        QMessageBox.information(self, t("Shortcut"), message)
        if ok:
            self.conf["shortcut"] = combo
            self.conf.save()
        self._refresh_shortcut_status()

    def _remove_shortcut(self):
        hotkey.remove_kde_shortcut()
        self._refresh_shortcut_status()

    def _refresh_shortcut_status(self):
        current = hotkey.kde_shortcut_status()
        self.shortcut_status.setText(
            t("Registered in KDE: {shortcut}", shortcut=current) if current
            else t("No KDE shortcut installed.")
        )

    # ---- history ---------------------------------------------------------

    def _load_history(self):
        self.history.clear()
        for row in reversed(cfg.read_history(200)):
            text = (row.get("text") or "").replace("\n", " ")
            preview = text[:110] + ("…" if len(text) > 110 else "")
            header = t("{ts}  ({duration} s)",
                       ts=row.get("ts", ""), duration=row.get("duration", 0))
            item = QListWidgetItem(f"{header}\n{preview}")
            item.setData(Qt.ItemDataRole.UserRole, row.get("text", ""))
            self.history.addItem(item)

    def _copy_history(self):
        item = self.history.currentItem()
        if item:
            QGuiApplication.clipboard().setText(item.data(Qt.ItemDataRole.UserRole))
