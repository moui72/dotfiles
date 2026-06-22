---
name: assisted-review
description: Interactive PR review where the human is the reviewer and Claude is the assistant. Walks the user through a GitHub PR hunk by hunk, presenting each hunk with AI commentary and waiting for the user to choose an action (comment, flag, ask AI, etc.) before moving on. ONLY use this skill when the user explicitly asks for HELP reviewing a PR or wants to be WALKED THROUGH one — trigger phrases include "help me review", "walk me through", "review with me", "assist me reviewing", "let's review together", or an explicit `/assisted-review` invocation. DO NOT use this skill when the user asks Claude to "review a PR", "do a code review", "check this PR", or any phrasing where Claude is the reviewer producing a review — that is the `review` skill. If ambiguous, ask the user which they want before invoking. Invoke via `/assisted-review <owner/repo#N | URL>`.
argument-hint: <owner/repo#N or PR URL>
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, WebFetch]
---

# AI-Assisted PR Review

You are walking a human reviewer through a GitHub PR one hunk at a time. The human makes every decision. Your job is prep, recall, classification, and bookkeeping.

**Read this entire file before starting.** Then read [rubric.md](rubric.md) for the safety classification criteria. Companion references — load when you need them:

- [palette.md](palette.md) — ANSI color codes, application rules, and conditional styling for the preamble/verdict.
- [templates.md](templates.md) — printed UI shapes (preamble, chunk card, prompts, end-of-review).
- [state.md](state.md) — state file location, write policy, lifecycle, and JSON shape.
- [stale.md](stale.md) — stale-PR detection and stale-inline fallback flow. Load before submit, on resume, or when `submit-review.sh` exits 4.
- [PERMISSIONS.md](PERMISSIONS.md) — recommended `settings.json` allowlist for prompt-free runs.

## Two-script architecture

Almost everything routes through two scripts on stable paths. Stick to them — inline `python3 -c` or ad-hoc `jq | bat` pipelines cost permission prompts and make sessions slow.

- `scripts/start.sh "<ref>"` — one Bash call from invocation → state file written + preamble data ready. Folds parse-ref, fetch, bat-check, diff parse, file filter, override fetches, bot detection, and state init. Emits a JSON status doc on stdout.
- `scripts/act.sh "$ENV_FILE" <sub> [args...]` — one Bash call per user action. Mutates state and emits the next card (or end-of-review doc) as JSON. See [PERMISSIONS.md](PERMISSIONS.md) for the full subcommand list.

The state file is the source of truth. To inspect it ad-hoc, use the `Read` tool — the harness file-tracker is already aware of it after `start.sh` writes it.

## Rendering UI: always use `print`

**Never hand-write ANSI templates.** The terminal interprets the ESC byte (0x1B), not the literal characters `\e`. To print any UI surface (preamble, chunk card, prompts, end-of-review summary, drafts, threads), use:

```bash
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" print <surface> [args...]
```

…and emit the stdout **verbatim** in your next message — Bash output includes real ESC bytes, which the user's terminal renders as colors. Do not paraphrase, do not reformat, do not strip the codes. Just paste the bytes through.

Surfaces (see `scripts/_render.py` for the full list):

| Surface | Use |
|---|---|
| `preamble` | After `start.sh` and `set-summary`, before the first card |
| `card [cid]` | After every state mutation that advances the queue (omit cid for queue head) |
| `prompt verdict` | At end-of-review |
| `prompt verdict-invalid` | When the user types something that isn't `a`/`c`/`r` |
| `prompt body` | After verdict is set |
| `prompt body-frame <text>` | Frame an AI-generated body |
| `prompt final-confirm` | Before `submit` |
| `prompt submitted <url> <archive>` | After successful submit |
| `prompt flagged-banner` | When main queue empties with flagged remaining |
| `prompt quit` | On action `q` |
| `prompt anchor-error <line>` | When `comment` rejects a bad anchor |
| `prompt comment-body` | Action `3` body prompt |
| `prompt open-threads <cid>` | Action `3` when chunk has open threads |
| `prompt no-threads` | Action `T` on a chunk with no threads |
| `prompt resume <rel> <done> <total>` | Resume prompt on `start.sh` returning `status=resume` |
| `prompt bat-install` | When `start.sh` returns `bat_mode=MISSING_PROMPT` |
| `end-of-review` | Summary block (then call `prompt verdict`) |
| `drafts` | Action `D` |
| `threads <cid>` | Action `T` expanded view |

