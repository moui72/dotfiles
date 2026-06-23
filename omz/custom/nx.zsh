alias nx="npx nx"

nxlint() {
  if [[ -n "$1" ]]; then
    npx nx run-many -t lint --output-style=static | ansifilter | nxfilter | tee "$1"
  else
    npx nx run-many -t lint --output-style=static | ansifilter | nxfilter
  fi
}
