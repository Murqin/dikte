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
./install.sh                 # or:  ./install.sh "Ctrl+Alt+Space"
dikte                        # the settings window opens on first run
```

System packages (Arch/CachyOS):

```sh
sudo pacman -S --needed pipewire-audio wl-clipboard ydotool ffmpeg python-pyqt6
systemctl --user enable --now ydotool     # needed for auto-paste
```

Two API keys go in the settings window:

- **OpenAI**: speech to text (`gpt-4o-transcribe`). Falls back to the
  `OPENAI_API_KEY` environment variable when left empty.
- **OpenRouter**: transcript cleanup (`google/gemini-3.5-flash-lite` by
  default, any model on the list works). Falls back to `OPENROUTER_API_KEY`.
  Cleanup can be switched off entirely, in which case the raw transcript is
  pasted.

## Using it

| What | How |
| --- | --- |
| Start / stop recording | `Ctrl+Space`, or click the tray icon |
| Cancel a recording | Tray menu → *Cancel recording*, or `dikte cancel` |
| Settings | Tray menu → *Settings*, or `dikte settings` |
| Quit | Tray menu → *Quit*, or `dikte quit` |

While recording, a small indicator sits in the bottom-left corner of the
screen: a red dot, a live waveform, the elapsed time. Then it walks through
"Transcribing…", "Cleaning up…" and finally shows the first line of what it
pasted. The indicator never takes focus, so you stay in the window you were
working in.

## Silence never reaches the API

Handed near-silence, a transcription model does not return an empty string.
It invents one. Whisper is notorious for answering a quiet two seconds with
"Thanks for watching" or, in Turkish, "Altyazı M.K.". An accidental
`Ctrl+Space` would otherwise cost you an API call and paste a sentence you
never said.

Dikte checks before spending the call, and the check is relative rather than
absolute, because microphone gain varies far too much between machines for a
fixed threshold to mean anything. A recording is dropped when any of these holds:

- the loud end of it sits below the absolute floor (default -55 dBFS);
- nothing rose 10 dB above *this recording's own* noise floor for at least
  0.3 s, which is also what removes steady fan or hiss, however loud;
- the level never moved at all near the floor.

When something slips through anyway, a second filter catches the handful of
stock phrases the models fall back on, but only for clips under six seconds,
so a genuine "thanks for watching the demo" survives.

The indicator reports the level it measured (`No speech detected (-56 dB)`),
which is what you calibrate the threshold against if your microphone is
unusually quiet or unusually noisy.

## Transcribing a file

Settings → **Audio file** takes any audio or video file and runs it through the
same models. Two options, both remembered between runs:

- **Add timestamps**: prefixes every segment with `[mm:ss]`. This switches to
  `whisper-1`, the only model that returns segment times.
- **Run the cleanup model afterwards**: same cleanup as live dictation, with an
  extra rule telling the model to leave the timestamps alone.

Long files are converted to 16 kHz mono with ffmpeg and split into ten-minute
chunks, each transcribed in turn with its timestamps shifted into place. The
result can be copied or saved as `.txt`.

## About the global shortcut

KWin only reads `kglobalshortcutsrc` at startup. `install.sh` writes the
shortcut to the right place, but **it will not fire until you log out and back
in.** Two ways around that:

1. Log out and in. This is the clean solution: the key is swallowed by KWin,
   so it never leaks into other applications.
2. Settings → Shortcut → turn on the **built-in listener**. It reads
   `/dev/input` and catches the combination itself, working immediately. The
   difference: it does not swallow the key, so `Ctrl+Space` also reaches the
   focused application (some editors will pop up autocomplete). If that bothers
   you, change the shortcut to something like `Ctrl+Alt+Space`.

The built-in listener needs your user to be in the `input` group:
`sudo usermod -aG input $USER`.

## Settings

Stored in `~/.config/dikte/config.json`, mode 600, since the API keys live there.

| Setting | What it does |
| --- | --- |
| Interface language | Turkish, English, or follow the system locale |
| Microphone | Pick a specific source or use the default |
| Speech language | Language hint for transcription, or automatic detection |
| Paste key | `ctrl+v` / `ctrl+shift+v` / `shift+insert`. Terminals usually want the second |
| Restore clipboard | Puts your previous clipboard back after pasting |
| Skip silent recordings | Drops recordings with no speech before any API call, see above |
| Cleanup rules | The system prompt handed to the cleanup model. This is where you decide how much it may touch your words |
| Transcription hint | Names and terms you use often, so they get spelled correctly |
| Keep audio files | WAVs are kept in `~/.local/share/dikte/recordings` |

History lives in `~/.local/share/dikte/history.jsonl`; the last 200 entries are
browsable under Settings → History.

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

## Known limits

- The indicator is drawn through XWayland, because a Wayland client cannot
  place a window in a screen corner. `dikte.py` sets `QT_QPA_PLATFORM=xcb` for
  this reason.
- Auto-paste goes through `ydotool`'s virtual keyboard. Without a running
  `ydotoold` the text is only copied, and the indicator says so.
- Shortcut presses during "Transcribing…" are ignored.

## License

GPL-3.0, see [LICENSE](LICENSE).