[templates.md](templates.md) and [palette.md](palette.md) describe the shapes and colors for maintenance/reference. They are not LLM-facing templates anymore.

## Core loop

1. Parse arg → fetch PR data → build state → write state file → print preamble.
2. For each chunk in the queue: print the chunk card → read the user's action → execute it → update state file → next.
3. When main queue empties → flagged-queue pass.
4. When flagged queue empties → final review flow → submit to GitHub → archive state file.

Persist state after every action. The session may compact or be interrupted; resume must work.

## Startup (one Bash call)

Run the orchestrator with the user's invocation argument:

```bash
~/.claude/skills/assisted-review/scripts/start.sh "<the full ARGUMENTS string from invocation>"
```

`start.sh` does parse-ref + fetch + bat-check + diff parse + filter + override-fetches + bot-detect + state-init in one process. On success it emits a JSON status doc on stdout with these fields:

- `status`: `"ok"` (fresh start) | `"resume"` (existing valid state file) | `"invalid_ref"` | `"fetch_failed"` | `"bat_prompt"`
- `env_file`, `state_file`: paths for later calls (always pass `$env_file` as the first arg to `act.sh`)
- `bat_mode`: `HIGHLIGHT` | `PLAIN_SKIPPED` | `MISSING_PROMPT`
- `total_chunks`, `skipped_generated_count`
- `preamble`: precomputed values for the preamble template (title, author, base/head, CI tally, draft/mergeable, self_authored, body_snippet, existing_threads_open/_authors)
- `pr`: `{owner, repo, number, head_sha, url}`
- `rubric_source`: `"default"` or `"project:.claude/review-rubric.md@<short-sha>"`
- `first_chunk_id`: queue head for the first card

Handle these statuses:

| status | Action |
|---|---|
| `ok` | Generate the 2-3-sentence AI summary and persist it via `act.sh "$env_file" set-summary "<text>"`. Then print the preamble via `act.sh "$env_file" print preamble` and emit stdout verbatim. Then pre-gen the initial AI note for the first card (and ideally the next 1-2) via `act.sh "$env_file" add-note <cid> initial "<note>"` and print the card with `act.sh "$env_file" print card`. |
| `resume` | Print `act.sh "$env_file" print prompt resume <relative-time> <done> <total>`. On `r`, run `act.sh "$env_file" print card`. On `n`, `rm "$state_file"` then re-invoke `start.sh`. On `c`, stop. |
| `invalid_ref` | Surface `message` to user, stop. |
| `fetch_failed` | Surface `message`. Common cause is `gh` auth — tell the user `gh auth login`. |
| `MISSING_PROMPT` bat_mode | Before rendering the preamble, print `act.sh "$env_file" print prompt bat-install`. `y` → `~/.claude/skills/assisted-review/scripts/bat-check.sh --install`. `n` → continue plain. `s` → `bat-check.sh --mark-skip` then plain. |

The state file written by `start.sh` is complete except that AI notes (`ai_notes[]`) are empty — those are generated lazily as each card is presented (see "Per-chunk card").

For ad-hoc inspection of preamble fields, file lists, or existing threads on a chunk, **use the `Read` tool to read `$state_file` directly** — it's just JSON. Do not shell out unless you need to mutate.

## State file

See [state.md](state.md) for the file path, write policy, resume/archive lifecycle, cursor semantics, and full JSON schema.

## Per-chunk card

Print the first card explicitly:

```bash
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" print card
```

The renderer pulls the current queue head from state and emits a terminal-ready chunk card (header rule, file path, diff with bat highlighting, AI notes, existing threads, action menu) with real ESC bytes. Emit stdout verbatim — do not paraphrase.

