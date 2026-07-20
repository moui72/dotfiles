#!/usr/bin/env bash
# ubuntu.setup.sh — Ubuntu/Debian bootstrap. Run via setup.sh (dispatcher); idempotent.
# Mirrors the Brewfile: apt for basics, vendor apt repos / official installers
# for the rest. GUI casks (1Password app, Ghostty, fonts) are mac-only.
set -euo pipefail

DOTFILES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$DOTFILES/common.setup.sh"

SUDO=""
[[ $EUID -ne 0 ]] && SUDO="sudo"
export DEBIAN_FRONTEND=noninteractive

# --- apt basics ------------------------------------------------------------
step "apt packages"
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq \
  build-essential curl ca-certificates gnupg unzip zsh \
  git jq ripgrep fd-find bat fzf zoxide tree wget \
  git-filter-repo rclone podman poppler-utils
# ubuntu names fd/bat differently; give them their real names
mkdir -p "$HOME/.local/bin"
have fd  || ln -sfn "$(command -v fdfind)" "$HOME/.local/bin/fd"
have bat || ln -sfn "$(command -v batcat)" "$HOME/.local/bin/bat"
export PATH="$HOME/.local/bin:$PATH"

# --- vendor apt repos (gh, gcloud, 1password-cli) --------------------------
add_apt_repo() { # name keyring-url repo-line
  local name="$1" key_url="$2" repo_line="$3"
  local keyring="/usr/share/keyrings/${name}.gpg"
  if [[ ! -f "/etc/apt/sources.list.d/${name}.list" ]]; then
    curl -fsSL "$key_url" | $SUDO gpg --dearmor -o "$keyring" --yes
    echo "$repo_line" | $SUDO tee "/etc/apt/sources.list.d/${name}.list" >/dev/null
  fi
}

step "vendor apt repos"
add_apt_repo github-cli \
  https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/github-cli.gpg] https://cli.github.com/packages stable main"
add_apt_repo google-cloud-sdk \
  https://packages.cloud.google.com/apt/doc/apt-key.gpg \
  "deb [signed-by=/usr/share/keyrings/google-cloud-sdk.gpg] https://packages.cloud.google.com/apt cloud-sdk main"
add_apt_repo 1password \
  https://downloads.1password.com/linux/keys/1password.asc \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/1password.gpg] https://downloads.1password.com/linux/debian/$(dpkg --print-architecture) stable main"
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq gh google-cloud-cli 1password-cli

# --- official installers (no good apt story) -------------------------------
step "uv"
have uv || curl -LsSf https://astral.sh/uv/install.sh | sh

step "awscli"
if ! have aws; then
  tmp="$(mktemp -d)"
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o "$tmp/awscli.zip"
  unzip -q "$tmp/awscli.zip" -d "$tmp"
  $SUDO "$tmp/aws/install" --update
  rm -rf "$tmp"
else
  echo "already installed"
fi

step "flyctl"
have flyctl || curl -fsSL https://fly.io/install.sh | sh

step "railway"
have railway || bash <(curl -fsSL https://railway.com/install.sh)

step "supabase"
if ! have supabase; then
  arch="$(dpkg --print-architecture)"
  url="$(curl -fsSL https://api.github.com/repos/supabase/cli/releases/latest \
        | jq -r ".assets[] | select(.name | endswith(\"linux_${arch}.deb\")) | .browser_download_url")"
  curl -fsSL "$url" -o /tmp/supabase.deb
  $SUDO apt-get install -y -qq /tmp/supabase.deb
  rm -f /tmp/supabase.deb
else
  echo "already installed"
fi

step "opentofu"
if ! have tofu; then
  curl -fsSL https://get.opentofu.org/install-opentofu.sh -o /tmp/install-opentofu.sh
  chmod +x /tmp/install-opentofu.sh
  # deb method writes a malformed sources line on noble/arm64; standalone
  # drops the binary in /usr/local/bin instead
  $SUDO /tmp/install-opentofu.sh --install-method standalone --skip-verify
  rm -f /tmp/install-opentofu.sh
else
  echo "already installed"
fi

common_tail
