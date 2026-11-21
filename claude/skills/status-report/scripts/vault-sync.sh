#!/usr/bin/env bash
# Sync the Obsidian vault with its git remote.
#   vault-sync.sh pull   -> rebase local onto remote (run BEFORE reading/writing todos)
#   vault-sync.sh push   -> commit any changes and push (run AFTER writing todos)
# Never fails the caller: prints a one-line status and exits 0 unless the vault is missing.
set -uo pipefail

PROFILE_PY="$HOME/.claude/skills/project/scripts/skill_profile.py"
VAULT="${OBSIDIAN_VAULT:-$([[ -f "$PROFILE_PY" ]] && python3 "$PROFILE_PY" get vault_dir 2>/dev/null)}"
VAULT="${VAULT:-$HOME/Documents}"  # vault_dir from the per-machine profile (project skill)
MODE="${1:-}"

[[ -d "$VAULT/.git" ]] || { echo "vault-sync: $VAULT is not a git repo"; exit 1; }
cd "$VAULT"

has_remote() { git remote get-url origin >/dev/null 2>&1; }

case "$MODE" in
  pull)
    if ! has_remote; then echo "vault-sync: no remote configured, skipping pull"; exit 0; fi
    # Stash local edits so a rebase can't trip over a dirty tree.
    dirty=0
    if [[ -n "$(git status --porcelain)" ]]; then dirty=1; git stash push -q -u -m vault-sync; fi
    if git pull --rebase -q origin "$(git branch --show-current)"; then
      echo "vault-sync: pulled"
    else
      git rebase --abort 2>/dev/null
      echo "vault-sync: PULL FAILED (rebase conflict) — resolve in $VAULT before syncing"
    fi
    [[ $dirty -eq 1 ]] && { git stash pop -q || echo "vault-sync: stash pop conflicted — see 'git stash list'"; }
    ;;
  push)
    if [[ -z "$(git status --porcelain)" ]]; then echo "vault-sync: nothing to commit"; else
      git add -A
      git commit -q -m "${2:-vault: sync todos}"
      echo "vault-sync: committed"
    fi
    if ! has_remote; then echo "vault-sync: no remote configured, skipping push"; exit 0; fi
    branch="$(git branch --show-current)"
    if git push -q origin "$branch" 2>/dev/null; then
      echo "vault-sync: pushed"
    else
      # Remote moved ahead — rebase first, then retry once (see feedback_git_push_rejected).
      echo "vault-sync: push rejected, rebasing"
      if git pull --rebase -q origin "$branch" && git push -q origin "$branch"; then
        echo "vault-sync: pushed after rebase"
      else
        echo "vault-sync: PUSH FAILED — resolve in $VAULT"
      fi
    fi
    ;;
  *)
    echo "usage: vault-sync.sh {pull|push} [commit message]" >&2; exit 2 ;;
esac
