#!/usr/bin/env bash
# mac.setup.sh — macOS bootstrap. Run via setup.sh (dispatcher); idempotent.
set -euo pipefail

DOTFILES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$DOTFILES/common.setup.sh"

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

# --- podman machine (linux VM; not needed on native linux) -----------------
step "podman machine"
if podman machine inspect >/dev/null 2>&1; then
  echo "machine already exists"
else
  podman machine init
fi

common_tail
