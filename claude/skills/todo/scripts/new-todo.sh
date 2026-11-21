#!/usr/bin/env bash
# Create a todo note in the Obsidian vault with the frontmatter Todos.base reads.
#
# usage: new-todo.sh --title "..." [--area AREA] [--issue KEY-123|URL] [--due YYYY-MM-DD]
#                    [--slug name] [--body-file FILE | --body -] [--push] [--dry-run]
#        new-todo.sh --list-areas
#
#   --body -     read the body markdown from stdin
#   --push       git-commit ONLY the new file and push (rebase + retry once if rejected)
#   --dry-run    print the note to stdout; write nothing
#   --issue      a tracker key (needs the profile's issue_url) or any URL; --jira is an alias
# Vault, issue_url and issue_field come from the per-machine profile (project skill's skill_profile.py).
# Prints the created file path (or the note, with --dry-run). Exit 1 on validation errors.
set -euo pipefail

PROFILE_PY="$HOME/.claude/skills/project/scripts/skill_profile.py"
prof() { [[ -f "$PROFILE_PY" ]] && python3 "$PROFILE_PY" get "$1" 2>/dev/null || true; }
VAULT="${OBSIDIAN_VAULT:-$(prof vault_dir)}"; VAULT="${VAULT:-$HOME/Documents}"
TODO="$VAULT/todo"
BASE="$VAULT/Todos.base"
ISSUE_URL="$(prof issue_url)"
ISSUE_FIELD="$(prof issue_field)"; ISSUE_FIELD="${ISSUE_FIELD:-issue}"

die() { echo "new-todo: $*" >&2; exit 1; }

# Areas that have a per-area view in Todos.base (area == "x" filters).
base_areas() { grep -oE 'area == "[^"]+"' "$BASE" 2>/dev/null | sed -E 's/area == "(.*)"/\1/' | sort -u; }

title=""; area=""; issue=""; due=""; slug=""; body_src=""; push=0; dry=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --title) title="${2-}"; shift 2;;
    --area)  area="${2-}";  shift 2;;
    --issue|--jira) issue="${2-}"; shift 2;;
    --due)   due="${2-}";   shift 2;;
    --slug)  slug="${2-}";  shift 2;;
    --body-file) body_src="${2-}"; shift 2;;
    --body)  body_src="${2-}"; shift 2;;
    --push)  push=1; shift;;
    --dry-run) dry=1; shift;;
    --list-areas) base_areas; exit 0;;
    -h|--help) sed -n '2,14p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

[[ -d "$TODO" ]] || die "todo folder not found: $TODO"
title="$(printf '%s' "$title" | tr '\n' ' ' | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
[[ -n "$title" ]] || die "--title is required"

# --issue: a URL is stored as given, except a Jira-style browse URL, which is canonicalised like a
# bare key; a bare key becomes the profile's issue_url with {key} filled in
if [[ -n "$issue" ]]; then
  if [[ "$issue" =~ ^https?:// && ! "$issue" =~ /browse/ ]]; then :
  else
    key="$(sed -E 's#^.*/browse/##; s#[/?].*$##' <<<"$issue" | tr '[:lower:]' '[:upper:]')"
    [[ "$key" =~ ^[A-Z][A-Z0-9]+-[0-9]+$ ]] || die "--issue must be a key like ABC-123 or a URL (got '$issue')"
    if [[ -n "$ISSUE_URL" ]]; then issue="${ISSUE_URL//\{key\}/$key}"
    elif [[ "$issue" =~ ^https?:// ]]; then :
    else die "--issue $key: no issue_url in this machine's profile; pass a full URL"
    fi
  fi
fi

# --due: real calendar date in ISO form
if [[ -n "$due" ]]; then
  [[ "$due" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || die "--due must be YYYY-MM-DD (got '$due')"
  if date -j -f %Y-%m-%d "$due" +%F >/dev/null 2>&1; then
    [[ "$(date -j -f %Y-%m-%d "$due" +%F)" == "$due" ]] || die "--due is not a real date: $due"
  else
    date -d "$due" +%F >/dev/null 2>&1 || die "--due is not a real date: $due"
  fi
fi

# --area: closed vocabulary = the per-area views in Todos.base
if [[ -n "$area" ]] && ! base_areas | grep -qxF "$area"; then
  echo "new-todo: WARNING area '$area' has no view in Todos.base (known: $(base_areas | tr '\n' ' '))." >&2
  echo "new-todo:         It will show in Active only, until a view is added." >&2
fi

# slug: lowercase ascii, runs of non-alnum -> '-', trimmed, <= 60 chars (portable: no sed '\+')
[[ -n "$slug" ]] || slug="$title"
slug="$(printf '%s' "$slug" | perl -CS -MUnicode::Normalize -pe '$_ = NFD($_); s/\pM//g')"  # é -> e
slug="$(printf '%s' "$slug" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed -E 's/^-+//; s/-+$//' | cut -c1-60 | sed -E 's/-+$//')"
[[ -n "$slug" ]] || die "could not derive a slug from the title; pass --slug"
f="$TODO/$slug.md"
[[ ! -e "$f" && ! -e "$TODO/completed/$slug.md" ]] || die "refusing to overwrite existing todo: $slug.md"

# body: file or stdin; drop a leading H1 (the script writes the title heading itself)
body=""
if [[ "$body_src" == "-" ]]; then body="$(cat)"
elif [[ -n "$body_src" ]]; then [[ -f "$body_src" ]] || die "body file not found: $body_src"; body="$(cat "$body_src")"
fi
body="$(printf '%s\n' "$body" | awk 'BEGIN{s=1} s && /^[[:space:]]*$/ {next} s && /^# / {s=0; drop=1; next} {s=0; if (drop && /^[[:space:]]*$/ && !seen) {next} seen=1; print}')"

esc=${title//\\/\\\\}; esc=${esc//\"/\\\"}
note="$(
  echo "---"
  echo "done: false"
  echo "title: \"$esc\""
  [[ -n "$issue" ]] && echo "$ISSUE_FIELD: $issue"
  echo "area: ${area}"
  echo "due: ${due}"
  echo "---"
  echo "# $title"
  if [[ -n "$body" ]]; then echo; printf '%s\n' "$body"; fi
)"

if [[ $dry -eq 1 ]]; then echo "new-todo: would write $f" >&2; printf '%s\n' "$note"; exit 0; fi
printf '%s\n' "$note" > "$f"
echo "$f"

if [[ $push -eq 1 ]]; then
  cd "$VAULT"
  rel="todo/$slug.md"
  git add -- "$rel" && git commit -q -m "todo: add $slug" -- "$rel" || die "commit failed; $rel is written but uncommitted"
  echo "new-todo: committed $rel"
  branch="$(git branch --show-current)"
  if git push -q origin "$branch" 2>/dev/null; then echo "new-todo: pushed"
  elif git pull --rebase --autostash -q origin "$branch" && git push -q origin "$branch"; then echo "new-todo: pushed after rebase"
  else echo "new-todo: PUSH FAILED — commit is local; resolve in $VAULT" >&2
  fi
fi
