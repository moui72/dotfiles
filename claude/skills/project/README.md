# project

A Claude Code skill that keeps one markdown note per project you're working on, so that any session can answer "where does this stand?" and keeps the answer current as work lands. If you use an issue tracker (Linear or Jira), it also keeps the note and the tracker in step, and it never writes to the tracker without showing you the plan first.

This README is for people. The agent reads `SKILL.md`.

## What it's for

Claude Code sessions start with no memory of your projects. You end up re-explaining what's shipped, what's in flight and what's next, and the tracker drifts from reality because nobody updates it after a PR merges.

This skill fixes that with three parts:

- **A note per project.** Each is a plain markdown file you can read, edit and keep in git. It holds the current state, the next step, open questions, a table of open issues and a dated log.
- **Hooks that make sessions notice.** Every session starts with a short index of your projects. When a prompt or a git branch names a project or one of its issues, the session is told which note to keep current.
- **A command-line tool, `project`.** It creates notes, compares them with your GitHub repos, and syncs them with the tracker.

The note is the source of truth. The tracker is the published view of it.

## What using it looks like

You talk to Claude as usual:

| You say | What happens |
|---|---|
| "status on garden" | Claude reads the note and leads with the next step, blockers and anything new from the tracker. |
| "update garden: the planting calendar merged" | Claude revises `## Current state`, sets `next:`, and adds a dated line to `## Log`. |
| "what projects do I have?" | One line per project, with its status and next step. |
| "audit garden" | Claude compares the note with the repo's open and merged PRs and releases, and points out where the note is out of date. |
| "sync garden" | Claude shows a dry-run plan: what it would change in the tracker and what changed there. Nothing is written until you say yes. |

You often don't have to ask. When a session opens or merges a PR for a tracked project, the hooks remind it to update the note before it finishes.

## A project note

```markdown
---
title: Garden Planner
aliases: [garden]
status: active
linear_team: ENG
repos: [acme/garden-planner]
next: get the planting calendar reviewed and merged
stale_days: 7
last_synced: 2026-11-20T17:52:10-05:00
---
# Garden Planner

## Current state
- Sign-in and garden beds are live in production.
- garden-planner#12 (ENG-1) is open for review: the planting calendar.

## Questions for me

## Open stories
<!-- jira:stories -->
| key | status | synced | summary | assignee |
|---|---|---|---|---|
| ENG-1 | In Progress | In Progress | Planting calendar | Sam Rivera |
| ENG-2 | Todo | Todo | Frost date lookup | Unassigned |
<!-- /jira:stories -->

## Planned
- [ ] Email a weekly watering reminder

## Comments to post

## Log
- 2026-11-20: note created from Linear (2 open stories)
```

- **Frontmatter and the table** belong to the tool. The table markers say `jira:stories` for every tracker; the name is historical.
- **The prose sections** are yours and Claude's to edit. `Current state` says what is true now, with no history. History goes in `Log`.
- **`status` and `synced`** are how sync works. `synced` is the tracker's status as of the last sync. To move an issue, change its `status` cell and leave `synced` alone.

## How sync works

For each issue in the table, the tool compares three values: the note's `status`, the note's `synced`, and the tracker's live status.

| What changed since the last sync | Result |
|---|---|
| Only the note | Outbound: the tracker issue is moved to the note's status. |
| Only the tracker | Inbound: the note takes the tracker's status. |
| Both, to different statuses | Conflict: you choose with `project resolve`. |

Sync also carries these:

- **New issues in the tracker** are added to the table.
- **Comments from other people** since the last sync land under `## Questions for me`.
- **`- [ ] summary` lines under `## Planned`** become new issues, assigned to you.
- **`- KEY: text` lines under `## Comments to post`** are posted as comments.

`project sync NAME` is always a dry run. `--apply` writes to the tracker, and the skill's rules tell Claude to show you the plan and wait for a yes first. `--pull` takes inbound changes only and never writes to the tracker. Each tracker write is saved to the note before the next one, so a failure partway through loses nothing.

## Trackers

| Tracker | A note is linked by | Needs |
|---|---|---|
| none | (nothing to link) | Nothing. The notes are the whole record. |
| Linear | `linear_team`, and optionally `linear_project` | A personal API key. |
| Jira Cloud | `jira_epic`, `jira_project`, and `owns` (JQL) | Your own `_client.py`; see `scripts/backends/jira.py`. |

The profile sets a machine's default tracker. A note can override it with `tracker: linear`, `tracker: jira` or `tracker: none` in its frontmatter, so one machine can hold projects from different trackers. `project init NAME --tracker linear ...` writes that line for you.

A note with no link is **local-only**, even on a machine with a tracker: it still shows up in the index and can be audited, and sync skips it.

**Linear.** A note owns every issue in its team, or only one project's issues if `linear_project` is set. Create a personal API key in Linear under Settings, Security & access, then either export `LINEAR_API_KEY` or save the key to `~/.config/project-skill/linear-api-key` and `chmod 600` it. You can also set `linear.api_key_cmd` in the profile to read it from a password manager. The backend uses only Python's standard library.

**Linear without a key (connector mode).** Inside a Claude session that has a Linear connector, sync works with no API key. The `project` tool can't call a connector itself, so Claude carries the data: it fetches recent issues and comments through the connector, hands them to the tool as a file, and makes any approved writes through the connector before the tool records them in the note. It is slower than the key and only works inside a session, so the key is still the better setup where you can have one. The same mode works for any tracker that has both a backend here and a connector in your session.

