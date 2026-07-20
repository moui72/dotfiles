# dotfiles

Portable personal configuration: machine bootstrap + Claude Code settings + skills.

## Layout

```
dotfiles/
├── README.md
├── .gitignore
├── Brewfile               # macOS dependency list (brew bundle)
├── setup.sh               # platform dispatcher + curl-pipe bootstrap
├── mac.setup.sh           # macOS: Xcode CLT, Homebrew, Brewfile, podman VM
├── ubuntu.setup.sh        # Ubuntu/Debian: apt, vendor repos, installers
├── common.setup.sh        # shared tail: omz, nvm, Claude/Codex, auth checklist
└── claude/
    ├── settings.json          # generic, machine-agnostic Claude Code user settings
    ├── install.sh             # symlinks settings.json + skills into ~/.claude
    └── skills/
        └── assisted-review/   # interactive hunk-by-hunk PR review (you are the reviewer)
```

## Install on a new machine

On a brand-new machine (no git credentials needed — the script ensures git
exists, clones this public repo anonymously over HTTPS, and re-execs its
cloned self):

```bash
curl -fsSL https://raw.githubusercontent.com/moui72/dotfiles/main/setup.sh | bash
```

Or from an existing clone:

```bash
git clone https://github.com/moui72/dotfiles ~/dev/dotfiles
~/dev/dotfiles/setup.sh
```

`setup.sh` detects the platform and dispatches to `mac.setup.sh` (macOS) or
`ubuntu.setup.sh` (Ubuntu/Debian). Both are idempotent (safe to re-run):

- **macOS**: Xcode Command Line Tools → Homebrew → `brew bundle` against the
  `Brewfile` (git, gh, ripgrep, uv, awscli, gcloud, railway, flyctl, supabase,
  opentofu, podman, fzf/fd/zoxide, casks incl. 1Password + Ghostty) →
  `podman machine init`.
- **Ubuntu**: apt basics (incl. `fd`/`bat` symlinked to their real names),
  vendor apt repos (gh, gcloud, 1password-cli), official installers for
  uv/awscli/flyctl/railway/supabase/opentofu. GUI apps and fonts are mac-only.
  Smoke-tested in an `ubuntu:24.04` container.

Both then run the shared tail (`common.setup.sh`): oh-my-zsh + `omz/custom`
symlinks → node LTS via nvm → Claude Code + `claude/install.sh` → Codex →
an auth checklist for the cloud CLIs (`gh`, `gcloud`, `aws`, `railway`,
`flyctl`, `supabase`, `op`, `codex`), which always need a one-time
interactive login per machine.

To keep dependencies in sync later: edit `Brewfile`, then
`brew bundle --file=~/dev/dotfiles/Brewfile`. Audit drift with
`brew bundle check` / `brew bundle cleanup` (dry-run by default).

To install only the Claude Code config:

```bash
~/dev/dotfiles/claude/install.sh      # or: --dry-run to preview
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

## Machine-specific things that ARE in this repo (degrade gracefully elsewhere)

Unlike the section above, these files *are* checked in — they're just tuned to
the source machine's setup. They no-op or fall back harmlessly if that setup
isn't present, so it wasn't worth excluding them, but don't expect them to be
useful as-is on a different setup:

- **Ghostty-specific notification hooks.** `claude/settings.json` sets
  `"preferredNotifChannel": "ghostty"` and the `PermissionRequest`/`Elicitation`
  hooks call `terminal-notifier -activate com.mitchellh.ghostty`. Silent no-op
  in any other terminal.
- **1Password-based commit signing.** `git-hooks/pre-push` and
  `omz/custom/git-signing.zsh` assume SSH commit signing via 1Password. If you
  don't sign commits this way, the hook's unsigned-commit check will just never
  find anything to block.
- **`omz/custom/op.zsh`** wraps the 1Password CLI (`op`); errors harmlessly if
  `op` isn't installed.
- **`omz/custom/gcloud.zsh`** defaults `CLOUDSDK_ROOT_DIR` to
  `~/google-cloud-sdk` (a manual, non-Homebrew install). Override
  `CLOUDSDK_ROOT_DIR` or edit the path if your install lives elsewhere (e.g. a
  Homebrew cask under `/opt/homebrew/Caskroom/...`).
- **nvm** is configured via oh-my-zsh's built-in `nvm` plugin (lazy-loaded, see
  the zstyle config in `~/.zshrc`), not a file in `omz/custom/` — there's
  nothing to symlink for it.

## Secrets

No credentials live in this repo. `.gitignore` blocks `**/.env.skill`, `.env`,
`settings.local.json`, and caches. Skills that need credentials ship an
`.env.skill.example` template — copy it to `.env.skill` (gitignored) and fill it in.
Before any `git push`, confirm `git status` shows no `.env.skill` or `.env` files.
