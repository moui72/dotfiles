#!/usr/bin/env bash
# fetch.sh — fetch PR metadata, diff, comments, checks, and viewer login.
#
# Usage:
#   fetch.sh <env-file-path>
#
# Sources the env file produced by parse-ref.sh (OWNER, REPO, NUMBER,
# STATE_FILE), then runs 5 gh calls in parallel and writes outputs alongside
# STATE_FILE. On success prints a sourceable env block listing the 5 paths.

set -uo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: fetch.sh <env-file-path>" >&2
  exit 2
fi

env_file="$1"
if [[ ! -f "$env_file" ]]; then
  echo "fetch: env file not found: $env_file" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "$env_file"

: "${OWNER:?fetch: OWNER missing from env file}"
: "${REPO:?fetch: REPO missing from env file}"
: "${NUMBER:?fetch: NUMBER missing from env file}"
: "${STATE_FILE:?fetch: STATE_FILE missing from env file}"

base="${STATE_FILE%.json}"
meta_file="${base}.meta.json"
diff_file="${base}.diff.txt"
comments_file="${base}.comments.json"
checks_file="${base}.checks.txt"
me_file="${base}.me.txt"

meta_err="$(mktemp)"
diff_err="$(mktemp)"
comments_err="$(mktemp)"
checks_err="$(mktemp)"
me_err="$(mktemp)"
trap 'rm -f "$meta_err" "$diff_err" "$comments_err" "$checks_err" "$me_err"' EXIT

gh pr view "$NUMBER" --repo "$OWNER/$REPO" \
  --json title,body,author,isDraft,mergeable,headRefOid,baseRefName,headRefName,url,state \
  >"$meta_file" 2>"$meta_err" &
meta_pid=$!

gh pr diff "$NUMBER" --repo "$OWNER/$REPO" \
  >"$diff_file" 2>"$diff_err" &
diff_pid=$!

gh api "repos/$OWNER/$REPO/pulls/$NUMBER/comments" \
  >"$comments_file" 2>"$comments_err" &
comments_pid=$!

gh pr checks "$NUMBER" --repo "$OWNER/$REPO" \
  >"$checks_file" 2>"$checks_err" &
checks_pid=$!

gh api user --jq .login \
  >"$me_file" 2>"$me_err" &
me_pid=$!

wait "$meta_pid";     meta_rc=$?
wait "$diff_pid";     diff_rc=$?
wait "$comments_pid"; comments_rc=$?
wait "$checks_pid";   checks_rc=$?  # not strict
wait "$me_pid";       me_rc=$?

fail=0
if [[ $meta_rc -ne 0 ]]; then
  echo "fetch: gh pr view failed (rc=$meta_rc)" >&2
  cat "$meta_err" >&2
  fail=1
fi
if [[ $diff_rc -ne 0 ]]; then
  echo "fetch: gh pr diff failed (rc=$diff_rc)" >&2
  cat "$diff_err" >&2
  fail=1
fi
if [[ $comments_rc -ne 0 ]]; then
  echo "fetch: gh api comments failed (rc=$comments_rc)" >&2
  cat "$comments_err" >&2
  fail=1
fi
if [[ $me_rc -ne 0 ]]; then
  echo "fetch: gh api user failed (rc=$me_rc)" >&2
  cat "$me_err" >&2
  fail=1
fi

if [[ $fail -ne 0 ]]; then
  exit 1
fi

# checks_rc is intentionally ignored (non-zero when any check fails)
: "$checks_rc"

cat <<EOF
META_FILE='$meta_file'
DIFF_FILE='$diff_file'
COMMENTS_FILE='$comments_file'
CHECKS_FILE='$checks_file'
ME_FILE='$me_file'
EOF