**Another tracker.** A backend is one module in `scripts/backends/` with about fifteen small methods. `scripts/backends/__init__.py` documents the interface, and `linear.py` is the one to copy.

## Install

Requirements: Claude Code, Python 3.9 or later, and the GitHub CLI (`gh`) for `audit`.

If you use this whole dotfiles repo, `claude/install.sh` does steps 1 and 2.

1. **Put the skill where Claude Code finds it.**

   ```bash
   git clone https://github.com/moui72/dotfiles ~/dev/dotfiles
   ln -s ~/dev/dotfiles/claude/skills/project ~/.claude/skills/project
   ```

2. **Put the tool on your PATH.**

   ```bash
   mkdir -p ~/.local/bin
   ln -s ~/.claude/skills/project/scripts/project ~/.local/bin/project
   ```

3. **Register the hooks** in `~/.claude/settings.json`. If you already have a `hooks` section, add these entries to it.

   ```json
   {
     "hooks": {
       "SessionStart": [
         {"hooks": [{"type": "command", "command": "python3 ~/.claude/skills/project/hooks/project_context.py", "timeout": 10}]}
       ],
       "UserPromptSubmit": [
         {"hooks": [{"type": "command", "command": "python3 ~/.claude/skills/project/hooks/project_context.py", "timeout": 10}]}
       ],
       "Stop": [
         {"hooks": [{"type": "command", "command": "python3 ~/.claude/skills/project/hooks/project_stop.py", "timeout": 10}]}
       ]
     }
   }
   ```

4. **Write a profile** (optional). With no profile, there is no tracker and notes live in `~/Documents/projects`. To change that, copy `profile.example.json` to `~/.config/project-skill/profile.json` and edit it. The profile is per machine and is never kept in this repo.

   | Key | Meaning |
   |---|---|
   | `notes_dir` | Where the notes live. Put it in a git repo if you want history. |
   | `tracker` | `none`, `linear` or `jira`. The default; a note can override it. |
   | `github_org` | The owner assumed for a bare `repo#123` reference in a note. |
   | `done_statuses` | Statuses that count as closed. For Linear, use `["Done", "Canceled", "Duplicate"]`. |
   | `in_flight_statuses` | Statuses that mean someone is working on it. |
   | `instructions` | A markdown file of your own conventions. Claude reads it before syncing. |
   | `kick` | A shell command for `project kick`, such as refreshing a token. |

5. **Create your first note.**

   ```bash
   project init 'My Project' --alias mp                  # local-only
   project init 'My Project' --team ENG --alias mp       # Linear: seeds the table from the team
   project init 'My Project' --epic KEY-1 --owns 'parent = KEY-1'   # Jira
   project init 'My Project' --tracker linear --team ENG  # not the default tracker? name it
   ```

   Then add `repos: [owner/repo]` to the frontmatter so `audit` knows where to look, and ask Claude to fill in `## Current state`.

Run `project profile` at any time to see the settings in effect.

## Commands

```bash
project profile                      # the settings in effect on this machine
project list                         # one line per project
project status NAME                  # the note, with staleness warnings
project audit NAME [--since DATE]    # read-only: the note against PRs and releases
project audit NAME --stamp           # record that the note was brought up to date
project sync [NAME]                  # dry run
project sync NAME --pull             # take inbound changes; never writes to the tracker
project sync NAME --apply            # write to the tracker
project snapshot NAME                # connector mode: what Claude should fetch
project sync NAME --snapshot FILE    # connector mode: plan from what Claude fetched
project resolve NAME KEY --keep tracker|local
```

`NAME` matches a note's title, file name or alias, in full or in part.

## What the hooks do

- **`hooks/project_context.py`** runs when a session starts and on each prompt. At the start it prints the project index and the upkeep rule. On a prompt it adds one line if the prompt names a project or one of its open issues. It reads only the local notes, so it is fast and makes no network calls.
- **`hooks/project_stop.py`** runs when Claude is about to finish a turn. If the session opened or merged a PR for a linked project and hasn't run a sync since, it asks Claude once to update the note and show you the sync plan. It does nothing for local-only projects.

Neither hook can fail a session: any error is printed and ignored.

## Limits

- Titles and aliases shorter than four characters aren't matched in prompts, to avoid false hits. Give a short-named project a longer alias.
- A PR counts toward an issue only when the issue's key is in the PR's title, branch name or the first line of its body.
- `audit` trusts merged PRs only as evidence. Claude is told to ask about acceptance criteria before marking anything Done.
- With Linear, an issue created from `## Planned` lands in the note's team (and project, if set) with the team's default status.

## Development

```bash
python3 -m pytest claude/skills/project/tests
```

The tests run the Linear backend, connector mode and the command-line tool against an in-memory fake of Linear's API. They need no key and no network.

| Path | Purpose |
|---|---|
| `SKILL.md` | What the agent reads: commands, verbs, the sync model, rules. |
| `scripts/project.py` | The command-line tool. It owns the note format. |
| `scripts/skill_profile.py` | Loads the per-machine profile. |
| `scripts/backends/` | One module per tracker: `none.py`, `linear.py`, `jira.py`. `snapshot.py` is connector mode. |
| `hooks/` | The session hooks. |
| `profile.example.json` | A profile to copy. |
| `tests/` | Tests for the Linear backend and the tracker-neutral paths. |
