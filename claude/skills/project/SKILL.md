---
name: project
description: Track the state of the user's ongoing projects as markdown notes (one per project), answer "status on <project>", and, when this machine's profile names an issue tracker, diff and sync the notes against it. Use when the user asks for the status of a project by name, wants to record progress on one, asks what projects they have, or wants to sync a project with the tracker. For open todos and a cross-project sitrep use status-report; to file a todo use todo.
allowed-tools: [Bash, Read, Edit]
---

# project: local-first project state, optionally synced to a tracker

One note per project at `<notes_dir>/<slug>.md`. **The note is the source of truth**; the tracker, if there is one, is the published view. The script owns the frontmatter and the managed story table. Edit the prose sections (`Current state`, `Questions for me`, `Planned`, `Log`) with Edit.

## Profile

Each machine has its own profile at `~/.config/project-skill/profile.json` (or `$PROJECT_SKILL_PROFILE`). The profile is never kept in this repo. It sets:
- `notes_dir`
- `tracker`: `none` or `jira`
- `github_org`: the owner for bare `repo#123` references
- `done_statuses` and `in_flight_statuses`
- `instructions`: a markdown file of machine-specific conventions
- `kick`: a shell command for `project kick`
- backend settings, such as `jira.client_dir`

With no profile file, the tracker is `none` and notes live in `~/Documents/projects`. `project profile` prints the profile in effect. **If the profile has `instructions`, read that file before syncing.** The SessionStart hook also points to it.

Tracker backends are modules in `scripts/backends/`. `__init__.py` documents the interface: issues cross the boundary as flat dicts, so nothing above that layer reads a tracker's raw JSON. To add a tracker, write `backends/<name>.py` and set `"tracker": "<name>"`.

## Commands

```bash
P=~/.claude/skills/project/scripts/project   # also symlinkable as `project` on PATH
$P profile
$P list
$P status 'my proj'                # NAME matches title, slug, alias or epic key
$P audit 'my proj' [--since YYYY-MM-DD]   # read-only: note vs PRs/releases in `repos:`
$P audit 'my proj' --stamp         # record last_audited once the note is updated
$P init 'Name' --alias foo         # tracker none
$P init 'Name' --epic KEY-1 --owns 'parent = KEY-1' --alias foo   # tracker jira: seeds the table
$P accept 'my proj' KEY-1          # take a line under ## Proposed status changes: sets the status cell, drops the line
$P reject 'my proj' KEY-1          # drop a proposal
# tracker only:
$P sync ['my proj']                # DRY RUN: outbound, creates, comments, inbound, conflicts
$P sync 'my proj' --apply [--only K1,K2] [--no-commit]   # WRITES to the tracker
$P sync 'my proj' --pull [--no-commit]   # inbound only: updates the note, never writes the tracker
$P resolve 'my proj' KEY-1 --keep tracker|local          # settle a sync conflict (local = queue a transition)
$P kick                            # the profile's kick command
```

## Verbs

- **"status on X"**: run `status X`. With a tracker, also run `sync X` for the live delta. Lead with `next`, blockers, and anything inbound (new stories, comments from others). With a tracker, warn when `last_synced` is older than `stale_days`.
- **"update X: ..."**: Edit the note: append a dated line to `## Log`, revise `## Current state` (declarative, point-in-time, no history), and set `next:`. To change a story's status, edit its `status` cell in the table and leave `synced` alone. `sync` turns the difference into an outbound transition.
- **"projects"**: `list`.
- **"audit X"**: run `audit X` and read the report. It draws on the project's `repos:` (frontmatter) and lists:
  - open PRs
  - PRs merged since `last_audited`
  - the latest releases and component tags
  - open stories whose PRs are all merged (candidates for Done)
  - in-flight stories with no PR
  - PR references in the note that contradict the PR's real state

  Then fix the note: update `## Current state` and set story statuses in the table. A merged PR is evidence, not proof, so ask about acceptance criteria and human steps. With a tracker, run `sync` for the plan and wait for approval. Finish with `audit X --stamp`. A PR is tied to a story only when the story's key appears in the PR's title, branch, or first line of the body; a passing mention elsewhere doesn't count. `audit` never writes to the tracker and never edits the note except with `--stamp`.
- **"sync X"** (tracker only): run the dry run and show it. Run `--apply` only after the user approves that plan, because it writes to the tracker. `--only K1,K2` pushes just those keys' transitions and comments: no creates, no inbound, and `last_synced` is unchanged.

## Sync model (tracker only)

For each tracked key, `synced` holds the tracker's status as of the last sync:
- Only the local status changed → outbound transition.
- Only the tracker's status changed → inbound (pulled into the note).
- Both changed and they differ → conflict; ask the user.

Transitions are chosen by **target status**, because a workflow's transition names can differ from its status names.

Inbound picks up:
- stories new under `owns`
- tracker-side status or assignee changes
- comments from anyone but the user since `last_synced`, on every owned issue including closed ones (only issues updated since the last sync are fetched)

Put others' questions under `## Questions for me`. `sync` with no name also lists open stories assigned to the user that no project claims.

Outbound also covers two prose sections:
- Unkeyed `- [ ] summary` lines under `## Planned` become story creates under the project's epic. The user is assignee and reporter. A summary identical to an existing child is blocked as a duplicate.
- `- KEY: text` lines under `## Comments to post` become comments.

`--apply` runs in this order:
1. transitions
2. comments
3. creates
4. inbound

Every tracker write is saved to the note before the next one, so a crash never loses a created key. It stops at the first failure and does not advance `last_synced`. Transitions are verified by re-reading the issue status.

After the writes, apply records the inbound items in the note (status pulls, adopted stories, others' comments), advances `last_synced`, and commits only that note if the notes dir is in a git repo (rebase and retry on a rejected push). Conflicting keys are left untouched. `--apply` and `--pull` take an exclusive lock (`<notes_dir>/.sync.lock`), so two sessions can't sync at once, and each re-plans under the lock. Exit code 75 means the lock is busy: retry shortly.

## Hooks

Both hooks live in `hooks/` and are registered in `settings.json`.

- **`project_context.py`** runs at SessionStart and on each prompt.
  - At SessionStart it injects the project index, the upkeep rule, and the profile's `instructions` pointer, and it flags a git branch named for a tracked story.
  - On each prompt it adds one line when the prompt names a tracked story key or a project's title or alias.
  - The upkeep rule: at checkpoints, keep the note current. With a tracker, also run the dry run before finishing, `--pull` inbound changes without asking, and show anything that writes to the tracker and wait for a yes before `--apply`.
- **`project_stop.py`** blocks a turn's stop, once per checkpoint, when all of these hold:
  - The session ran `gh pr create|merge|ready` as a command (not as text inside a heredoc). Commits and pushes don't count.
  - The work belongs to a tracked project. Story keys in those commands or in the branch name decide this, and the prompts are the fallback.
  - No `sync` has run since.

  Either do the upkeep or say in one line why the work isn't project work. The hook does nothing when the tracker is `none` or when `PROJECT_UPKEEP_HEADLESS` is set.

## Rules

- Never run `--apply` (or any tracker write) without showing the dry-run plan first and getting the user's go-ahead. Tracker edits are visible to other people.
- If the notes dir is in a git repo, commit only the touched note files.
- Python here uses keyword arguments.
