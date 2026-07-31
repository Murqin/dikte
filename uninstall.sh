#!/usr/bin/env bash
# Dikte uninstaller: takes back what install.sh put down, and nothing else
# unless asked. Your settings and your dictations survive a plain run; --purge
# is what deletes them.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/dikte"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/dikte"
# One per global shortcut: install.sh writes the first two, the settings window
# writes the other two when you ask it to.
DESKTOP_IDS=(dikte-toggle.desktop dikte-cancel.desktop dikte-meeting.desktop
             dikte-ask.desktop)

PURGE=0
ASSUME_YES=0

say()  { printf '  %s\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
gone() { printf '  \033[90m·\033[0m %s\n' "$1"; }
# "1 dictation", "3 dictations": how many is the point of printing it at all.
count() { (( $1 == 1 )) && printf '%s %s' "$1" "$2" || printf '%s %s' "$1" "$3"; }

usage() {
  cat <<EOF
Usage: ./uninstall.sh [--purge] [--yes]

  --purge   also delete the settings ($CONFIG_DIR)
            and the dictations, meetings and recordings ($DATA_DIR)
  --yes     do not ask before deleting those

Without --purge nothing you have written is touched, and the source directory
is left alone either way.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'uninstall.sh: unknown option: %s\n' "$arg" >&2; usage >&2; exit 2 ;;
  esac
done

# A symlink whose target is gone is still a file to remove, hence -L.
remove() {
  if [[ -e "$1" || -L "$1" ]]; then
    rm -f "$1"
    ok "Removed $1"
  else
    gone "Was not there: $1"
  fi
}

echo
echo "Uninstalling Dikte"
echo "──────────────────"

# 1. The running instance --------------------------------------------------
# It holds a tray icon and the global shortcuts; asking it to quit is tidier
# than pulling its launchers out from under it.
if pgrep -u "$USER" -f 'dikte\.py' >/dev/null 2>&1; then
  python3 "$DIR/dikte.py" quit >/dev/null 2>&1 || true
  sleep 0.5
  if pgrep -u "$USER" -f 'dikte\.py' >/dev/null 2>&1; then
    warn "Dikte is still running; close it from the tray icon"
  else
    ok "Stopped the running instance"
  fi
fi

# 2. Launchers -------------------------------------------------------------
# Only our own symlink goes: a file of the same name that somebody else put
# there is not ours to delete.
if [[ -L "$BIN_DIR/dikte" ]]; then
  remove "$BIN_DIR/dikte"
elif [[ -e "$BIN_DIR/dikte" ]]; then
  warn "$BIN_DIR/dikte is not our symlink, leaving it alone"
else
  gone "Was not there: $BIN_DIR/dikte"
fi
remove "$APP_DIR/dikte.desktop"
remove "$AUTOSTART_DIR/dikte.desktop"

# 3. KDE global shortcuts --------------------------------------------------
for id in "${DESKTOP_IDS[@]}"; do
  remove "$APP_DIR/$id"
done

if command -v kwriteconfig6 >/dev/null; then
  for id in "${DESKTOP_IDS[@]}"; do
    # kwriteconfig6 deletes keys, not groups, so both of the ones KDE keeps in
    # there go and the empty group is left behind harmlessly.
    for key in _launch _k_friendly_name; do
      kwriteconfig6 --notify --file kglobalshortcutsrc \
        --group services --group "$id" --key "$key" --delete 2>/dev/null || true
    done
  done
  ok "KDE shortcuts unregistered"
  say "KWin reads that file at startup, so the keys are free after your next login."
else
  warn "kwriteconfig6 not found. Remove the shortcuts in System Settings > Shortcuts"
fi

# 4. Settings and dictations -----------------------------------------------
echo
if ((PURGE)); then
  warn "--purge also deletes:"
  if [[ -f "$CONFIG_DIR/config.json" ]]; then
    say "$CONFIG_DIR/config.json  (your API keys and every setting)"
  fi
  if [[ -f "$DATA_DIR/history.jsonl" ]]; then
    say "$DATA_DIR/history.jsonl  ($(count "$(wc -l < "$DATA_DIR/history.jsonl")" dictation dictations))"
  fi
  if [[ -d "$DATA_DIR/meetings" ]]; then
    say "$DATA_DIR/meetings  ($(count "$(find "$DATA_DIR/meetings" -name '*.md' | wc -l)" meeting meetings))"
  fi
  if [[ -d "$DATA_DIR/recordings" ]]; then
    say "$DATA_DIR/recordings  ($(du -sh "$DATA_DIR/recordings" | cut -f1) of audio)"
  fi

  if ((!ASSUME_YES)); then
    if [[ -t 0 ]]; then
      printf '  Type yes to delete them: '
      read -r reply
      [[ "$reply" == "yes" ]] || { PURGE=0; say "Kept."; }
    else
      PURGE=0
      warn "Not a terminal, so nothing was deleted. Pass --yes if you meant it."
    fi
  fi
fi

if ((PURGE)); then
  rm -rf "$CONFIG_DIR" "$DATA_DIR"
  ok "Settings and dictations deleted"
else
  say "Settings kept:     $CONFIG_DIR"
  say "Dictations kept:   $DATA_DIR"
  say "Delete them too with:  ./uninstall.sh --purge"
fi

echo
ok "Done."
say "The source directory is untouched: $DIR"
echo