**Subsequent cards are auto-printed by mutating subcommands** — see the Actions section. One Bash call per user action is sufficient: `act.sh "$env_file" dismiss c1` emits the next card (or the flagged-banner + next card on phase promotion, or end-of-review + verdict prompt when both queues empty).

To inspect chunk metadata without printing, read `$state_file` directly with the `Read` tool, or call `act.sh "$env_file" --json next` for the JSON form. The `--json` flag also works on mutating subcommands (`act.sh "$env_file" --json dismiss c1`) for legacy/debug.

### AI note pre-generation

The state file starts with empty `ai_notes` for every chunk. Generate the `kind:"initial"` note for the current card *and* the next 1-2 in the queue, then persist them in a single batched Bash invocation. Once `ai_notes` is non-empty for a chunk, future `render`/`next` calls include it — no re-generation needed.

Pattern: after `act.sh ... next` returns a card, generate the initial note(s) you need, then persist before printing:

```bash
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" add-note c4 initial "<note body>"
```

Investigation notes (action `4`) and context notes (action `1`) are generated on demand using the same `add-note` subcommand with kinds `investigation` and `context`. Investigation notes pass the user's prompt as the 4th arg.

On generation failure, record `add-note <cid> error "<message>"` and continue.

### Existing threads & bots

Bot detection happens in `start.sh`. The state's `existing_threads[].is_bot` flag is reliable — render `[bot]` next to the author when it's true. If you discover a new bot login that wasn't auto-flagged (`is_bot` false but the body is clearly machine-generated), append it to `~/.claude/skills/assisted-review/user-bots.txt` (one login per line; create the file if it doesn't exist). This file is gitignored so skill updates don't clobber local additions. The bundled `scripts/bots.txt` is the shared default list — propose PRs there for entries that should ship to everyone.

## Actions

After printing the card, wait for the user's next message and parse it as an action. Every state-mutating action is one `act.sh` subcommand. Do not mutate the state file directly — go through the driver.

Mutating subcommands (`dismiss`, `flag`, `defer`, `back`, `comment`) auto-print the next surface — emit stdout verbatim. They handle phase promotion (printing `flagged-banner` before the first flagged card) and end-of-review transition (printing the summary + verdict prompt when both queues empty) automatically.

### `1` — more context
Gather related code with read-only tools (Grep, Read). Budget: ≤10 tool calls. Persist the finding:

```bash
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" add-note <cid> context "<body>"
```

**Do not reprint the chunk card** — print just the new note in the AI-notes style (`↳ context:` prefix), then re-show the action menu. Cursor unchanged.

### `2` — mark viewed
```bash
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" dismiss <cid>
```

Pipes straight to the next card.

### `3` — comment
Parse the rest of the message for an anchor and optional inline body:
- `3` — whole hunk (last new-file line, RIGHT)
- `3 L<n>` — single line RIGHT, new-file line `<n>`
- `3 L<a>-<b>` — range RIGHT, new-file lines `<a>`-`<b>`
- `3 L-<n>` — single line LEFT (deleted), old-file line `<n>`
- `3 L-<a>-<b>` — range LEFT
- Append ` :: <body>` to skip the body prompt (single-turn). See "Action `3` — inline body syntax" in [templates.md](templates.md).

Pass the anchor as the third arg (empty string for whole-hunk):

```bash
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" comment <cid> "L20-22" "<body>"
# reply to an existing thread:
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" comment <cid> "L20-22" "<body>" <thread_id>
```

`_state.py` validates the anchor against the chunk's `members[]` ranges — a bad anchor exits non-zero with a clear message; show the line-anchor validation error from [templates.md](templates.md) and re-prompt.

If the chunk has open threads and no inline body was given, show the open-threads prompt from [templates.md](templates.md) before the body prompt.

### `4` — ask AI
Read the rest of the message as the prompt; if empty, ask `What should I investigate?`. Run the investigation read-only with ≤10 tool calls, output 3-5 bullets. Persist + defer:

```bash
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" add-note <cid> investigation "<body>" "<prompt>"
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" defer <cid>
```

**Not offered when this is the only chunk left in the current queue** — `is_last_in_queue: true` in the card JSON means defer-to-bottom is a no-op; drop `[4] ask AI` from the action menu.

