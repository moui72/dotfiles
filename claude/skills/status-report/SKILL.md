---
name: status-report
description: Produce a situation report on the user's open todos, tracked projects and, when this machine has a tracker, in-flight tracker issues. Use when the user runs /status-report or asks for a status report, sitrep, or "what's on my plate". To create a todo, use the `todo` skill.
---

# Status report

Assemble a concise situation report from the todos in the notes vault, the `project` skill's project notes, and, if this machine's profile names a tracker, in-flight tracker work. New todos are created with the `todo` skill.

**Mutation scope.** The tracker is strictly read-only: never transition, comment on, or edit an issue. The vault is writable, but only through the scripts below: create todo notes and sync git. Never mark a todo done; clicking the checkbox in Obsidian is the user's action, not yours.

**Profile.** Run `~/.claude/skills/project/scripts/project profile` first. It gives `vault_dir`, `tracker` and `instructions`. If `instructions` names a file, read it: it holds this machine's tracker queries and vault quirks. `$OBSIDIAN_VAULT` overrides `vault_dir`.

## 0. Sync first

```bash
~/.claude/skills/status-report/scripts/vault-sync.sh pull
```

Report the one-line result. If it says PULL FAILED, say so and continue with local state.

## 1. Open todos

Status is the `done` frontmatter property, **not** the folder. `todo/completed/` is an optional archive; a note can be `done: true` and still sit in `todo/`. Read through the real vault path: `find` does not descend into symlinked directories.

```bash
grep -rl '^done: false' "<vault_dir>/todo" --include='*.md'
```

For each hit, read the frontmatter (`title`, the issue-link field, `area`, `due`) plus the first ~15 lines of the body for the gist. Group by `area`. Surface `due` dates prominently, and flag anything past due or imminent. Also note timing pressure stated in the body ("blocked until", "earliest deletable", trial or billing deadlines) even when `due` is empty; most notes have no `due` set.

## 2. Projects

Run `project list`. For each project, report `next:` in one line. Flag a project whose `last_synced` or `last_audited` is stale (`project status NAME` warns). Don't run `sync` here.

## 3. In-flight tracker work (tracker ≠ none)

Query the issues assigned to the user that aren't finished, using the queries in the profile's `instructions` file. If the user named a project or theme filter in the argument, add it to the query. With tracker `none`, skip this section.

## 4. Report

- **Open todos**: grouped by `area`, one line each, with deadlines prominent.
- **Projects**: one line each, `next:` plus any staleness.
- **In-flight tracker work**: grouped by epic. Cross-reference: if a todo, a project note and an issue cover the same work, say so once rather than three times.
- If a source returns nothing (no todos, or tracker auth fails), say so in one line and continue.

Report findings in chat before writing anything.

## 5. Creating todos

Use the `todo` skill (`~/.claude/skills/todo/SKILL.md`). It owns the script, the frontmatter format and the area vocabulary. Its `--push` commits only the new todo file.

## 6. Sync at the end

Only if you created or changed something:

```bash
~/.claude/skills/status-report/scripts/vault-sync.sh push "vault: add todo <slug>"
```

Report the result line. A sync failure is worth reporting but never blocks the status report.
