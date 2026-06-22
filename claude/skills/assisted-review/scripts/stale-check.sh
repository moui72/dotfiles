#!/usr/bin/env bash
# stale-check.sh — compare stored PR head SHA against current GitHub state.
#
# Usage:
#   stale-check.sh <env-file-path>
#
# The env file (produced by parse-ref.sh) must define OWNER, REPO, NUMBER,
# and STATE_FILE. STATE_FILE must be a JSON document containing
# `.pr.head_sha`.
#
# Output / exit codes:
#   OK                                  exit 0  (stored sha matches current)
#   STALE old=<short> new=<short>       exit 1  (head moved)
#   CLOSED | MERGED                     exit 2  (PR no longer open)
#   <error to stderr>                   exit 3  (missing state file / jq failure)

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: stale-check.sh <env-file-path>" >&2
  exit 3
fi

env_file="$1"

if [[ ! -f "$env_file" ]]; then
  echo "stale-check: env file not found: $env_file" >&2
  exit 3
fi

# shellcheck disable=SC1090
source "$env_file"

: "${OWNER:?stale-check: OWNER not set in env file}"
: "${REPO:?stale-check: REPO not set in env file}"
: "${NUMBER:?stale-check: NUMBER not set in env file}"
: "${STATE_FILE:?stale-check: STATE_FILE not set in env file}"

if [[ ! -f "$STATE_FILE" ]]; then
  echo "stale-check: state file not found: $STATE_FILE" >&2
  exit 3
fi

stored_sha=$(jq -r '.pr.head_sha' "$STATE_FILE" 2>/dev/null) || {
  echo "stale-check: failed to parse state file: $STATE_FILE" >&2
  exit 3
}

if [[ -z "$stored_sha" || "$stored_sha" == "null" ]]; then
  echo "stale-check: .pr.head_sha missing or null in $STATE_FILE" >&2
  exit 3
fi

current_json=$(gh pr view "$NUMBER" --repo "$OWNER/$REPO" --json headRefOid,state)
current_sha=$(jq -r '.headRefOid' <<<"$current_json")
current_state=$(jq -r '.state' <<<"$current_json")

case "$current_state" in
  CLOSED)
    echo "CLOSED"
    exit 2
    ;;
  MERGED)
    echo "MERGED"
    exit 2
    ;;
esac

if [[ "$stored_sha" == "$current_sha" ]]; then
  echo "OK"
  exit 0
fi

echo "STALE old=${stored_sha:0:7} new=${current_sha:0:7}"
exit 1
