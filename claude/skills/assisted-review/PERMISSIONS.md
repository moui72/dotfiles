# Reducing permission prompts

Most of the per-action latency in `assisted-review` historically came from one source: each unique Bash command shape triggers a separate permission prompt under exact-match allowlists. The skill drives ~2 Bash calls per chunk, plus an ad-hoc submit fallback if anything goes wrong, so a 10-chunk PR can rack up 20+ prompts.

After the v2 refactor, almost everything runs through two stable script paths (`start.sh` and `act.sh`). Allowing those two paths up-front cuts the prompts down to one approval at the top of the session.

## Recommended allowlist

Add this to `~/.claude/settings.json` (or the per-project `.claude/settings.json`) under the `permissions.allow` array:

```json
{
  "permissions": {
    "allow": [
      "Bash(~/.claude/skills/assisted-review/scripts/start.sh:*)",
      "Bash(~/.claude/skills/assisted-review/scripts/act.sh:*)",
      "Bash(~/.claude/skills/assisted-review/scripts/submit-review.sh:*)",
      "Bash(gh api:*)",
      "Bash(gh pr view:*)",
      "Bash(gh pr diff:*)",
      "Bash(gh pr checks:*)",
      "Bash(jq:*)",
      "Bash(bat:*)"
    ]
  }
}
```

After this, the only prompt you should see is at the very first invocation if Claude needs to install `bat` via `brew install bat`. That prompt can be dismissed and `bat` can be installed later — diffs still render plain.

## Pre-approving the bat install

If you know you want highlighting, also add:

```json
"Bash(brew install bat)"
```

…and the first run will be fully prompt-free.

## What `act.sh` covers

A single stable script path with a small subcommand surface — none of the per-card actions invent new Bash command shapes:

| Subcommand | Use |
|---|---|
| `next` | Print current queue head |
| `render <cid>` | Print a specific chunk's card |
| `dismiss <cid>` | Action `2` — mark viewed + advance |
| `flag <cid>` | Action `5` — flag + advance |
| `defer <cid>` | Action `4` — move to bottom of queue |
| `back` | Action `b` — undo last queue op |
| `comment <cid> <anchor> <body> [reply_to]` | Action `3` — draft a comment |
| `add-note <cid> <kind> <body> [prompt]` | Persist an AI note |
| `set-verdict <APPROVE\|COMMENT\|REQUEST_CHANGES>` | End-of-review verdict |
| `set-body <text>` | End-of-review body |
| `edit-comment <cid> <idx> <body>` | Edit a draft at verdict step |
| `stats` | Review counters |
| `drafts` | Drafts dump (action `D`) |
| `end-of-review` | Final summary + draft list |
| `submit [--dry-run]` | Wrap `submit-review.sh` |
