# Resign commits that were made unsigned (e.g. while 1Password was locked
# during a remote/phone session) once you're back at your computer and
# 1Password is unlocked. See also: the global pre-push hook in
# dotfiles/git-hooks/pre-push, which blocks pushes containing unsigned
# commits and points here.

# Lists "<sha> <status>" for commits in <base>..HEAD whose signature status
# isn't "G" (good) — i.e. unsigned (N) or signed-but-not-good (B/X/Y/R/E).
git_unsigned_commits() {
  local base="$1"
  [[ -z "$base" ]] && base='@{u}'
  if ! git rev-parse "$base" >/dev/null 2>&1; then
    echo "git_unsigned_commits: no upstream configured and no base given. Usage: git_unsigned_commits [<base-ref>]" >&2
    return 1
  fi
  git log --format='%H %G?' "$base"..HEAD | awk '$2 != "G" {print $1, $2}'
}

# Rewrites <base>..HEAD (default: upstream..HEAD), re-signing every commit
# that isn't currently validly signed. Safe to run even if some commits in
# the range are already signed — they just get re-signed with an identical
# tree/message, no content change.
resign_unsigned_commits() {
  local base="$1"
  [[ -z "$base" ]] && base='@{u}'
  local unsigned
  unsigned=$(git_unsigned_commits "$base") || return 1

  if [[ -z "$unsigned" ]]; then
    echo "No unsigned commits between $base and HEAD."
    return 0
  fi

  echo "Unsigned/invalid-signature commits between $base and HEAD:"
  echo "$unsigned"
  echo
  echo "Resigning (requires 1Password unlocked for SSH signing)..."
  git rebase "$base" --exec 'git commit --amend --no-edit -S --allow-empty' || {
    echo "resign_unsigned_commits: rebase failed — resolve conflicts, or run 'git rebase --abort'." >&2
    return 1
  }

  local remaining
  remaining=$(git_unsigned_commits "$base")
  if [[ -n "$remaining" ]]; then
    echo "Some commits are still unsigned — is 1Password unlocked? Remaining:" >&2
    echo "$remaining" >&2
    return 1
  fi
  echo "All commits between $base and HEAD are now signed."
}

alias resign-unsigned-commits="resign_unsigned_commits"
alias gsg="resign_unsigned_commits"
