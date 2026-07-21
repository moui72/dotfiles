# Capture items (feedback, feature ideas) into .ardd-data/inbox/<repo>/
# from clipboard or a file, for a later ArDD drain to consume.
#
#   inbox              # new file from clipboard, repo guessed from cwd's git repo
#   inbox path/to.md   # new file copied from a file
#   inbox -e           # like inbox, then open in $EDITOR
#   inbox -r atelier   # target a specific repo's subdirectory
#
# Writes to $ARDD_INBOX_DIR (default ~/dev/.ardd-data/inbox).
# Convention: line 1 of each item names the target skill (/ardd-feedback
# or /ardd-backlog); the rest is raw prose.
# Repo resolution: -r wins; else the git repo containing $PWD; else a
# prompt defaulting to artifact-driven-dev.
# Filenames are timestamp-based (i-YYYYmmddTHHMMSS-PID.md; "i" = item) —
# stable under deletion (drained files are removed), unlike a max+1 counter.

inbox() {
  local base="${ARDD_INBOX_DIR:-$HOME/dev/.ardd-data/inbox}"
  local edit=0 src="" repo=""

  while (( $# )); do
    case "$1" in
      -e|--edit) edit=1 ;;
      -r|--repo) shift; repo="$1" ;;
      -h|--help) echo "usage: inbox [-e] [-r repo] [file]"; return 0 ;;
      *) src="$1" ;;
    esac
    shift
  done

  if [[ -z "$repo" ]]; then
    local top
    top="$(git rev-parse --show-toplevel 2>/dev/null)"
    if [[ -n "$top" ]]; then
      repo="${top:t}"
    else
      read "repo?inbox: repo [artifact-driven-dev]: " || return 1
      [[ -n "$repo" ]] || repo="artifact-driven-dev"
    fi
  fi

  local dir="$base/$repo"
  mkdir -p "$dir" || return 1

  local out="$dir/i-$(date +%Y%m%dT%H%M%S)-$$-$RANDOM.md"

  if [[ -n "$src" ]]; then
    [[ -r "$src" ]] || { echo "inbox: cannot read '$src'" >&2; return 1; }
    cp "$src" "$out" || return 1
  else
    local clip
    clip="$(pbpaste)"
    [[ -n "$clip" ]] || { echo "inbox: clipboard is empty" >&2; return 1; }
    printf '%s\n' "$clip" > "$out" || return 1
  fi

  echo "$out"
  if (( edit )); then
    "${EDITOR:-vi}" "$out"
  fi
  return 0
}

alias in=inbox
alias ib=inbox
