#!/usr/bin/env bash
# claude-fork-tab.sh — fork the Claude Code session running in the focused Ghostty
# terminal into a new Ghostty tab (`claude --resume <id> --fork-session`).
#
# Lookup: Ghostty AppleScript -> focused terminal's tty -> foreground `claude` pid on
# that tty -> ~/.claude/sessions/<pid>.json (sessionId + launch cwd). The new tab
# starts in the session's launch cwd, because --resume finds sessions by project dir.
#
# Bound to a hotkey by hammerspoon/init.lua; also runnable directly from a shell.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"  # Hammerspoon has a bare PATH

fail() { echo "claude-fork-tab: $*" >&2; exit 1; }

tty=$(osascript -e 'tell application "Ghostty" to get tty of focused terminal of selected tab of front window') \
  || fail "couldn't read the focused Ghostty terminal"
tty=${tty#/dev/}

# Foreground (stat contains '+') process whose executable is `claude`.
pid=$(ps -t "$tty" -o pid=,stat=,comm= | awk '$2 ~ /\+/ && ($3 == "claude" || $3 ~ /\/claude$/) {print $1; exit}')
[[ -n "$pid" ]] || fail "no Claude Code session in the focused terminal ($tty)"

session_file="$HOME/.claude/sessions/$pid.json"
[[ -f "$session_file" ]] || fail "no session file for pid $pid"
session_id=$(jq -r '.sessionId // empty' "$session_file")
cwd=$(jq -r '.cwd // empty' "$session_file")
[[ -n "$session_id" && -n "$cwd" ]] || fail "session file $session_file is missing sessionId/cwd"

osascript - "$cwd" "claude --resume $session_id --fork-session" <<'APPLESCRIPT'
on run argv
  set theDir to item 1 of argv
  set theCmd to item 2 of argv
  tell application "Ghostty"
    set cfg to new surface configuration
    set initial working directory of cfg to theDir
    set initial input of cfg to theCmd & return
    new tab in front window with configuration cfg
    activate
  end tell
end run
APPLESCRIPT
