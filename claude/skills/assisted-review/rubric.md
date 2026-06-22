# Safety Rubric

Loaded by SKILL.md during filtering (no-risk criteria) and classification (per-chunk high/medium/low rating).

Assign exactly one rating per chunk: `high`, `medium`, or `low`. Rating is informational only — it never blocks an action.

If you're torn between two levels, pick the higher one. Reviewer attention is the budget; over-flagging is recoverable, under-flagging is not.

## 🔴 High

Any one of these triggers high:

- Touches auth, authz, sessions, tokens, secrets, crypto
- Touches payments, billing, money math, PHI/PII handling
- Database migrations, schema changes, destructive SQL
- Changes to deployment, CI/CD, IaC, secrets management
- Deletes or weakens tests, assertions, or validation
- Modifies a public API contract — route path, response shape, exported function signature
- Concurrency primitives — locks, transactions, queues, retries, mutexes, channels

## 🟡 Medium

Any one of these triggers medium (and none of the high triggers fire):

- New external calls (HTTP, DB queries) in code that looks hot-path
- Error handling / retry / timeout changes
- Logging that might leak sensitive data
- Touches a file the PR author rarely edits (rough heuristic — look at `git log --author=<author> -- <file>` if needed)
- Large hunk (>~50 changed lines)
- Mixes refactor + behavior change in one hunk

## 🟢 Low

Everything else. Pure refactors, tests added, docs, formatting beyond the no-risk threshold, dependency bumps, internal helpers that aren't called from anywhere risky.

## 🟢⁰ No risk (auto-skipped — do not queue)

These are filtered before the rubric runs. Strict criteria:

- Pure whitespace / line-ending changes
- Comment-only changes (no code lines modified)
- Import sort order changes with no adds/removes
- Trailing comma additions only
- Rename of a local (non-exported) variable

If you're uncertain whether something is no-risk: it's not. Default to low and queue it.

## Project overrides

Repos can override this file by placing `.claude/review-rubric.md` at the repo root. When that file exists, use it instead. The skill records which rubric was loaded in `state.rubric_source`.
