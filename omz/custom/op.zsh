opv() {
  if [[ $# -lt 1 ]]; then
    echo "usage: opv <1password-share-link>" >&2
    return 1
  fi
  command op item get "$1" --fields type=concealed --reveal --format json \
    | jq -r 'if type=="array" then .[0].value else .value end'
}
