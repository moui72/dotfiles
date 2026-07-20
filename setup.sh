#!/usr/bin/env bash
# setup.sh — bootstrap a brand-new Mac. Idempotent: safe to re-run anytime.
#
#   git clone <repo-url> ~/dev/dotfiles && ~/dev/dotfiles/setup.sh
#
# Order matters only at the top (Xcode CLT -> Homebrew -> everything else).
set -euo pipefail

DOTFILES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# --- Xcode Command Line Tools (compilers, git bootstrap) -------------------
step "Xcode Command Line Tools"
if xcode-select -p >/dev/null 2>&1; then
  echo "already installed"
else
  xcode-select --install
  echo "Complete the CLT installer dialog, then re-run this script."
  exit 1
fi

# --- Homebrew --------------------------------------------------------------
step "Homebrew"
if ! have brew; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
# Apple Silicon shell setup (no-op if already present)
if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
  grep -q 'brew shellenv' ~/.zprofile 2>/dev/null || \
    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
fi

# --- Everything declared in the Brewfile -----------------------------------
step "brew bundle"
brew bundle --file="$DOTFILES/Brewfile"

# --- oh-my-zsh + custom snippets -------------------------------------------
step "oh-my-zsh"
if [[ -d "$HOME/.oh-my-zsh" ]]; then
  echo "already installed"
else
  RUNZSH=no KEEP_ZSHRC=yes sh -c \
    "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
fi
if [[ -d "$DOTFILES/omz/custom" ]]; then
  for f in "$DOTFILES"/omz/custom/*.zsh; do
    ln -sfn "$f" "$HOME/.oh-my-zsh/custom/$(basename "$f")"
  done
  echo "linked omz/custom snippets"
fi

# --- node via nvm ----------------------------------------------------------
step "node (nvm)"
export NVM_DIR="$HOME/.nvm"
mkdir -p "$NVM_DIR"
# shellcheck disable=SC1091
[[ -s "$(brew --prefix nvm)/nvm.sh" ]] && . "$(brew --prefix nvm)/nvm.sh"
if have nvm; then
  nvm install --lts --default
  corepack enable 2>/dev/null || true   # pnpm/yarn shims
else
  echo "nvm not loadable in this shell; run 'nvm install --lts' after restarting"
fi

# --- podman machine --------------------------------------------------------
step "podman machine"
if podman machine inspect >/dev/null 2>&1; then
  echo "machine already exists"
else
  podman machine init
fi

# --- Claude Code -----------------------------------------------------------
step "Claude Code"
if ! have claude; then
  curl -fsSL https://claude.ai/install.sh | bash
else
  echo "already installed"
fi
if [[ -x "$DOTFILES/claude/install.sh" ]]; then
  "$DOTFILES/claude/install.sh"
fi

# --- auth checklist (interactive; can't be made idempotent-silent) ---------
step "auth status"
check_auth() { printf '%-12s %s\n' "$1:" "$2"; }
gh auth status >/dev/null 2>&1        && check_auth gh ok      || check_auth gh      "run: gh auth login"
gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | grep -q . \
                                      && check_auth gcloud ok  || check_auth gcloud  "run: gcloud auth login"
aws sts get-caller-identity >/dev/null 2>&1 \
                                      && check_auth aws ok     || check_auth aws     "run: aws configure sso (or aws configure)"
railway whoami >/dev/null 2>&1        && check_auth railway ok || check_auth railway "run: railway login"
flyctl auth whoami >/dev/null 2>&1    && check_auth fly ok     || check_auth fly     "run: flyctl auth login"
supabase projects list >/dev/null 2>&1 && check_auth supabase ok || check_auth supabase "run: supabase login"
op whoami >/dev/null 2>&1             && check_auth op ok      || check_auth op      "run: op signin (enable 1Password CLI integration in app)"

step "done"
echo "Restart your terminal so shell config takes effect."
