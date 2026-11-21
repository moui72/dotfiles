---
name: todo
description: Create a todo in the user's notes vault (<vault_dir>/todo/) in the exact frontmatter format the Todos.base views read. Use whenever the user asks to write, add, capture, create, or file a todo / to-do / follow-up / reminder-for-later, or when finished work leaves something the user should execute later. Not for reading or reporting on todos — that's status-report.
allowed-tools: [Bash, Write]
---

# todo — write a vault todo

Todos are markdown notes in `<vault_dir>/todo/`. Obsidian's `Todos.base` renders them as views. The script owns the file format: never hand-write a todo file or edit its frontmatter.

`vault_dir`, `issue_url` and `issue_field` come from this machine's profile (see the `project` skill; `project profile` prints them). `$OBSIDIAN_VAULT` overrides `vault_dir`. With no profile, the vault is `~/Documents`.

## Write one

```bash
~/.claude/skills/todo/scripts/new-todo.sh \
  --title "Re-scope ABC-123 after the API change" \
  [--area AREA] [--issue ABC-123] [--due 2026-09-30] \
  [--body-file /path/to/body.md | --body -] \
  --push
```

- **`--title`** (required): short and imperative. It becomes the `title:` field, the H1, and the filename slug (lowercase ASCII, hyphens, ≤ 60 chars).
- **`--area`**: closed vocabulary. It must match a per-area view in `Todos.base`. Run `new-todo.sh --list-areas` to see the current set.
  - Pick the closest existing area, or leave it empty.
  - If the script warns that an area is new, tell the user it will show only in the Active view until they add a view.
- **`--issue`** (alias `--jira`): a bare tracker key (`ABC-123`) or a URL.
  - A bare key becomes the profile's `issue_url` with the key filled in. A Jira browse URL is canonicalised the same way, and any other URL is stored as given.
  - The link goes in the frontmatter field named by `issue_field` (default `issue`).
  - Include it whenever the work maps to a tracker issue.
- **`--due`**: `YYYY-MM-DD`. Only set it when the user gives, or clearly implies, a date. Convert relative dates to absolute ones.
- **Body**: pass markdown through `--body -` (stdin heredoc) or `--body-file` (write it to the scratchpad first).
  - Don't start the body with an H1; the script writes it and strips a duplicate one.
  - A good body covers why it matters, links to the source (`[[note]]` wikilinks for vault notes, URLs for issues and PRs), and `- [ ]` steps when there is more than one.
- **`--push`**: commits **only the new file** and pushes, with one rebase-and-retry if the push is rejected. Use it by default. Other uncommitted vault edits are left alone.
  - Don't use `status-report/scripts/vault-sync.sh push` for this: it runs `git add -A`, which would commit the user's unrelated edits.
- **`--dry-run`**: prints the note and its target path, and writes nothing. Use it when the user wants to see the todo first.

The script refuses to overwrite an existing slug, including one in `todo/completed/`. It exits non-zero on a bad `--issue` or `--due`, or on a bare key when the profile has no `issue_url`. If it refuses a slug, choose a more specific `--slug`. Don't delete the existing file.

## Rules

- **Never mark a todo done**, and never set `done: true`. Completing it is the user's click in Obsidian.
- **Don't restructure existing todos.** Appending notes to an open todo's body is fine when asked, but leave the frontmatter alone.
- **Finish with the path** (`todo/<slug>.md`) and the push result in one line. When a todo comes out of a longer task, also say in one line what it captures.
