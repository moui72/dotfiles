#!/usr/bin/env bash
# fetch-repo-file.sh — fetch a file from a GitHub repo at a specific ref via
# the GitHub Contents API and write it to a local temp file. Prints the temp
# file path to stdout on success.
#
# Used by the assisted-review skill to pick up per-project overrides
# (e.g. .claude/review-rubric.md, .claude/review-skip.txt) at the PR head SHA.
#
# Usage:
#   fetch-repo-file.sh <owner/repo> <ref> <path-in-repo>
#
# Exit codes:
#   0  file exists; path printed on stdout
#   1  file does not exist at that ref (404)
#   2  usage error or other gh failure (stderr has details)

set -uo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: fetch-repo-file.sh <owner/repo> <ref> <path-in-repo>" >&2
  exit 2
fi

repo_full="$1"
ref="$2"
repo_path="$3"

tmp_out=$(mktemp -t assisted-review-fetch.XXXXXX)
tmp_err=$(mktemp -t assisted-review-fetch-err.XXXXXX)

if gh api "repos/$repo_full/contents/$repo_path?ref=$ref" \
     -H "Accept: application/vnd.github.raw" \
     > "$tmp_out" 2> "$tmp_err"; then
  rm -f "$tmp_err"
  echo "$tmp_out"
  exit 0
fi

err_content=$(cat "$tmp_err")
rm -f "$tmp_out" "$tmp_err"

if echo "$err_content" | grep -qiE '(^| )(404|not found|HTTP 404)'; then
  exit 1
fi

echo "fetch-repo-file: $err_content" >&2
exit 2
