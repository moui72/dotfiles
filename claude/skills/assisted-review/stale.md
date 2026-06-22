# Stale-PR handling

Loaded by SKILL.md only when (a) about to submit or resuming a review, or (b) `submit-review.sh` exits 4 (`STALE_INLINE`).

## Stale-PR detection

Run before submit and on resume:

```bash
~/.claude/skills/assisted-review/scripts/stale-check.sh "$ENV_FILE"
```

Stdout / exit code:
- `OK` / exit 0 → proceed.
- `STALE old=<short> new=<short>` / exit 1 → show the stale-PR prompt from [templates.md](templates.md). Both `s` and `c` submit against the old SHA (the submit helper uses `state.pr.head_sha` as `commit_id`) so line anchors stay valid.
- `CLOSED` or `MERGED` / exit 2 → offer submit-as-is or discard.
- exit 3 → state file missing or unreadable; surface stderr.

## Stale-inline fallback flow

`submit-review.sh` exits 4 when the reviewed SHA is no longer in the PR's commits list (typical after a force-push). Stderr is a single line:

```
STALE_INLINE old=<sha> new_head=<sha> inline_count=<n>
```

Replies have already posted (they don't depend on `commit_id`). Body and inline comments have not. Run this flow:

1. Show the **stale-inline fallback prompt** from [templates.md](templates.md).

2. On user input:

   - **`1` — embed in overall body.** Rewrite `state.draft_review.body` to append each inline comment as a section:
     ```
     ---
     **`<file>:<lines>`** (originally <side>-side, SHA `<old-short>`)

     > <2-3 lines of original anchor context from chunk diff>

     <comment body>
     ```
     Clear `chunks[].comments` (move them into `state.draft_review.embedded_comments` so resume is informative). Re-invoke `submit-review.sh`. Inline-comment count is now 0, pre-flight passes, body posts.

   - **`2` — re-anchor to new HEAD.** Run the re-anchor pass:
     1. Fetch the new HEAD diff via `gh api repos/$OWNER/$REPO/pulls/$NUMBER -H "Accept: application/vnd.github.diff" > $DIFF_FILE.new` and parse with `scripts/parse-diff.py "$DIFF_FILE.new"`.
     2. For each comment in `chunks[].comments` (where `in_reply_to == null`):
        a. Extract the original anchor content: for a single-line comment, the line at `end_line` on `side` from the original chunk diff; for a range, the `start_line`..`end_line` slice.
        b. Search the new diff for a hunk in the same `file` whose lines contain that exact content. Prefer the closest match by line distance to original; require an exact content match (whitespace-significant) to avoid mis-anchoring.
        c. If found: update the comment's `side`, `start_line`, `end_line` to the new anchor and the parent chunk's `file` (in case of rename — also check the new diff's rename headers via `git --no-pager diff` parsing if needed). Record `state.chunks[].comments[].reanchored = {from: {sha: old, side, lines}, to: {...}}` for transparency.
        d. If not found: show the **per-comment re-anchor prompt** from [templates.md](templates.md). Map input:
           - `t` → anchor at line 1 on RIGHT in the original `file`. If the file no longer exists, fall through to `b`.
           - `b` → embed in body using the same template as option `1`. Move to `state.draft_review.embedded_comments`.
           - `d` → drop. Move to `state.draft_review.dropped_comments` (with original anchor) so it stays auditable.
     3. Update `state.pr.head_sha` to the new HEAD SHA (the commit_id we're now anchoring against). Persist state.
     4. Re-invoke `submit-review.sh`.

   - **`3` — drop inline comments.** Move all `chunks[].comments` (where `in_reply_to == null`) into `state.draft_review.dropped_comments` with their original anchors preserved for the archive. Clear `chunks[].comments` of non-reply entries. Persist state and re-invoke `submit-review.sh`.

3. If the re-invoke succeeds, print the submitted template with the URL.
4. If it fails again, fall back to the generic exit-1 manual-recovery path (print assembled JSON).

The agent owns all rewriting; the helper only detects and signals. Each branch must persist state before re-invoking so a crash between branches is recoverable on resume.
