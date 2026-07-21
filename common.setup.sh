#!/usr/bin/env bash
# common.setup.sh — platform-independent tail of the bootstrap.
# Sourced by mac.setup.sh / ubuntu.setup.sh; expects $DOTFILES to be set.
# Provides step/have helpers and common_tail().

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

common_tail() {
  # --- oh-my-zsh + custom snippets -----------------------------------------
  step "oh-my-zsh"
  if [[ -d "$HOME/.oh-my-zsh" ]]; then
    echo "already installed"
  else
    RUNZSH=no KEEP_ZSHRC=yes sh -c \
      "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
  fi
  if [[ -d "$DOTFILES/omz/custom" ]]; then
    # If custom/ is already a link to the dotfiles dir, per-file links would
    # resolve back onto the sources and overwrite them with self-symlinks.
    if [[ "$(cd "$HOME/.oh-my-zsh/custom" 2>/dev/null && pwd -P)" == "$(cd "$DOTFILES/omz/custom" && pwd -P)" ]]; then
      echo "omz/custom already linked as a directory"
    else
      for f in "$DOTFILES"/omz/custom/*.zsh; do
        ln -sfn "$f" "$HOME/.oh-my-zsh/custom/$(basename "$f")"
      done
      echo "linked omz/custom snippets"
    fi
  fi

  # --- node via nvm --------------------------------------------------------
  step "node (nvm)"
  export NVM_DIR="$HOME/.nvm"
  mkdir -p "$NVM_DIR"
  # brew-installed nvm (mac) or standalone install (ubuntu)
  if have brew && [[ -s "$(brew --prefix nvm 2>/dev/null)/nvm.sh" ]]; then
    # shellcheck disable=SC1091
    . "$(brew --prefix nvm)/nvm.sh"
  elif [[ -s "$NVM_DIR/nvm.sh" ]]; then
    # shellcheck disable=SC1091
    . "$NVM_DIR/nvm.sh"
  else
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash
    # shellcheck disable=SC1091
    [[ -s "$NVM_DIR/nvm.sh" ]] && . "$NVM_DIR/nvm.sh"
  fi
  if have nvm; then
    nvm install --lts --default
    corepack enable 2>/dev/null || true   # pnpm/yarn shims
  else
    echo "nvm not loadable in this shell; run 'nvm install --lts' after restarting"
  fi

  # --- AI coding agents (native installers, not distro-managed) ------------
  step "Claude Code"
  if ! have claude; then
    curl -fsSL https://claude.ai/install.sh | bash
  else
    echo "already installed"
  fi
  if [[ -x "$DOTFILES/claude/install.sh" ]]; then
    "$DOTFILES/claude/install.sh"
  fi

  step "Codex"
  if ! have codex; then
    curl -fsSL https://chatgpt.com/codex/install.sh | sh
  else
    echo "already installed"
  fi

  # --- auth checklist (interactive; can't be made idempotent-silent) -------
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
  have codex && codex login status >/dev/null 2>&1 \
                                        && check_auth codex ok   || check_auth codex   "run: codex login"

  step "done"
  echo "Restart your terminal so shell config takes effect."
}
