#!/usr/bin/env bash
# Dikte updater: pull, put the launchers back, restart what was running.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say()  { printf '  %s\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$1"; echo; exit 1; }

# What the shortcut is registered under right now. The stored value is
# "Ctrl+Space,none,Dikte: …"; the first field is the key that is live.
registered() {
  command -v kreadconfig6 >/dev/null || return 0
  kreadconfig6 --file kglobalshortcutsrc --group services \
    --group "$1" --key _launch 2>/dev/null | cut -d, -f1
}

echo
echo "Updating Dikte"
echo "──────────────"

cd "$DIR"

# 1. Somewhere there is something to pull ----------------------------------
command -v git >/dev/null || die "git not found; update by downloading the source again"
git rev-parse --git-dir >/dev/null 2>&1 \
  || die "$DIR is not a git checkout; update by downloading the source again"

before="$(git rev-parse HEAD)"

# 2. Is there anything to come? ---------------------------------------------
# Asked before anything else is complained about: an unfinished afternoon in
# the working tree is nobody's problem on a day when nothing has been
# published. Fetching leaves the working tree alone.
git fetch --quiet || die "Could not reach the remote."
upstream="$(git rev-parse '@{u}' 2>/dev/null)" \
  || die "This branch is not tracking a remote one; pull by hand."

if [[ "$before" == "$upstream" ]]; then
  echo
  ok "Already up to date ($(git log -1 --format=%s))"
  echo
  exit 0
fi

# 3. Only now, your own edits -----------------------------------------------
# They would be overwritten by a fast-forward or would block it, and either
# way that is your call to make, not this script's.
if [[ -n "$(git status --porcelain)" ]]; then
  warn "There is an update waiting, but you have changes of your own here:"
  git --no-pager status --short | sed 's/^/    /'
  say "Commit them, or put them aside with:  git stash"
  die "Nothing was updated."
fi

# --ff-only: an update should be somebody else's commits arriving, never a
# merge this script decided to make on your behalf. The fetch above already
# brought them, so this touches no network.
# advice off: git's suggestion is a merge or a rebase, and which of those you
# want is the sentence below, not a wall of hints.
if ! merge_log="$(git -c advice.diverging=false merge --ff-only '@{u}' 2>&1)"; then
  printf '%s\n' "$merge_log" | sed 's/^/    /'
  say "Your branch has commits the remote does not. To put them on top of the"
  say "update instead:  git pull --rebase"
  die "Could not fast-forward."
fi
after="$(git rev-parse HEAD)"

echo
say "What arrived:"
git --no-pager log --oneline "$before..$after" | sed 's/^/    /'
echo

# 4. Launchers --------------------------------------------------------------
# An update can add a dependency or move a file, so the installer runs again.
# It would otherwise re-register its own default shortcuts over the ones you
# chose, so it is told which ones are already registered.
shortcut="$(registered dikte-toggle.desktop)"
cancel_shortcut="$(registered dikte-cancel.desktop)"
# Positional, so a chosen cancel key cannot be passed without the other one.
# Falling back to the installer's default here rather than leaving a gap keeps
# the two arguments lined up with what they mean.
"$DIR/install.sh" "${shortcut:-Ctrl+Space}" "${cancel_shortcut:-Ctrl+Alt+Space}"

# 5. The running instance ---------------------------------------------------
# It is still running the code from before the pull.
if pgrep -u "$USER" -f 'dikte\.py' >/dev/null 2>&1; then
  if python3 "$DIR/dikte.py" restart >/dev/null 2>&1; then
    ok "Restarted, so the new version is the one running"
  else
    warn "Could not restart it; use the tray menu → Restart"
  fi
else
  say "Dikte was not running. Start it with:  dikte"
fi
echo
