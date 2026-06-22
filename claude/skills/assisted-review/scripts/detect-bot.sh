#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ] || [ -z "$1" ]; then
  echo "Usage: $(basename "$0") <login>" >&2
  exit 2
fi

login="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ends with [bot]
case "$login" in
  *"[bot]") exit 0 ;;
esac

# starts with sa-
case "$login" in
  sa-*) exit 0 ;;
esac

# ends with -automation or contains -automation- as a segment
case "$login" in
  *-automation|*-automation-*) exit 0 ;;
esac

# bots.txt exact match (case-insensitive, comments/blanks ignored).
# Bundled defaults live in scripts/bots.txt (tracked); user additions go in
# user-bots.txt at the skill root (gitignored, created on first append) so
# skill updates don't clobber local edits.
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
for bots_file in "$SCRIPT_DIR/bots.txt" "$SKILL_DIR/user-bots.txt"; do
  [ -f "$bots_file" ] || continue
  if grep -v '^[[:space:]]*\(#\|$\)' "$bots_file" \
      | tr -d '\r' \
      | sed 's/[[:space:]]*$//' \
      | tr '[:upper:]' '[:lower:]' \
      | grep -Fxq -- "$login"; then
    exit 0
  fi
done

exit 1
