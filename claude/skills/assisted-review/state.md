# State persistence

Loaded by SKILL.md when reading, writing, or resuming the review state file.

## Location

`$STATE_FILE` is set by `scripts/parse-ref.sh` and resolves to:

```
~/.claude/projects/<project-slug>/scratch/review-<owner>-<repo>-<num>.json
```

where `<project-slug>` is `$PWD` with `/` replaced by `-`. Override the parent dir via `REVIEW_PR_SCRATCH_DIR`.

## Write policy

- Write the **entire** state file after every action via the Write tool.
- JSON, pretty-printed.
- The session may compact or be interrupted; resume must work from this file alone.

## Lifecycle

- **On start** — if the file exists, show the resume prompt from [templates.md](templates.md). On `r`, load and skip to current cursor. On `n`, delete and proceed fresh. On `c`, stop. Otherwise create fresh.
- **On submit success** — rename to `review-<owner>-<repo>-<num>-submitted-<unix-ts>.json` via `mv`. The submit helper (`scripts/submit-review.sh`) handles this.
- **On submit failure** — leave the state file in place; the helper prints the assembled review JSON to stdout for manual recovery.

## Cursor semantics

`state.cursor.queue` is the ordered list of chunk IDs to present in the current phase. The chunk currently being presented is always `queue[0]`. Chunk-consuming actions (`mark viewed`, `comment`, `flag`) shift it off; action `4` (`ask AI`) moves it to the end (`queue.push(queue.shift())`); actions `1` and `R` do not modify the queue.

## Shape

```json
{
  "pr": { "owner": "...", "repo": "...", "number": 123, "head_sha": "a1b2c3d4...", "url": "..." },
  "started_at": "2026-05-18T14:00:00Z",
  "rubric_source": "default",
  "preamble": {
    "title": "...",
    "ai_summary": "...",
    "ci": { "passing": 2, "failing": 1, "failing_names": ["e2e-auth"] },
    "is_draft": false,
    "mergeable": true,
    "self_authored": false,
    "author": "alice",
    "base_ref": "main",
    "head_ref": "alice/session-retry"
  },
  "skipped": {
    "generated": [{ "file": "yarn.lock", "reason": "lockfile" }],
    "no_risk":   [{ "id": "c3", "file": "src/foo.ts", "summary": "import reorder" }]
  },
  "chunks": [
    {
      "id": "c7",
      "file": "src/auth/session.ts",
      "hunk_header": "@@ -42,8 +42,14 @@ function refreshSession()",
      "old_range": [42, 49],
      "new_range": [42, 55],
      "members": [
        { "hunk_header": "@@ -42,8 +42,14 @@ function refreshSession()", "old_range": [42, 49], "new_range": [42, 55] }
      ],
      "diff": "@@ -42,8 +42,14 @@ ...\n ...",
      "rating": "medium",
      "ai_notes": [
        { "kind": "initial", "body": "..." },
        { "kind": "context", "body": "..." },
        { "kind": "investigation", "prompt": "...", "body": "..." }
      ],
      "existing_threads": [
        { "id": "12345", "author": "bob", "is_bot": false, "state": "open", "line": 45, "side": "RIGHT", "body": "..." }
      ],
      "status": "pending",
      "comments": [
        { "side": "RIGHT", "start_line": 45, "end_line": 47, "body": "...", "in_reply_to": null }
      ]
    }
  ],
  "cursor": { "phase": "main", "queue": ["c1", "c2", "c4", "c7"] },
  "draft_review": { "verdict": null, "body": null }
}
```

## Field notes

- `chunks[].members` lists the original hunk boundaries that were grouped into this chunk (single-element for ungrouped chunks). Comment line-anchor validation uses these ranges so a request can't anchor in a gap between merged hunks. The chunk's top-level `old_range`/`new_range` span first-member-start to last-member-end inclusive.
- `chunks[].status` values: `pending`, `flagged`, `dismissed`.
- `chunks[].ai_notes[].kind` values: `initial` (pre-generated commentary), `context` (action `1`), `investigation` (action `4`), `error` (pre-gen failure — `{kind: "error", body: "<message>"}`).
- `chunks[].comments[].in_reply_to` is the thread ID being replied to, or `null` for a new top-level comment.
- `cursor.phase` is `"main"` or `"flagged"`.
- `rubric_source` is `"default"` or `"project:.claude/review-rubric.md@<short-head-sha>"`.
