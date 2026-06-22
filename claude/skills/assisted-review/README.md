# assisted-review

Interactive GitHub PR review: the human is the reviewer, Claude is the assistant. Walks the user through a PR one hunk at a time, presenting AI commentary and waiting for an action (comment, flag, ask AI, etc.) before moving on.

This README is for humans maintaining the skill. The agent loads `SKILL.md` and its references — not this file.

Distinct from the `review` skill, where Claude *is* the reviewer producing a review. See `SKILL.md` front-matter for the trigger phrases that route between the two.

## Invocation

```sh
/assisted-review <owner/repo#N | PR URL>
```

## File layout

| File             | Audience  | Purpose                                                                          |
|------------------|-----------|----------------------------------------------------------------------------------|
| `SKILL.md`       | agent     | Runbook: core loop, fetch/filter/classify, action handlers, end-of-review.       |
| `rubric.md`      | agent     | Default high/medium/low classification criteria.                                 |
| `state.md`       | agent     | State file location, write policy, lifecycle, JSON schema.                       |
| `stale.md`       | agent     | Stale-PR detection + stale-inline fallback (loaded near submit/resume only).     |
| `palette.md`     | reference | ANSI codes used by `_render.py`. Not LLM-facing — for maintainers updating the renderer. |
| `templates.md`   | reference | Original template shapes. Superseded by `_render.py`; kept as visual reference.  |
| `PERMISSIONS.md` | user      | Recommended `~/.claude/settings.json` allowlist for prompt-free runs.            |
| `scripts/`       | both      | Helper scripts the agent shells out to (see below).                              |

The agent reads `SKILL.md` + agent-tier references on demand. UI is rendered server-side by `scripts/_render.py` (invoked via `act.sh print <surface>`); the agent emits stdout verbatim and does not construct ANSI templates itself.

## Scripts

The agent shells out through two stable entry points (`start.sh`, `act.sh`); everything else is internal.

### Entry points (agent-facing)

| Script               | Role                                                                                     |
|----------------------|------------------------------------------------------------------------------------------|
| `start.sh`           | One call from invocation → parses ref, fetches, bat-check, parses diff, filters, fetches overrides, detects bots, writes state. Emits a JSON status doc. |
| `act.sh`             | Per-action driver. Mutating subcommands (`dismiss`, `flag`, `defer`, `back`, `comment`) auto-print the next surface (card, flagged-banner+card, or end-of-review+verdict). `print <surface>` emits any UI surface terminal-ready. `--json` (between env-file and subcommand) returns structured JSON instead. |
| `submit-review.sh`   | Post replies first, then the main review (via `gh api --input -` to send `comments[]` as a real array). Archives state on success. Has `--dry-run`. |

### Internal

