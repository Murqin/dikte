# Dikte

Press `Ctrl+Space`, talk, press again. The recording goes to OpenAI for
transcription, a model on OpenRouter cleans it up (dropping the *uh*s, the
restarts, the missing punctuation), and the result lands in your clipboard and
is pasted into whatever window you were typing in.

Built for KDE Plasma 6 on Wayland. No dependencies beyond system packages:
just the Python standard library and PyQt6.

*[Türkçe README](README.tr.md)*

<p align="center">
  <img src="docs/settings-general.webp" width="820" alt="Dikte settings, General tab">
</p>

|  |  |
|---|---|
| <img src="docs/settings-api.webp" width="410" alt="API and models"> | <img src="docs/settings-cleanup.webp" width="410" alt="Cleanup rules"> |
| <img src="docs/settings-audio-file.webp" width="410" alt="Audio file"> | <img src="docs/settings-history.webp" width="410" alt="History"> |

## Install

```sh
sudo pacman -S --needed pipewire-audio wl-clipboard ydotool ffmpeg python-pyqt6
systemctl --user enable --now ydotool     # needed for auto-paste

./install.sh                 # or:  ./install.sh "Ctrl+Alt+Space"
dikte                        # the settings window opens on first run
```

`install.sh` adds the `dikte` command, a menu entry, an autostart entry and the
KDE shortcut.

Two keys go in the settings window: **OpenAI** for speech to text
(`gpt-4o-transcribe`) and **OpenRouter** for the cleanup
(`google/gemini-3.5-flash-lite` by default, any model on the list works). They
fall back to `OPENAI_API_KEY` and `OPENROUTER_API_KEY`, and are stored in
`~/.config/dikte/config.json`, mode 600. Cleanup can be switched off, in which
case the raw transcript is pasted.

## Using it

| What | How |
| --- | --- |
| Start / stop recording | `Ctrl+Space`, or click the tray icon |
| Cancel a recording | Tray menu → *Cancel recording*, or `dikte cancel` |
| Settings | Tray menu → *Settings*, or `dikte settings` |
| Reload after an update | Tray menu → *Restart*, or `dikte restart` |
| Quit | Tray menu → *Quit*, or `dikte quit` |

An indicator in the screen corner shows a red dot, a live waveform and the
elapsed time, then the stage it is on. It never takes focus. Pressing
`Ctrl+Space` again while Dikte is still working does nothing; nothing queues up.

## What it does

- **Silence never reaches the API.** Handed near-silence, a transcription model
  invents a sentence instead of returning nothing ("Thanks for watching", or in
  Turkish "Altyazı M.K."). A recording is dropped when nothing rose 10 dB above
  *that recording's own* noise floor for at least 0.3 s, which is also what
  removes steady fan noise however loud, or when its loud end sits below
  -55 dBFS. The indicator reports the level it measured, which is what you
  calibrate the threshold against.
- **Misheard words are repaired.** Speech models fail phonetically on proper
  nouns, so the cleanup model is asked to fix those from context, and to leave
  the word alone when the context does not make the intended one clear. The names
  you list under Cleanup rules go to the transcription model as a hint and to the
  cleanup model as a glossary, which is what lets it recognise "kuber netis":

  ```
  raw    ıı bugün şey kuber netis üzerinde çalışan servisleri güncelledim
         yani sonra grafanada bir panel açtım hani ve pay kut ile arayüzü
         şey bitirdim işte

  result Bugün Kubernetes üzerinde çalışan servisleri güncelledim. Sonra
         Grafana'da bir panel açtım ve PyQt ile arayüzü bitirdim.
  ```
- **A failed cleanup is never silent.** The raw transcript is still pasted so the
  dictation is not lost, but the indicator turns amber with the reason instead of
  looking like a normal run.
- **Audio and video files** run through the same models under Settings → Audio
  file, optionally with `[mm:ss]` timestamps, chunked through ffmpeg when long.
- **History** of every dictation under Settings → History, with a size limit and
  right-click to delete.
- **Turkish and English interface**, following the system locale by default.

## The global shortcut needs one logout

KWin only reads `kglobalshortcutsrc` at startup, so the shortcut `install.sh`
writes will not fire until you log out and back in. Until then, Settings →
Shortcut → **built-in listener** reads `/dev/input` and catches the combination
itself. The difference: it does not swallow the key, so `Ctrl+Space` also reaches
the focused application (some editors will pop up autocomplete). The listener
needs your user in the `input` group: `sudo usermod -aG input $USER`.

## Layout

```
dikte.py          entry point, tray icon, state machine, IPC
audio.py          raw PCM capture through pw-record plus the level meter
api.py            OpenAI transcription and OpenRouter cleanup (stdlib only)
worker.py         transcribe → clean up → clipboard → paste
vad.py            deciding whether a recording holds speech at all
filetranscribe.py file transcription: ffmpeg, chunking, timestamps
overlay.py        the corner indicator
settings_ui.py    settings window
hotkey.py         KDE shortcut installation and the evdev listener
paste.py          wl-clipboard and ydotool wrappers
i18n.py           the string table
```

The indicator is drawn through XWayland, because a Wayland client cannot place a
window in a screen corner; `dikte.py` sets `QT_QPA_PLATFORM=xcb` for that.

## License

GPL-3.0, see [LICENSE](LICENSE).
