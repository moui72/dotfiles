#!/bin/zsh

function git_repush() {
  current_sha=$(git rev-parse HEAD)
  git reset --hard HEAD^
  git push --force --no-verify
  git reset --hard $current_sha
  git push --no-verify
}
