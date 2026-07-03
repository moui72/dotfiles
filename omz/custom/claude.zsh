alias ccp="CLAUDE_CONFIG_DIR=~/.claude-personal claude"

claude-wt() {
  local name="${1:-$(date +%s)}"
  local branch="wt/$name"
  local source_dir="$PWD"
  local dir=".worktrees/$name"

  git worktree add -b "$branch" "$dir" || return 1
  cd "$dir" || return 1

  [[ -f package.json && -d "$source_dir/node_modules" ]] && ln -s "$source_dir/node_modules" node_modules
  [[ -f composer.json && -d "$source_dir/vendor" ]] && ln -s "$source_dir/vendor" vendor
  [[ ( -f requirements.txt || -f pyproject.toml ) && -d "$source_dir/.venv" ]] && ln -s "$source_dir/.venv" .venv
  [[ -f Gemfile && -d "$source_dir/vendor/bundle" ]] && { mkdir -p vendor; ln -s "$source_dir/vendor/bundle" vendor/bundle; }

  claude
}
