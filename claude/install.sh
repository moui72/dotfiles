#!/usr/bin/env bash
#
# install.sh — symlink this portable Claude Code config into ~/.claude
#
# Idempotent. Run it as many times as you like. It:
#   - symlinks claude/settings.json        -> ~/.claude/settings.json
#   - symlinks claude/skills/<each-skill>  -> ~/.claude/skills/<each-skill>
#
# Skills are linked individually (not the whole skills/ dir) so any other
# skills you already have in ~/.claude/skills are left untouched.
#
# Existing real files/dirs at a target are backed up to <target>.bak-<ts>
# before being replaced. Existing correct symlinks are left as-is.
#
# Usage:
#   ./install.sh            # install
#   ./install.sh --dry-run  # show what would happen, change nothing

set -euo pipefail

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

# Resolve the repo's claude/ dir from this script's location (portable, no realpath dep).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${HOME}/.claude"
TS="$(date +%Y%m%d-%H%M%S)"

c_green() { printf '\033[32m%s\033[0m\n' "$1"; }
c_yellow() { printf '\033[33m%s\033[0m\n' "$1"; }
c_red() { printf '\033[31m%s\033[0m\n' "$1"; }

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "  [dry-run] $*"
  else
    "$@"
  fi
}

# link <source> <target>
link() {
  local src="$1" dst="$2"
  if [ ! -e "$src" ]; then
    c_red "  skip: source missing: $src"
    return
  fi
  # Already the correct symlink?
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    echo "  ok (already linked): ${dst/#$HOME/~}"
    return
  fi
  # Existing symlink pointing elsewhere -> replace (no backup; symlinks are cheap).
  if [ -L "$dst" ]; then
    c_yellow "  relink: ${dst/#$HOME/~} (was -> $(readlink "$dst"))"
    run rm "$dst"
  # Existing real file/dir -> back it up first.
  elif [ -e "$dst" ]; then
    c_yellow "  backup: ${dst/#$HOME/~} -> ${dst/#$HOME/~}.bak-$TS"
    run mv "$dst" "${dst}.bak-${TS}"
  fi
  run ln -s "$src" "$dst"
  c_green "  linked: ${dst/#$HOME/~} -> ${src/#$HOME/~}"
}

echo "Installing portable Claude config from: ${SCRIPT_DIR/#$HOME/~}"
[ "$DRY_RUN" -eq 1 ] && c_yellow "(dry run — no changes will be made)"
echo

run mkdir -p "${CLAUDE_HOME}/skills"

echo "settings.json:"
link "${SCRIPT_DIR}/settings.json" "${CLAUDE_HOME}/settings.json"
echo

echo "skills:"
for skill_dir in "${SCRIPT_DIR}"/skills/*/; do
  [ -d "$skill_dir" ] || continue
  name="$(basename "$skill_dir")"
  link "${skill_dir%/}" "${CLAUDE_HOME}/skills/${name}"
done
echo

# ---- prerequisite check (warn-only; never fails the install) ----
echo "Checking prerequisites (warnings only):"
check() {
  local cmd="$1" why="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    c_green "  ✓ $cmd"
  else
    c_yellow "  ✗ $cmd — $why"
  fi
}
check gh                "GitHub CLI; required by the assisted-review skill"
check jq                "JSON wrangling; used by assisted-review scripts"
check bat               "syntax-highlighted diff rendering in assisted-review"
check node              "statusLine (ccstatusline) runs via npx"
check npx               "statusLine (ccstatusline) runs via npx"
check python3           "assisted-review helper scripts"
check terminal-notifier "optional — macOS notification hooks (no-op without it)"
echo
c_green "Done."
echo
echo "Notes:"
echo "  - The notification hooks + 'preferredNotifChannel: ghostty' are macOS/Ghostty"
echo "    specific. They background and suppress output, so they no-op elsewhere."
echo "  - This config does NOT set ANTHROPIC_BASE_URL. If a machine needs a local"
echo "    API proxy, export it from your shell rc — keep it out of the shared file."
echo "  - enabledPlugins lists frontend-design@claude-plugins-official. Install it"
echo "    once with: /plugin marketplace add claude-plugins-official"
