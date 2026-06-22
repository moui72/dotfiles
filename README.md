# dotfiles

Portable personal configuration. Currently: Claude Code settings + skills.

## Layout

```
dotfiles/
├── README.md
├── .gitignore
└── claude/
    ├── settings.json          # generic, machine-agnostic Claude Code user settings
    ├── install.sh             # symlinks settings.json + skills into ~/.claude
    └── skills/
        └── assisted-review/   # interactive hunk-by-hunk PR review (you are the reviewer)
```

## Install on a new machine

```bash
git clone <your-repo-url> ~/dotfiles
~/dotfiles/claude/install.sh          # or: --dry-run to preview
```

`install.sh` is idempotent and **symlinks** (does not copy):

- `claude/settings.json` → `~/.claude/settings.json`
- each `claude/skills/<name>` → `~/.claude/skills/<name>`

The repo is the single source of truth — editing a linked file edits the repo, so
`git pull` on another machine keeps everything in sync. Skills are linked
individually, so any other skills already in `~/.claude/skills` are left alone.
Real files already at a target are backed up to `<target>.bak-<timestamp>` before
being replaced; correct symlinks are left untouched.

> **Verify the symlink survives a settings write.** Claude Code rewrites
> `~/.claude/settings.json` when you toggle settings it owns (e.g. `/fast`,
> effort level, thinking). If that write replaces the file atomically it would
> clobber the symlink with a regular file, silently breaking live-sync. After
> installing, toggle one setting in Claude, then run `ls -l ~/.claude/settings.json`:
> still a symlink → you're set. Became a regular file → re-run `install.sh` to
> relink (you'll lose any in-app changes to that file; make settings edits in the
> repo instead). Also confirm the skill loaded with `/skills`.

## Prerequisites

`install.sh` warns (never fails) if these are missing:

| Tool | Needed for |
| --- | --- |
| `gh` (GitHub CLI, authenticated) | assisted-review skill |
| `jq` | assisted-review scripts |
| `bat` | diff rendering in assisted-review |
| `node` + `npx` | status line (`ccstatusline`) |
| `python3` | assisted-review helper scripts |
| `terminal-notifier` | **optional** — macOS notification hooks; no-op without it |

## Machine- and account-specific things NOT in this repo (by design)

These are intentionally excluded so the config is portable and safe to publish.
Set them up per machine as needed:

- **`ANTHROPIC_BASE_URL` (local API proxy).** The source machine ran a local proxy
  (`http://127.0.0.1:9801`). That is machine-specific — bundling it would break
  Claude Code anywhere the proxy isn't running. Claude Code has **no user-level
  `settings.local.json`** (the `.local` override is project-scoped only), so if a
  machine needs a proxy, export it from your shell rc instead:
  ```bash
  export ANTHROPIC_BASE_URL=http://127.0.0.1:9801   # only where the proxy runs
  ```

- **Project-scoped Edit/Write permissions.** The source config allowed writes under
  a specific work tree (`~/pager/**`). That's left out of the generic settings.
  Add per-project write permissions in that project's `.claude/settings.local.json`,
  or re-add a home-relative rule to `~/.claude/settings.json` after install.

- **Plugins.** `settings.json` enables `frontend-design@claude-plugins-official`.
  The plugin itself isn't vendored here — add the marketplace once per machine:
  ```
  /plugin marketplace add claude-plugins-official
  ```

- **Company / work-specific skills and their secrets** (Jira/Confluence, Qase,
  database proxies, etc.) are deliberately **not** in this repo. They depend on
  org URLs, credentials, and shell helpers that don't belong in a portable personal
  bundle. Keep those in `~/.claude/skills` directly on the machines that need them.

## Secrets

No credentials live in this repo. `.gitignore` blocks `**/.env.skill`, `.env`,
`settings.local.json`, and caches. Skills that need credentials ship an
`.env.skill.example` template — copy it to `.env.skill` (gitignored) and fill it in.
Before any `git push`, confirm `git status` shows no `.env.skill` or `.env` files.
