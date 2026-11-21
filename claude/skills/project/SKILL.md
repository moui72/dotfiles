---
name: project
description: Track the state of the user's ongoing projects as markdown notes (one per project), answer "status on <project>", and, when this machine's profile names an issue tracker, diff and sync the notes against it. Use when the user asks for the status of a project by name, wants to record progress on one, asks what projects they have, or wants to sync a project with the tracker. Also use for a status report, sitrep or "what's on my plate" across everything: open todos, every project and the user's tracker issues. Also use whenever the user asks to write, add, capture or file a todo, to-do, follow-up or reminder for later, or when finished work leaves something the user should do later.
allowed-tools: [Bash, Read, Edit, Write]
---

# project: local-first project state, optionally synced to a tracker

One note per project at `<notes_dir>/<slug>.md`. **The note is the source of truth**; the tracker, if there is one, is the published view. The script owns the frontmatter and the managed story table. Edit the prose sections (`Current state`, `Questions for me`, `Planned`, `Log`) with Edit.

## Profile

Each machine has its own profile at `~/.config/project-skill/profile.json` (or `$PROJECT_SKILL_PROFILE`). The profile is never kept in this repo. It sets:
- `vault_dir`: the notes vault, which also holds `todo/` and `Todos.base` for `project todo` and `project report`
- `notes_dir`: default `<vault_dir>/projects`
- `issue_url` and `issue_field`: how `project todo` links a tracker key
- `tracker`: `none`, `jira` or `linear`. This is the default for every note.
- `github_org`: the owner for bare `repo#123` references
- `done_statuses` and `in_flight_statuses`
- `instructions`: a markdown file of machine-specific conventions
- `kick`: a shell command for `project kick`
- backend settings, such as `jira.client_dir` or `linear.api_key_file`

With no profile file, the tracker is `none`, the vault is `~/Documents`, and notes live in `~/Documents/projects`. `project profile` prints the profile in effect. **If the profile has `instructions`, read that file before syncing.** The SessionStart hook also points to it.

Tracker backends are modules in `scripts/backends/`. `__init__.py` documents the interface: issues cross the boundary as flat dicts, so nothing above that layer reads a tracker's raw JSON. To add a tracker, write `backends/<name>.py` and set `"tracker": "<name>"`.

**A note can override the default** with `tracker: <name>` in its frontmatter. That lets one machine hold Linear projects, Jira projects and local-only ones together. `init --tracker <name>` writes that line. `tracker: none` keeps a note local whatever the default is.