### `5` — flag (main pass only)
```bash
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" flag <cid>
```

### `b` — back
```bash
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" back
```

The driver pops the last `dismiss`/`comment`/`flag`/`defer` from `state.history` and restores the chunk to the front of the queue. A previously-drafted comment survives — surface the `(drafted comment exists — re-comment to overwrite)` note before the action menu if `drafted_comment` in the returned card is non-null. No-op at the start of a session (the driver returns the current queue head unchanged).

### `D` — dump drafts
```bash
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" print drafts
```

Emits terminal-ready draft list, sorted by file:line. Cursor unchanged — after printing, reprint the current card with `print card` or just re-show the action menu.

### `T` — show threads
```bash
~/.claude/skills/assisted-review/scripts/act.sh "$env_file" print threads <cid>
```

Renders threads with full bodies. Falls back to `prompt no-threads` if the chunk has none.

### `R` — show resolved threads
Resolved threads aren't fetched by `start.sh` (the `comments` endpoint returns active only). If the user asks for them, fetch on demand via `gh api repos/$OWNER/$REPO/pulls/$NUMBER/comments?per_page=100` and filter for resolved replies; otherwise skip.

### `q` — quit & save
State is already persisted (every `act.sh` call writes). Print `act.sh "$env_file" print prompt quit` and stop.

## Flagged-queue pass

Handled by the driver. When the main queue empties with flagged chunks remaining, the next mutating subcommand auto-promotes to `flagged` phase and prepends the flagged-banner to the first flagged card. The renderer drops `[5] flag` from the action menu automatically in `flagged` phase.

If both queues are empty after a mutation, the driver emits the end-of-review summary + verdict prompt directly. No follow-up call required.

## Stale-PR detection

See [stale.md](stale.md). Run `stale-check.sh` before submit and on resume.

## End-of-review

The final mutating subcommand of the session (the one that empties both queues) auto-prints the end-of-review summary + verdict prompt — you don't need to call `print end-of-review` separately. From there:

1. (Done automatically.) If you need to redisplay, run `act.sh "$env_file" print end-of-review` and `act.sh "$env_file" print prompt verdict`.

2. Map verdict letters to API events: `APPROVE`, `COMMENT`, `REQUEST_CHANGES`. Also accept `e <chunk-id>` to edit a drafted comment in place. If the user types something unrecognized, print `prompt verdict-invalid` and re-print `prompt verdict`.

   Persist via:
   ```bash
   ~/.claude/skills/assisted-review/scripts/act.sh "$env_file" set-verdict APPROVE
   # or: edit-comment <cid> <draft_index> "<new body>"
   ```

3. Print the body prompt: `act.sh "$env_file" print prompt body`. On `g`, generate a body grounded in the drafts, frame it with `print prompt body-frame "<text>"`, allow edit/accept/regenerate. Persist via `act.sh "$env_file" set-body "<text>"`.

4. Print the final confirm: `act.sh "$env_file" print prompt final-confirm`.

5. On `y`:
   ```bash
   ~/.claude/skills/assisted-review/scripts/act.sh "$env_file" submit
   ```
   `act.sh submit` wraps `submit-review.sh`. The wrapper posts replies first (one POST per reply), then the main review via `gh api --input -` (sends the full JSON payload on stdin so `comments` is a real array, not a stringified one). On success the state file is archived and the review's `html_url` is printed. On generic failure (exit 1) the assembled JSON goes to stdout for manual recovery. **On `exit 4` (`STALE_INLINE`)** — run the stale-inline fallback flow in [stale.md](stale.md).

   Tip: pass `submit --dry-run` first if you want to inspect the exact POSTs before sending.

6. Print `act.sh "$env_file" print prompt submitted <html_url> <archive_path>`.

## Tone

When you (Claude) write AI notes and investigation findings: short, direct, no hedging. The reviewer is reading dozens of these in a row — every "it's worth considering" wastes their attention. Lead with the concern, then evidence.

Bad: "This change appears to potentially modify how errors are handled in a way that could possibly affect behavior."
Good: "Catches all errors including `AbortError`, so a user-cancelled request will retry 3 times before surfacing."
