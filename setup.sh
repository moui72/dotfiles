#!/usr/bin/env bash
# setup.sh — platform dispatcher. Idempotent: safe to re-run anytime.
#
# From a clone:        ~/dev/dotfiles/setup.sh
# On a virgin machine: curl -fsSL https://raw.githubusercontent.com/moui72/dotfiles/main/setup.sh | bash
#   (piped mode ensures git exists, clones this public repo anonymously
#    over HTTPS, then re-execs the cloned copy of itself)
set -euo pipefail

REPO_URL="https://github.com/moui72/dotfiles"
CLONE_DIR="$HOME/dev/dotfiles"
step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# --- piped mode: BASH_SOURCE is unset when the script arrives on stdin -----
if [[ -z "${BASH_SOURCE[0]:-}" || ! -f "$(dirname "${BASH_SOURCE[0]}")/mac.setup.sh" ]]; then
  step "bootstrap: clone dotfiles repo"
  if ! have git; then
    case "$(uname -s)" in
      Darwin)
        xcode-select --install
        echo "Complete the Command Line Tools dialog, then re-run the curl one-liner."
        exit 1 ;;
      Linux)
        SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo"
        $SUDO apt-get update -qq && $SUDO apt-get install -y -qq git ;;
    esac
  fi
  if [[ ! -d "$CLONE_DIR/.git" ]]; then
    mkdir -p "$(dirname "$CLONE_DIR")"
    git clone "$REPO_URL" "$CLONE_DIR"
  fi
  exec bash "$CLONE_DIR/setup.sh"
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$(uname -s)" in
  Darwin) exec bash "$DIR/mac.setup.sh" ;;
  Linux)
    . /etc/os-release
    if [[ "${ID:-}" == "ubuntu" || "${ID_LIKE:-}" == *ubuntu* || "${ID_LIKE:-}" == *debian* ]]; then
      exec bash "$DIR/ubuntu.setup.sh"
    fi
    echo "unsupported distro: ${ID:-unknown}" >&2; exit 1 ;;
  *) echo "unsupported OS: $(uname -s)" >&2; exit 1 ;;
esac
