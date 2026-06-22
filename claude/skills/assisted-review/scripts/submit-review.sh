#!/usr/bin/env bash
# submit-review.sh — Submit a PR review assembled in $STATE_FILE.
#
# Usage: submit-review.sh <env-file-path> [--dry-run]
#   Env: DRY_RUN=1 also enables dry-run mode.
#
# Reads the env file (must export OWNER, REPO, NUMBER, STATE_FILE, URL),
# extracts verdict/body/head_sha/comments from $STATE_FILE, posts replies
# first (one POST per reply), then a single bundled review POST containing
# any new inline comments.
#
# On failure: prints failing stderr + the assembled main-review JSON so the
# user can submit manually, and exits non-zero without archiving state.
# On success: archives state file and prints the review html_url.
#
# Exit codes:
#   0  success
#   1  general failure (main review POST rejected)
#   2  usage / preconditions
#   4  inline-anchor failure on stale SHA — HEAD_SHA is not on the PR's
#      commits list and inline comments exist. Stderr contains a single line:
#         STALE_INLINE old=<sha> new_head=<sha> inline_count=<n>
#      Replies have already been posted (they don't depend on commit_id).
#      State file is left in place so the agent can run the fallback flow
#      and re-invoke this helper after rewriting comments.

set -uo pipefail

ENV_FILE="${1:-}"
DRY_RUN="${DRY_RUN:-0}"
if [[ "${2:-}" == "--dry-run" || "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
fi
# If --dry-run was the first arg, the env file must be the second
if [[ "${1:-}" == "--dry-run" ]]; then
    ENV_FILE="${2:-}"
fi

if [[ -z "$ENV_FILE" ]]; then
    echo "Usage: $0 <env-file-path> [--dry-run]" >&2
    exit 2
fi
if [[ ! -f "$ENV_FILE" ]]; then
    echo "Env file not found: $ENV_FILE" >&2
    exit 2
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

for var in OWNER REPO NUMBER STATE_FILE; do
    if [[ -z "${!var:-}" ]]; then
        echo "Missing required variable from env file: $var" >&2
        exit 2
    fi
done

if [[ ! -f "$STATE_FILE" ]]; then
    echo "State file not found: $STATE_FILE" >&2
    exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "jq is required but not installed" >&2
    exit 2
fi

# Extract review-level fields.
VERDICT=$(jq -r '.draft_review.verdict // ""' "$STATE_FILE")
BODY=$(jq -r '.draft_review.body // ""' "$STATE_FILE")
HEAD_SHA=$(jq -r '.pr.head_sha // ""' "$STATE_FILE")

if [[ -z "$VERDICT" ]]; then
    echo "draft_review.verdict is missing or empty in state file" >&2
    exit 2
fi
case "$VERDICT" in
    APPROVE|COMMENT|REQUEST_CHANGES) ;;
    *)
        echo "Invalid verdict: $VERDICT (expected APPROVE|COMMENT|REQUEST_CHANGES)" >&2
        exit 2
        ;;
esac
if [[ -z "$HEAD_SHA" ]]; then
    echo "pr.head_sha is missing in state file" >&2
    exit 2
fi

