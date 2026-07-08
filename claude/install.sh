#!/usr/bin/env bash
#
# install.sh — set up this portable Claude Code config in ~/.claude
#
# Idempotent. Run it as many times as you like. It:
#   - copies claude/settings.json          -> ~/.claude/settings.json
#     (copy, not symlink — /config does atomic writes that break symlinks)
#   - writes dotfiles path                 -> ~/.claude/.dotfiles-claude-dir
#     (used by the ConfigChange hook to sync /config edits back to the repo)
#   - symlinks claude/skills/<each-skill>  -> ~/.claude/skills/<each-skill>
#   - symlinks omz/custom                  -> ~/.oh-my-zsh/custom
#   - symlinks ccstatusline/settings.json  -> ~/.config/ccstatusline/settings.json
#   - sets this repo's core.hooksPath      -> git-hooks/
#     (repo-local only — activates pre-push signing check + post-merge
#     auto-reinstall for this repo; does not touch other repos)
#   - sets this repo's pull.rebase         -> false
#     (repo-local only — post-merge only fires on a merge, not a rebase, so
#     this guarantees `git pull` always merges and always triggers it, even
#     when a fast-forward is possible)
#
# Skills are linked individually so any other files you already have in
# ~/.claude/skills are left untouched. omz/custom is linked as a whole
# directory, not per-file — oh-my-zsh only globs top-level *.zsh files
# directly in $ZSH_CUSTOM (confirmed against oh-my-zsh.sh), so anything
# machine-local that needs sourcing (e.g. a vault, stock example files)
# has to live inside omz/custom itself, not alongside it. Per-file symlinks
# were tried first and abandoned for this reason.
#
# settings.json copy behaviour:
#   - symlink at target  → convert to real file (copy from dotfiles)
#   - missing            → copy from dotfiles
#   - real file present  → leave it alone (may have /config edits); update pointer
#
# Usage:
#   ./install.sh            # install
#   ./install.sh --dry-run  # show what would happen, change nothing

set -euo pipefail

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

# Resolve the repo's claude/ dir from this script's location (portable, no realpath dep).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
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
settings_src="${SCRIPT_DIR}/settings.json"
settings_dst="${CLAUDE_HOME}/settings.json"
if [ -L "$settings_dst" ]; then
  c_yellow "  converting symlink to real file: ${settings_dst/#$HOME/~}"
  run cp "$settings_src" "${settings_dst}.new"
  run mv "${settings_dst}.new" "$settings_dst"
  c_green "  copied: ${settings_dst/#$HOME/~}"
elif [ ! -e "$settings_dst" ]; then
  c_yellow "  copying: ${settings_dst/#$HOME/~}"
  run cp "$settings_src" "$settings_dst"
  c_green "  copied: ${settings_dst/#$HOME/~}"
else
  echo "  ok (real file present, not overwriting): ${settings_dst/#$HOME/~}"
fi
run sh -c "echo \"${SCRIPT_DIR}\" > \"${CLAUDE_HOME}/.dotfiles-claude-dir\""
c_green "  stored dotfiles path -> ${CLAUDE_HOME/#$HOME/~}/.dotfiles-claude-dir"
echo

echo "skills:"
for skill_dir in "${SCRIPT_DIR}"/skills/*/; do
  [ -d "$skill_dir" ] || continue
  name="$(basename "$skill_dir")"
  link "${skill_dir%/}" "${CLAUDE_HOME}/skills/${name}"
done
echo

echo "oh-my-zsh custom dir:"
omz_home="${HOME}/.oh-my-zsh"
if [ ! -d "$omz_home" ]; then
  c_yellow "  skip: ~/.oh-my-zsh not found (oh-my-zsh not installed?)"
else
  link "${REPO_ROOT}/omz/custom" "${omz_home}/custom"
fi
echo

echo "ccstatusline config:"
run mkdir -p "${HOME}/.config/ccstatusline"
link "${REPO_ROOT}/ccstatusline/settings.json" "${HOME}/.config/ccstatusline/settings.json"
echo

echo "git hooks (this repo only):"
current_hooks_path="$(git -C "$REPO_ROOT" config --local --get core.hooksPath || true)"
if [ "$current_hooks_path" = "${REPO_ROOT}/git-hooks" ]; then
  echo "  ok (already wired): core.hooksPath -> git-hooks"
else
  run git -C "$REPO_ROOT" config --local core.hooksPath "${REPO_ROOT}/git-hooks"
  c_green "  wired: core.hooksPath -> ${REPO_ROOT}/git-hooks"
fi
# post-merge only fires on a merge (fast-forward included); a rebase never
# triggers it. This repo may inherit pull.rebase=true from global config, so
# pin merge-on-pull locally here to guarantee `git pull` always runs post-merge.
current_pull_rebase="$(git -C "$REPO_ROOT" config --local --get pull.rebase || true)"
if [ "$current_pull_rebase" = "false" ]; then
  echo "  ok (already wired): pull.rebase -> false"
else
  run git -C "$REPO_ROOT" config --local pull.rebase false
  c_green "  wired: pull.rebase -> false (this repo only, so post-merge always fires on pull)"
fi
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
