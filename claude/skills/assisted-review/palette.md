# Color palette

**Reference / maintenance only.** This skill renders UI server-side via `scripts/_render.py` (invoked through `act.sh print <surface>`). The LLM does NOT construct ANSI templates — it just emits the bytes from those commands verbatim. This document exists so that future edits to `_render.py` stay consistent with the existing visual style.

If you find yourself about to write `\e[1;36m…\e[0m` into the LLM's output: stop. Terminals interpret the actual ESC byte (0x1B), not the two characters `\` + `e`. Use `act.sh print` instead.

| Code            | Role                                                       |
|-----------------|------------------------------------------------------------|
| `\e[1;36m`      | bold cyan — banners, header rules, structural lines        |
| `\e[1m`         | bold — section labels (AI notes, Verdict, Actions, …)      |
| `\e[1;37m`      | bold white — file paths, PR refs, emphasized identifiers   |
| `\e[36m`        | cyan — URLs                                                |
| `\e[2m`         | dim — bracketed action keys `[x]`, secondary info          |
| `\e[2;35m`      | dim magenta — hunk headers (`@@ ... @@`)                   |
| `\e[33m`        | yellow — `[bot]` markers, warnings                         |
| `\e[1;33m`      | bold yellow — medium-rating tag, attention                 |
| `\e[1;31m`      | bold red — high-rating tag, errors, request-changes verdict|
| `\e[1;32m`      | bold green — low-rating tag, success, approve verdict      |
| `\e[31m`        | red — removed/destructive                                  |
| `\e[32m`        | green — added/approved                                     |
| `\e[0m`         | reset — close every styled span                            |

Application rules:
- Section labels are always `\e[1m…\e[0m`.
- Action key brackets are always `\e[2m[\e[0mx\e[2m]\e[0m`.
- URLs are `\e[36m…\e[0m`.
- Verdict words use their rating color (`APPROVE` green, `COMMENT` cyan, `REQUEST_CHANGES` red).
- Rating colors: `high` → `31` (red), `medium` → `33` (yellow), `low` → `32` (green). Emojis: 🔴 high, 🟡 medium, 🟢 low.

## Conditional styling rules

These rules govern when to apply or omit styling based on PR state. They are referenced from templates in [templates.md](templates.md).

**Preamble — mergeable indicator** (`<mergeable-styled>` token):
- `yes` → `\e[32myes\e[0m`
- `no (CONFLICTING)` → `\e[1;31mno (CONFLICTING)\e[0m`
- `unknown` → `\e[2munknown\e[0m`

**Preamble — CI counts**: if 0 failing checks, drop the `<fail-count> failing` span entirely (don't print red "0 failing").

**Preamble — draft warning**: if the PR is a draft, insert this line just below the `URL:` line:
```
\e[1;33mWarning:\e[0m this is a draft PR. The author may not be ready for feedback.
```

**Preamble — mergeability warning**: if mergeable is `CONFLICTING` or any CI check is failing, also insert:
```
\e[1;33mNote:\e[0m PR is not currently mergeable.
```

**Preamble — rubric source line**: append a dim trailing line beneath the hunk-counts block:
```
\e[2mRubric: <source>\e[0m
```
where `<source>` is `default` or `project:.claude/review-rubric.md@<short-head-sha>`.

**Preamble — skip-inspection responses** (when user hits `s` or `S`):
- `s` → list no-risk skipped chunks, one per line: `\e[1;37m<file>:<lines>\e[0m — <summary>`. Offer `\e[1mp <id>\e[0m` to promote any back to the queue. Then re-prompt.
- `S` → list generated-file skips by filename in `\e[2m…\e[0m`. Then re-prompt.

**Verdict prompt — self-authored**: if `state.preamble.self_authored` is true, omit the `[a] approve` option from the verdict prompt.
