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
  # omz TRACKS files under its own custom/ (example.zsh, plugins/example,
  # themes/example), so symlinking that directory to the dotfiles copy makes git
  # report them deleted and every `omz update` dies with
  #   error: 'custom/example.zsh' is beyond a symbolic link ... Cannot autostash
  # ZSH_CUSTOM is the supported way to relocate the directory: omz's checkout
  # stays pristine, and subdirs (plugins/, completions/, themes/) come along too,
  # which per-file *.zsh symlinks never covered.
  zshrc="$HOME/.zshrc"
  if [[ -d "$DOTFILES/omz/custom" ]]; then
    want="export ZSH_CUSTOM=\"\$HOME/${DOTFILES#$HOME/}/omz/custom\""
    # Undo the old whole-directory symlink, if this machine still has one.
    if [[ -L "$HOME/.oh-my-zsh/custom" ]]; then
      rm "$HOME/.oh-my-zsh/custom"
      git -C "$HOME/.oh-my-zsh" checkout -- custom 2>/dev/null || mkdir -p "$HOME/.oh-my-zsh/custom"
      echo "removed legacy custom/ directory symlink"
    fi
    if [[ ! -f "$zshrc" ]]; then
      echo "no ~/.zshrc yet; add before 'source \$ZSH/oh-my-zsh.sh':  $want"
    elif grep -qE '^[[:space:]]*(export[[:space:]]+)?ZSH_CUSTOM=' "$zshrc"; then
      echo "ZSH_CUSTOM already set in ~/.zshrc: $(grep -m1 -E '^[[:space:]]*(export[[:space:]]+)?ZSH_CUSTOM=' "$zshrc")"
    elif grep -qE '^[[:space:]]*#[[:space:]]*ZSH_CUSTOM=' "$zshrc"; then
      # omz's own template ships this placeholder above the source line.
      WANT="$want" perl -i -pe '$done ||= s{^\s*#\s*ZSH_CUSTOM=.*}{$ENV{WANT}} unless $done' "$zshrc"
      echo "set ZSH_CUSTOM in ~/.zshrc (replaced omz placeholder)"
    elif grep -q 'source \$ZSH/oh-my-zsh.sh' "$zshrc"; then
      # Must land BEFORE omz is sourced, so insert rather than append.
      WANT="$want" perl -i -pe 'print "$ENV{WANT}\n" if m{^source \$ZSH/oh-my-zsh\.sh} && !$done++' "$zshrc"
      echo "set ZSH_CUSTOM in ~/.zshrc (inserted above omz source line)"
    else
      echo "WARNING: could not place ZSH_CUSTOM in ~/.zshrc; add manually: $want"
    fi
  fi

  # --- ~/.zsh_private: company/machine-local snippets ----------------------
  # Sourced AFTER oh-my-zsh so it can override portable snippets and plugins.
  # Kept outside this public repo so employer-specific config cannot leak.
  step "~/.zsh_private"
  mkdir -p "$HOME/.zsh_private"
  chmod 700 "$HOME/.zsh_private"
  if [[ ! -f "$zshrc" ]]; then
    echo "no ~/.zshrc yet; add a loop sourcing ~/.zsh_private/*.zsh after oh-my-zsh"
  elif grep -q '\.zsh_private' "$zshrc"; then
    echo "already sourced from ~/.zshrc"
  elif grep -q 'source \$ZSH/oh-my-zsh.sh' "$zshrc"; then
    # Appended AFTER the omz source line, so these snippets can override it.
    perl -i -pe '$_ .= qq{\n# Company-specific customizations - kept out of the portable dotfiles repo.\n# (N) qualifier = nullglob, so this does not error if the dir is ever empty.\nfor f in ~/.zsh_private/*.zsh(N); do\n  source "\$f"\ndone\n} if m{^source \$ZSH/oh-my-zsh\.sh} && !$done++' "$zshrc"
    echo "added ~/.zsh_private source loop to ~/.zshrc"
  else
    echo "WARNING: could not add the ~/.zsh_private loop to ~/.zshrc; add it manually"
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