A note is **linked** to its tracker by its frontmatter:
- Jira: `jira_epic`, `jira_project` and `owns` (JQL for the project's issues).
- Linear: `linear_team` (the team key), and optionally `linear_project` (a project name). The note owns every issue in the team, or only that project's issues when one is named.

A note with no link is **local-only**, even on a machine with a tracker. `sync` skips it, and the SessionStart index marks it "local only".

The Linear backend reads a personal API key from `$LINEAR_API_KEY`, then the profile's `linear.api_key_cmd`, then `linear.api_key_file` (default `~/.config/project-skill/linear-api-key`). Local-only commands need no key. Linear has no workflow transitions, so a status cell can be set to any status of the issue's team.

## Status report ("what's on my plate")

`project report` is read-only and prints three sections:
- **Open todos** from `<vault_dir>/todo` (written by `project todo`), grouped by area, with due dates flagged. Open means `done: false` in the frontmatter, wherever the file sits.
- **Projects**: each note's `next:`, plus a flag when its sync or code audit is stale.
- **Tracker issues assigned to the user that no note claims**, for each tracker in use.

Turn it into a short report:
- Lead with deadlines: anything overdue or due within a week.
- Read the body of each open todo for timing pressure that isn't in `due` ("blocked until", a trial or billing date). Most todos have no `due`.
- When a todo, a project note and an issue cover the same work, say it once.
- If the tracker line says "not reachable" and this session has a connector for it, fetch the user's open issues with the connector and leave out the keys already in the project tables. With no connector, say so in one line.
- Never mark a todo done and never write to the tracker from a report. Don't run `sync` here; suggest it for a stale project.

`--offline` skips the tracker and the vault pull. Without it, the vault is pulled first when it has an upstream and no uncommitted edits.

## Todos

A todo is something for the user to do later, tied to a project or not. Each is a note in `<vault_dir>/todo/`, and Obsidian's `Todos.base` shows them as views. The script owns the format: never hand-write a todo file or edit its frontmatter.

```bash
project todo "Re-scope ABC-123 after the API change" \
  [--area AREA] [--issue ABC-123] [--due 2026-09-30] [--body-file FILE | --body -]
```

- **Title**: short and imperative. It becomes `title:`, the H1 and the file name (lowercase ASCII, hyphens, at most 60 characters; `--slug` overrides).
- **`--area`**: a closed vocabulary, one per view in `Todos.base`. `project todo --list-areas` prints it. Pick the closest one or leave it out. If the script warns that an area is new, tell the user it shows only in the Active view until they add a view.
- **`--issue`**: a tracker key or a URL. A bare key (or a Jira browse URL) becomes the profile's `issue_url`; any other URL is kept. Include it whenever the work maps to an issue.
- **`--due`**: only when the user gives or clearly implies a date. Convert relative dates to absolute ones.
- **Body**: markdown through `--body -` (stdin) or `--body-file`. Say why it matters, link the source (`[[note]]` for vault notes, URLs for issues and PRs), and add `- [ ]` steps when there is more than one. Don't start with an H1.
- The new file is committed on its own, and pushed when the vault has an upstream. `--no-commit` skips that. `--dry-run` prints the note and writes nothing.
- The script never overwrites a todo, including one in `todo/completed/`. If it refuses, pass a more specific `--slug`; don't delete the existing file.

Rules:
- **Never mark a todo done** or set `done: true`. That is the user's click in Obsidian.
- Don't restructure existing todos. Appending to an open todo's body is fine when asked; leave its frontmatter alone.
- Finish with the path (`todo/<slug>.md`) in one line. When a todo comes out of a longer task, also say what it captures.

## Commands

```bash
P=~/.claude/skills/project/scripts/project   # also symlinkable as `project` on PATH
$P profile
$P list
$P todo 'Title' [--area A] [--issue KEY] [--due DATE]   # write a todo note (see Todos)
$P report [--offline]             # everything on the user's plate: todos, projects, unclaimed tracker issues
$P status 'my proj'                # NAME matches title, slug, alias or epic key
$P audit 'my proj' [--since YYYY-MM-DD]   # read-only: note vs PRs/releases in `repos:`
$P audit 'my proj' --stamp         # record last_audited once the note is updated
$P init 'Name' --alias foo         # a local-only note (any tracker)
$P init 'Name' --epic KEY-1 --owns 'parent = KEY-1' --alias foo   # tracker jira: seeds the table
$P init 'Name' --team ENG [--project 'Project name'] --alias foo  # tracker linear: seeds the table
$P init 'Name' --tracker linear --team ENG   # use a tracker other than the profile's default for this note
$P accept 'my proj' KEY-1          # take a line under ## Proposed status changes: sets the status cell, drops the line
$P reject 'my proj' KEY-1          # drop a proposal
# linked notes only:
$P sync ['my proj']                # DRY RUN: outbound, creates, comments, inbound, conflicts
$P sync 'my proj' --apply [--only K1,K2] [--no-commit]   # WRITES to the tracker
$P sync 'my proj' --pull [--no-commit]   # inbound only: updates the note, never writes the tracker
$P resolve 'my proj' KEY-1 --keep tracker|local          # settle a sync conflict (local = queue a transition)
$P kick                            # the profile's kick command
# connector mode (no API credential; see below):
$P snapshot 'my proj'               # what to fetch with the tracker's connector
$P sync 'my proj' --snapshot FILE [--pull | --apply --results FILE]
$P audit 'my proj' --local          # audit from the note's table, without asking the tracker
```

## Verbs

- **"status on X"**: run `status X`. For a linked note, also run `sync X` for the live delta. Lead with `next`, blockers, and anything inbound (new stories, comments from others). With a tracker, warn when `last_synced` is older than `stale_days`.
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
- **"sync X"** (linked notes only): run the dry run and show it. Run `--apply` only after the user approves that plan, because it writes to the tracker. `--only K1,K2` pushes just those keys' transitions and comments: no creates, no inbound, and `last_synced` is unchanged.

## Sync model (linked notes only)

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
- Unkeyed `- [ ] summary` lines under `## Planned` become story creates under the project's epic (Jira) or in its team and project (Linear). The user is assignee and reporter. The new row takes the status the tracker gave the issue. A summary identical to an existing child is blocked as a duplicate.
- `- KEY: text` lines under `## Comments to post` become comments.

`--apply` runs in this order:
1. transitions
2. comments
3. creates
4. inbound

Every tracker write is saved to the note before the next one, so a crash never loses a created key. It stops at the first failure and does not advance `last_synced`. Transitions are verified by re-reading the issue status.

After the writes, apply records the inbound items in the note (status pulls, adopted stories, others' comments), advances `last_synced`, and commits only that note if the notes dir is in a git repo (rebase and retry on a rejected push). Conflicting keys are left untouched. `--apply` and `--pull` take an exclusive lock (`<notes_dir>/.sync.lock`), so two sessions can't sync at once, and each re-plans under the lock. Exit code 75 means the lock is busy: retry shortly.

## Connector mode (no API credential)

Use this when `sync` fails for want of a credential (for Linear: no API key) and this session has a connector for the tracker, such as the Linear MCP tools. The script can't call a connector, so you carry the data. Reads come from a snapshot file you write; writes are made by you and recorded in a results file. The formats are in `scripts/backends/snapshot.py`.

1. **Ask what to fetch.** Run `snapshot X`. It prints the scope (for Linear, the team and project), `updated_after`, and the two file paths.
2. **Fetch with the connector.**
   - your own name in the tracker
   - the team's status names
   - every issue in scope updated after `updated_after`, all pages, with key, title, status, assignee, creator and updatedAt
   - for each of those issues, its comments. Keep only comments created after `updated_after`.
3. **Write the snapshot file** at the path from step 1. Copy values exactly as the connector returned them. Never fill in an issue or a status from memory. An issue that wasn't returned is left out; the script treats it as unchanged.
4. **Dry run:** `sync X --snapshot FILE`. Show the plan. If it lists tracker writes, it prints them as JSON.
5. **Inbound only:** `sync X --pull --snapshot FILE`. This needs no approval and no results file.
6. **Outbound, after the user's yes:** make each listed write with the connector, in the listed order. Stop at the first failure.
   - `transition`: set the issue's status, then read the status back from the connector's reply.
   - `comment`: post the comment.
   - `create`: create the issue in the listed team and project, assigned to the user. Record the new key and status.

   Write one outcome per write to the results file, including a failed one (`"ok": false, "error": "..."`). Then run `sync X --apply --snapshot FILE --results RESULTS`.

Rules for this mode:
- One project at a time. `sync` with no name isn't available.
- Take a fresh snapshot for every sync. `last_synced` advances to the snapshot file's modified time, so an old file hides nothing but also shows nothing new.
- Record only what the connector confirmed. If a write's reply is unclear, read the issue back before recording `"ok": true`.
- A snapshot holds only recent changes, so an issue that was deleted or moved out of the team is not noticed in this mode.
- To seed a new note, fetch every open issue in scope and run `init 'Name' --team KEY --snapshot FILE`.

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

  Either do the upkeep or say in one line why the work isn't project work. The hook does nothing when the project is local-only or when `PROJECT_UPKEEP_HEADLESS` is set.

## Rules

- Never run `--apply` (or any tracker write) without showing the dry-run plan first and getting the user's go-ahead. Tracker edits are visible to other people.
- If the notes dir is in a git repo, commit only the touched note files.
- Python here uses keyword arguments.