| Script               | Role                                                                                     |
|----------------------|------------------------------------------------------------------------------------------|
| `_state.py`          | All state-file reads/writes — `dismiss`, `flag`, `defer`, `back`, `comment`, `add-note`, `set-verdict`, `set-body`, `set-summary`, `edit-comment`, `promote-flagged`, `stats`. Single chokepoint for the JSON shape. |
| `_render.py`         | All UI rendering. Emits terminal-ready text with real ESC bytes (0x1B). Surfaces: `preamble`, `card`, `end-of-review`, `drafts`, `threads`, `prompt <name>`. Invoked via `act.sh print`. |
| `parse-ref.sh`       | Parse PR ref (URL / `owner/repo#N`) and emit a sourceable env file with `STATE_FILE`.    |
| `fetch.sh`           | Run 5 `gh` calls in parallel (meta, diff, comments, checks, me) and emit a file manifest. |
| `fetch-repo-file.sh` | Fetch a file from a repo at a given SHA (used for project-override rubric/skip).         |
| `parse-diff.py`      | Parse the unified diff into a JSON array of chunks (with `members[]`). Adjacent hunks in the same file ≤20 lines apart are merged; `--group-gap N` overrides (0 disables). |
| `filter-skip.sh`     | Layer-1 generated/vendored file filter. Accepts optional project skip-list.              |
| `bat-check.sh`       | Detect/install `bat` for syntax-highlighted diff rendering. Has `--mark-skip`.           |
| `detect-bot.sh`      | Bot detection (GitHub's `user.type` is unreliable). Backed by `bots.txt`.                |
| `bots.txt`           | One bot login per line. Agent appends as it encounters new ones.                         |
| `stale-check.sh`     | Compare `state.pr.head_sha` to current PR HEAD; report `OK` / `STALE` / `CLOSED|MERGED`. |

## Extension points

- **Per-repo rubric override.** Drop a `.claude/review-rubric.md` at the PR head ref to replace the bundled `rubric.md`. The agent records the source in `state.rubric_source`.
- **Per-repo skip-list.** Drop a `.claude/review-skip.txt` at the PR head ref. Lines feed `filter-skip.sh` alongside its built-in patterns.
- **`bat` highlighting.** If `bat` is missing the agent offers to install it; "don't ask again" persists via `bat-check.sh --mark-skip`.

## State file

`~/.claude/projects/<project-slug>/scratch/review-<owner>-<repo>-<num>.json`, where `<project-slug>` is `$PWD` with `/` → `-` (e.g. `/Users/alice/work` → `-Users-alice-work`). Override the parent dir with `REVIEW_PR_SCRATCH_DIR`. Written after every action so resume survives compaction/interruption. On successful submit it's renamed to `…-submitted-<unix-ts>.json` rather than deleted. See `state.md` for the schema.

## GitHub API behaviors (verified against a real multi-commit PR, 2026-05-20)

- **Multi-line inline comments via the reviews POST** — works with `start_line` + `start_side` + `line` + `side`. The `/pulls/{n}/reviews/{id}/comments` listing returns those fields as `null`; fetch via `/pulls/comments/{id}` for the real anchor.
- **Replies via `/pulls/<n>/comments/<id>/replies`** — works. Response includes `in_reply_to_id`.
- **`commit_id` against a non-HEAD SHA** — partial. Accepted for the top-level review body, but inline comments require a SHA on the PR's own commits list (`/pulls/{n}/commits`); anything else yields `422 "Path could not be resolved"`. After a force-push that drops the reviewed SHA, inline comments will be rejected even though the body would post. `submit-review.sh` pre-flights this and exits 4 (`STALE_INLINE`); see `stale.md` for the fallback flow.

On other failures, `submit-review.sh` prints the assembled review JSON to stdout for manual recovery.

## Tests

```sh
tests/run.sh
```

Runs the Python unit tests (`tests/test_state.py`, `tests/test_render.py`) plus the shell tests (`tests/test_detect_bot.sh`). No external dependencies — pure stdlib + bash.

A pre-commit hook at `hooks/pre-commit` runs the suite automatically and aborts the commit on failure. To activate it after cloning:

```sh
git config core.hooksPath hooks
```

To bypass for an emergency commit: `git commit --no-verify` (but fix the tests).

## Rendering

UI is emitted by `scripts/_render.py` with real ANSI ESC bytes (0x1B) so the terminal renders colors correctly. The LLM never constructs `\e[…m` templates — it runs `act.sh print <surface>` and emits stdout verbatim. Mutating subcommands auto-pick the right surface based on queue state, so the typical flow is one Bash call per user action:

- Main queue still has chunks → next card
- Main empties + flagged > 0 → `flagged-banner` + first flagged card (queue auto-promoted)
- Both queues empty → `end-of-review` summary + `verdict` prompt

`act.sh "$env" --json <sub>` returns the legacy JSON form (useful for debugging or scripted callers).

## Known follow-ups

- **`cursor` shape.** `state.cursor` carries `phase` and `queue` only; the current chunk is `queue[0]` by convention. Fine but implicit.

## TODO: Marketplace readiness

Self-contained briefing for the agent that takes this on after a positive end-to-end test run. The skill works today for the original author; the work below is what's needed for downstream users installing fresh from a marketplace.

> **Prompt — Prepare `assisted-review` skill for marketplace distribution**
>
> The skill lives at `~/.claude/skills/assisted-review/`. It is a working interactive PR-review skill — a human did a positive end-to-end test and the v2 architecture (single-call `start.sh` + `act.sh` driver, JSON-payload submit fix) is in place. Read `SKILL.md`, `PERMISSIONS.md`, and `scripts/start.sh` + `scripts/act.sh` + `scripts/_state.py` first to ground yourself in the current shape before changing anything.
>
> Your job is to make it ready for downstream users who install it from a marketplace and have never seen it before. The three friction points to eliminate, in priority order:
>
> **1. First-run permission prompts.** Downstream users haven't pre-approved any of the skill's Bash commands, so every unique command shape prompts. Build a one-shot `setup` flow that writes the recommended allowlist into the user's `~/.claude/settings.json` (mirror the JSON block in `PERMISSIONS.md`). The cleanest delivery is `scripts/doctor.sh` invoked by:
> - `/assisted-review setup` (explicit) — add to the slash-command surface
> - automatically by `start.sh` on first invocation if `~/.claude/skills/assisted-review/.setup-complete` doesn't exist
>
> `doctor.sh` should: (a) verify `gh`, `jq`, `python3` exist and `gh auth status` is green, surfacing platform-specific install hints if not; (b) check `bat` and offer to install via `brew`/`apt`/`pacman`/`dnf`/`zypper` based on detected platform; (c) prompt the user before writing the allowlist (they may already have it, or want a different scope); (d) on success, touch `.setup-complete` so it doesn't re-prompt. The allowlist write should be additive — read existing `permissions.allow`, merge, write back. Don't clobber user settings.
>
> **2. Dependency / platform surprises.** Right now `bat-check.sh --install` only knows `brew install bat`. Generalize it to dispatch by platform (or have `doctor.sh` own all install logic and reduce `bat-check.sh` to detection only). Surface clear errors when `gh` isn't authenticated — currently `fetch.sh` exits non-zero with raw stderr; wrap that in a friendly frame in `start.sh`'s `fetch_failed` path that includes the literal command the user should run.
>
> **3. Path portability audit.** Most scripts use `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` (good — they work regardless of where the skill is installed). Find any remaining hardcoded `~/.claude/skills/assisted-review/...` paths in scripts and replace with `$SCRIPT_DIR/`. `grep -rn 'claude/skills/assisted-review' ~/.claude/skills/assisted-review/scripts/` and audit each hit. `SKILL.md` itself can keep `~/.claude/skills/assisted-review/scripts/...` in user-facing prose; the rule applies to scripts only.
>
> **Plus three tier-2 items** worth doing while you're in there:
> - Add `"version": 1` to the state JSON emitted by `start.sh`. Add a migration check at the top of `_state.py`'s `load()` that refuses to load mismatched versions with a clear "your draft was created by an older/newer version of the skill" message, pointing at the archive path.
> - ~~Move `scripts/bots.txt` user-additions out of the bundled file so skill updates don't clobber local edits.~~ Done — `detect-bot.sh` reads both `scripts/bots.txt` (bundled defaults, tracked) and `~/.claude/skills/assisted-review/user-bots.txt` (local additions, gitignored).
> - ~~Refresh this README's "Scripts" table to include `start.sh`, `act.sh`, `_state.py`~~ (done — also includes `_render.py` for v2.1). Still TODO: add a top-level prereqs / example invocation / troubleshooting section (`gh auth`, missing `bat`, stale-PR flow, where state lives).
>
> **Things to leave alone unless you find a bug:**
> - `parse-diff.py`, `parse-ref.sh`, `fetch.sh`, `filter-skip.sh`, `fetch-repo-file.sh`, `stale-check.sh`, `detect-bot.sh` — these are stable and battle-tested.
> - The `start.sh` → `act.sh` two-script architecture and the state JSON shape (except adding `version`).
> - The submit fix in `submit-review.sh` (line ~197, `--input -` with stdin payload). It fixed a real HTTP 422 bug.
>
> **What "done" looks like:**
> - A user pastes `/assisted-review <some-PR>` after a fresh install, gets prompted ~3-4 yes/no questions during a one-time setup, and then runs the entire review with zero further permission prompts.
> - The skill works on macOS and Linux. (Windows is out of scope; document that.)
> - This README's Scripts table reflects v2.
> - `grep` for hardcoded user-home paths in `scripts/` returns nothing.
>
> Report back with a punch list of what landed, what you skipped and why, and any decisions you want a second opinion on before publishing.
