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
├── omz/custom/            # PORTABLE zsh snippets, plugins, completions — loaded via
│                          # $ZSH_CUSTOM. Company-specific ones go in ~/.zsh_private
├── git-hooks/             # pre-push / post-merge / post-rewrite
├── ccstatusline/          # status line config
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

Both then run the shared tail (`common.setup.sh`): oh-my-zsh + `ZSH_CUSTOM`
pointed at `omz/custom` (see below) → node LTS via nvm → Claude Code + `claude/install.sh` → Codex →
an auth checklist for the cloud CLIs (`gh`, `gcloud`, `aws`, `railway`,
`flyctl`, `supabase`, `op`, `codex`), which always need a one-time
interactive login per machine.

To keep dependencies in sync later: edit `Brewfile`, then
`brew bundle --file=~/dev/dotfiles/Brewfile`. Audit drift with
`brew bundle check` / `brew bundle cleanup` (dry-run by default).

## oh-my-zsh: `omz/custom` is wired up with `ZSH_CUSTOM`

`omz/custom/` in this repo *is* the live custom directory. `~/.zshrc` points at it:

```bash
export ZSH_CUSTOM="$HOME/dotfiles/omz/custom"   # must be BEFORE `source $ZSH/oh-my-zsh.sh`
```

(Path follows wherever this repo is cloned — `~/dev/dotfiles/omz/custom` if you
used the clone path above.)

`common.setup.sh` sets that line idempotently (replacing omz's commented
placeholder, or inserting above the `source` line), and removes the legacy
directory symlink described below if it finds one. Nothing under
`~/.oh-my-zsh/` is touched, so `omz update` stays clean.

Everything in the directory is picked up, not just top-level snippets:

| Path | Loaded as |
| --- | --- |
| `omz/custom/*.zsh` | sourced on every interactive shell |
| `omz/custom/plugins/<name>/` | custom plugin — enable by adding `<name>` to `plugins=(...)` in `~/.zshrc` |
| `omz/custom/completions/` | added to `$fpath` |

Two of those paths are **gitignored and installed per machine**, because they're
an upstream clone with its own `.git` (which would commit as a broken gitlink):

```bash
git clone https://github.com/1160054/claude-code-zsh-completion \
  "$ZSH_CUSTOM/plugins/claude-code"
```

`~/.zshrc` already lists `claude-code` in `plugins=(...)`, so a machine without
that clone gets a startup warning until you run the command above.
`omz/custom/completions/_claude` is a copy of the same plugin's completion and is
ignored for the same reason — everything *else* under `omz/custom/` is tracked
here and does travel with `git pull`.
| `omz/custom/themes/` | selectable via `ZSH_THEME` |

### Do NOT symlink `~/.oh-my-zsh/custom` to this directory

oh-my-zsh **tracks** files inside its own `custom/` (`example.zsh`,
`plugins/example/`, `themes/example.zsh-theme`). Replacing that directory with a
symlink makes git report those tracked files as deleted, and every update then
fails on the autostash:

```
error: 'custom/example.zsh' is beyond a symbolic link
fatal: Unable to process path custom/example.zsh
Cannot save the current worktree state
fatal: Cannot autostash
There was an error updating. Try again later?
```

Per-file `*.zsh` symlinks into `~/.oh-my-zsh/custom/` avoid that error but
silently drop `plugins/`, `completions/`, and `themes/`. `ZSH_CUSTOM` is the
mechanism omz provides for exactly this, and is the only supported layout here.

If a machine ever ends up with the directory symlink, undo it with:

```bash
rm ~/.oh-my-zsh/custom
git -C ~/.oh-my-zsh checkout -- custom     # restore omz's own tracked files
~/dotfiles/setup.sh                        # re-sets ZSH_CUSTOM
```

### Company/machine-local snippets go in `~/.zsh_private`, not here

Because the loaded directory *is* this public repo, anything dropped in
`omz/custom/` is a candidate for `git push`. **`omz/custom/` is for portable
snippets only** — no org names, GCP project ids, internal hostnames, tokens, or
employer-specific workflow.

Everything else belongs in `~/.zsh_private/`, which `~/.zshrc` sources *after*
oh-my-zsh:

```bash
# Company/Pager-specific customizations — kept out of the portable dotfiles repo.
# (N) qualifier = nullglob, so this doesn't error if the dir is ever empty.
for f in ~/.zsh_private/*.zsh(N); do
  source "$f"
done
```

`common.setup.sh` creates the directory (mode 700) and adds that loop if it's
missing. Why this rather than gitignoring inside `omz/custom/`:

- **It can't leak.** A gitignored file one `git add -f` or one `.gitignore` edit
  away from being committed is a standing risk; a file outside the repo isn't.
- **It loads last, so it wins.** Sourced after `oh-my-zsh.sh`, it can override a
  portable snippet or an omz plugin. That ordering is the point.
- **One home, one copy.** Do NOT keep the same snippet in both places. The
  `~/.zsh_private` copy silently wins, so edits to the `omz/custom/` twin appear
  to do nothing — a genuinely confusing failure. If a snippet is
  employer-specific, it lives in `~/.zsh_private` and nowhere else.

Corollary when debugging: a missing helper is more likely to be in
`~/.zsh_private` than absent. Check there before concluding a function is gone.

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

- **Company / work-specific shell snippets** live in `~/.zsh_private/` (see the
  oh-my-zsh section above), never in `omz/custom/`.

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
  nothing in this repo for it.

## Secrets

No credentials live in this repo. `.gitignore` blocks `**/.env.skill`, `.env`,
`settings.local.json`, and caches. Skills that need credentials ship an
`.env.skill.example` template — copy it to `.env.skill` (gitignored) and fill it in.
Before any `git push`, confirm `git status` shows no `.env.skill` or `.env` files.