# Pull all comments out, tagged with their parent file path.
ALL_COMMENTS_JSON=$(jq -c '
    [ .chunks[]
      | .file as $f
      | .comments[]
      | . + {path: $f}
    ]
' "$STATE_FILE")

# Replies: in_reply_to non-null.
REPLIES_JSON=$(jq -c '[ .[] | select(.in_reply_to != null) ]' <<<"$ALL_COMMENTS_JSON")

# New inline comments: in_reply_to null. Build the review API shape.
NEW_COMMENTS_JSON=$(jq -c '
    [ .[]
      | select(.in_reply_to == null)
      | {
          path: .path,
          body: .body,
          side: .side,
          line: .end_line
        }
        + (
            if (.start_line != null) and (.start_line < .end_line)
            then { start_line: .start_line, start_side: .side }
            else {}
            end
        )
    ]
' <<<"$ALL_COMMENTS_JSON")

REPLIES_COUNT=$(jq 'length' <<<"$REPLIES_JSON")
NEW_COMMENTS_COUNT=$(jq 'length' <<<"$NEW_COMMENTS_JSON")

print_main_payload() {
    jq -n \
        --arg event "$VERDICT" \
        --arg body "$BODY" \
        --arg commit_id "$HEAD_SHA" \
        --argjson comments "$NEW_COMMENTS_JSON" \
        '{event: $event, body: $body, commit_id: $commit_id, comments: $comments}'
}

if [[ "$DRY_RUN" == "1" ]]; then
    echo "=== DRY RUN ==="
    echo "Replies to post: $REPLIES_COUNT"
    if [[ "$REPLIES_COUNT" -gt 0 ]]; then
        # shellcheck disable=SC2034
        while IFS= read -r reply; do
            in_reply_to=$(jq -r '.in_reply_to' <<<"$reply")
            rbody=$(jq -r '.body' <<<"$reply")
            echo "--- reply POST ---"
            echo "gh api repos/$OWNER/$REPO/pulls/comments/$in_reply_to/replies -X POST -f body=<<<"
            printf '%s\n' "$rbody"
        done < <(jq -c '.[]' <<<"$REPLIES_JSON")
    fi
    echo "--- main review POST ---"
    echo "gh api repos/$OWNER/$REPO/pulls/$NUMBER/reviews -X POST --input - <<<\$PAYLOAD"
    echo "full payload:"
    print_main_payload | jq .
    exit 0
fi

# Post replies first so they land even if main review fails.
if [[ "$REPLIES_COUNT" -gt 0 ]]; then
    while IFS= read -r reply; do
        in_reply_to=$(jq -r '.in_reply_to' <<<"$reply")
        rbody=$(jq -r '.body' <<<"$reply")
        reply_err=$(mktemp)
        if ! gh api "repos/$OWNER/$REPO/pulls/comments/$in_reply_to/replies" \
                -X POST -f body="$rbody" >/dev/null 2>"$reply_err"; then
            echo "Failed to post reply to comment $in_reply_to:" >&2
            cat "$reply_err" >&2
            echo "Reply body was:" >&2
            printf '%s\n' "$rbody" >&2
            rm -f "$reply_err"
            # Continue trying other replies and main review? Per spec: replies
            # first so they land even if main fails. A single reply failure
            # shouldn't abort the rest. Log and continue.
            continue
        fi
        rm -f "$reply_err"
    done < <(jq -c '.[]' <<<"$REPLIES_JSON")
fi

# Pre-flight: if we have inline comments, verify HEAD_SHA is still on the PR's
# commits list. After a force-push, an orphaned SHA produces a 422
# "Path could not be resolved" on inline anchors even though the top-level
# body would be accepted. Detect this before posting so the agent can run
# the fallback flow.
if [[ "$NEW_COMMENTS_COUNT" -gt 0 ]]; then
    pr_commits=$(gh api --paginate "repos/$OWNER/$REPO/pulls/$NUMBER/commits" -q '.[].sha' 2>/dev/null || true)
    if [[ -n "$pr_commits" ]] && ! grep -qx "$HEAD_SHA" <<<"$pr_commits"; then
        new_head=$(gh api "repos/$OWNER/$REPO/pulls/$NUMBER" -q .head.sha 2>/dev/null || echo "unknown")
        echo "STALE_INLINE old=$HEAD_SHA new_head=$new_head inline_count=$NEW_COMMENTS_COUNT" >&2
        exit 4
    fi
fi

# Post the main review.
# We must POST the full payload as a single JSON document on stdin via
# `--input -`. Earlier versions used `--raw-field comments=...`, which gh
# encodes as a *string* under the `comments` key — the API rejects this
# with HTTP 422 ("not an array").
main_err=$(mktemp)
main_out=$(mktemp)
main_payload=$(print_main_payload)
if ! printf '%s' "$main_payload" | gh api "repos/$OWNER/$REPO/pulls/$NUMBER/reviews" \
        -X POST --input - \
        >"$main_out" 2>"$main_err"; then
    # Catch the "Path could not be resolved" case the pre-flight missed
    # (e.g. HEAD_SHA appears in pulls/commits but inline anchor still fails).
    if grep -q "Path could not be resolved" "$main_err"; then
        new_head=$(gh api "repos/$OWNER/$REPO/pulls/$NUMBER" -q .head.sha 2>/dev/null || echo "unknown")
        echo "STALE_INLINE old=$HEAD_SHA new_head=$new_head inline_count=$NEW_COMMENTS_COUNT" >&2
        rm -f "$main_err" "$main_out"
        exit 4
    fi
    echo "Failed to post main review:" >&2
    cat "$main_err" >&2
    echo "" >&2
    echo "Assembled review payload (submit manually if desired):"
    print_main_payload | jq .
    rm -f "$main_err" "$main_out"
    exit 1
fi

HTML_URL=$(jq -r '.html_url // empty' "$main_out")
rm -f "$main_err" "$main_out"

# Archive state file on success.
ARCHIVE="${STATE_FILE%.json}-submitted-$(date +%s).json"
if ! mv "$STATE_FILE" "$ARCHIVE"; then
    echo "Warning: failed to archive state file to $ARCHIVE" >&2
fi

if [[ -n "$HTML_URL" ]]; then
    echo "$HTML_URL"
else
    echo "Review submitted (no html_url in response)."
fi
