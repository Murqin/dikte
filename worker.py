"""The dictation chain: transcribe → clean up → clipboard → paste."""

import os
import shutil
import sys
import threading
import time
import traceback

from PyQt6.QtCore import QObject, pyqtSignal

import api
import audio
import config as cfg
import paste
import vad
from i18n import t

CHUNK_SECONDS = audio.CHUNK_FRAMES / audio.RATE


class Pipeline(QObject):
    stage = pyqtSignal(str)          # human-readable progress line
    finished = pyqtSignal(str, str, str)  # raw transcript, final text, warning
    failed = pyqtSignal(str)

    def __init__(self, conf, parent=None):
        super().__init__(parent)
        self.conf = conf
        self._thread = None

    @property
    def busy(self):
        return self._thread is not None and self._thread.is_alive()

    def run(self, wav_path, duration, rms_values=()):
        if self.busy:
            return
        self._thread = threading.Thread(
            target=self._work, args=(wav_path, duration, list(rms_values)), daemon=True
        )
        self._thread.start()

    def _work(self, wav_path, duration, rms_values):
        conf = self.conf
        started = time.monotonic()
        raw = ""

        # Room tone only: don't spend an API call, and don't invite a
        # hallucinated sentence back.
        if conf["skip_silent"]:
            stats = vad.analyse(rms_values, CHUNK_SECONDS, conf["speech_margin_db"])
            if vad.is_silent(stats, conf["silence_db"], conf["speech_margin_db"],
                             conf["min_voiced_seconds"]):
                self._discard(wav_path)
                self.failed.emit(
                    t("No speech detected ({level} dB)", level=round(stats["speech_db"]))
                )
                return

        try:
            self.stage.emit(t("Transcribing…"))
            target = conf.transcribe_target()
            raw = api.transcribe(
                target,
                wav_path,
                language=conf["language"],
                prompt=conf["transcribe_prompt"],
            )

            if conf["filter_hallucinations"] and vad.looks_like_hallucination(raw, duration):
                self._discard(wav_path)
                self.failed.emit(t("Discarded a stock phrase: “{text}”", text=raw[:60]))
                return

            text = raw
            warning = ""
            if conf["cleanup_enabled"]:
                self.stage.emit(t("Cleaning up…"))
                try:
                    text = api.cleanup(
                        raw,
                        conf.openrouter_key(),
                        conf["cleanup_model"],
                        conf.cleanup_prompt(),
                        reasoning=conf["cleanup_reasoning"],
                        base_url=conf["openrouter_base_url"],
                    )
                except api.ApiError as exc:
                    # Keep the transcript, but never let the failure pass unseen:
                    # a rejected key would otherwise look like working dictation.
                    text = raw
                    warning = str(exc)
                    print(f"dikte: cleanup failed: {exc}", file=sys.stderr)

            previous = paste.read_clipboard() if conf["restore_clipboard"] else None
            paste.copy(text)

            if conf["auto_paste"]:
                self.stage.emit(t("Pasting…"))
                paste.press(conf["paste_shortcut"])
                if previous is not None:
                    time.sleep(0.35)
                    paste.copy_bytes(previous)

            cfg.append_history({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "duration": round(duration, 1),
                "elapsed": round(time.monotonic() - started, 1),
                "model": target.model,
                "cleanup_model": conf["cleanup_model"] if conf["cleanup_enabled"] else "",
                "cleanup_error": warning,
                "raw": raw,
                "text": text,
            })
            try:
                cfg.trim_history(conf["history_limit"])
            except OSError as exc:
                print(f"dikte: could not trim the history: {exc}", file=sys.stderr)
            self.finished.emit(raw, text, warning)

        except (api.ApiError, paste.PasteError) as exc:
            print(f"dikte: {exc}", file=sys.stderr)
            self.failed.emit(str(exc))
        except Exception as exc:  # never fail silently
            traceback.print_exc()
            self.failed.emit(t("Unexpected error: {error}", error=exc))
        finally:
            self._discard(wav_path)

    def _discard(self, wav_path):
        if not os.path.exists(wav_path):
            return
        if self.conf["keep_audio"]:
            try:
                cfg.RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
                shutil.move(wav_path, cfg.RECORDINGS_DIR / (time.strftime("%Y%m%d-%H%M%S") + ".wav"))
                return
            except OSError:
                pass
        try:
            os.unlink(wav_path)
        except OSError:
            pass
