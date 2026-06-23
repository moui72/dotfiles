function git_default_branch_name() {
  basename $(git symbolic-ref --short refs/remotes/origin/HEAD)
}

function git_checkout_default_branch() {
  git checkout $(git_default_branch_name) || echo "Failed to checkout default branch, has it change since you cloned the repo? If so, run 'git fetch origin' to update your local branches."
}

function git_rebase_default_branch() {
  git rebase "$@" $(git_default_branch_name) || echo "Failed to checkout default branch, has it change since you cloned the repo? If so, run 'git fetch origin' to update your local branches."
}

function git_update_default_branch() {
  git fetch origin $(git_default_branch_name):$(git_default_branch_name) || echo "Failed to checkout default branch, has it change since you cloned the repo? If so, run 'git fetch origin' to update your local branches."
}

function git_reset_default_branch() {
  git_checkout_default_branch && git reset --hard origin/$(gdb) && git pull && gl || echo "Failed to checkout default branch, has it change since you cloned the repo? If so, run 'git fetch origin' to update your local branches."
}

function git_co_master_path() {
  git checkout master -- $1
}

alias gdb="git_default_branch_name"
alias gcam="git commit -am"
alias gcm="git commit -m"
alias gco="git checkout"
alias gcob="git checkout -b"
alias gcom="git_checkout_default_branch"
alias get="git"
alias gib="git branch"
alias gibc="git branch | cat"
alias gibd="git branch -D"
alias gl="git checkout -"
alias gp="git push"
alias gpl="git pull"
alias gpf="git push --force"
alias gpu='git push --set-upstream origin "$(git branch --show-current)"'
alias grb="git rebase"
alias grbm="git_update_default_branch && git_rebase_default_branch"
alias grm="git_update_default_branch && git_rebase_default_branch"
alias gs="git status"
alias gud="git_update_default_branch"
alias grsm="git_reset_default_branch"
alias update="gud"
alias git_set_head="git remote set-head origin -a"
alias grp="git_co_master_path"
