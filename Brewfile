# Brewfile — single source of truth for machine dependencies.
# Apply with:  brew bundle --file=~/dev/dotfiles/Brewfile
# Audit drift: brew bundle check / brew bundle cleanup (dry-run by default)

tap "hashicorp/tap"
tap "supabase/tap"

# --- core cli ---
brew "git"
brew "gh"                 # GitHub CLI
brew "ripgrep"
brew "jq"
brew "bat"
brew "uv"                 # python toolchain (also manages pythons)
brew "nvm"                # node versions (used via oh-my-zsh nvm plugin)

# --- cloud / deploy ---
brew "awscli"
brew "flyctl"
brew "railway"
brew "supabase/tap/supabase"
brew "opentofu"
brew "hashicorp/tap/terraform"

# --- containers ---
brew "podman"

# --- misc utilities already in use ---
brew "git-filter-repo"
brew "rclone"
brew "terminal-notifier"  # Claude Code notification hooks
brew "poppler"
brew "lilypond"

# --- opinionated additions (fast modern basics) ---
brew "fd"                 # find, but sane and fast (pairs with rg)
brew "fzf"                # fuzzy finder — ctrl-r history search alone is worth it
brew "zoxide"             # smarter cd (z <dir>)
brew "tree"
brew "wget"

# --- casks ---
cask "gcloud-cli"
cask "1password"
cask "1password-cli"      # `op` — commit signing + secret injection
cask "ghostty"            # your terminal
cask "font-jetbrains-mono-nerd-font"  # icons for statuslines/prompts
