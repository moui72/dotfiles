#!/usr/bin/env bash
# filter-skip.sh - decide whether a PR file path should be auto-skipped
# Usage: filter-skip.sh <file-path> [extra-patterns-file]
# Exit 0 + reason on stdout if skip; exit 1 if review; exit 2 on usage error.

set -uo pipefail
shopt -s extglob globstar nocaseglob 2>/dev/null
shopt -u nocaseglob  # we want case-sensitive

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: $0 <file-path> [extra-patterns-file]" >&2
    exit 2
fi

path="$1"
extra="${2:-}"
base="${path##*/}"

# Helper: check if path has a component equal to $1, or starts with "$1/"
has_component() {
    local dir="$1"
    [[ "$path" == "$dir"/* ]] && return 0
    [[ "$path" == */"$dir"/* ]] && return 0
    return 1
}

# Lockfiles
case "$base" in
    package-lock.json|yarn.lock|pnpm-lock.yaml|Cargo.lock|poetry.lock|Gemfile.lock|go.sum)
        echo lockfile; exit 0 ;;
esac
if [[ "$base" == *.lock ]]; then
    echo lockfile; exit 0
fi

# Generated
if [[ "$base" == *.generated.* ]]; then
    echo generated; exit 0
fi

# Protobuf
if [[ "$base" == *_pb.go || "$base" == *_pb2.py ]]; then
    echo protobuf; exit 0
fi

# Build output / vendored
for d in dist build out .next node_modules; do
    if has_component "$d"; then
        echo vendored; exit 0
    fi
done

# Minified
if [[ "$base" == *.min.js || "$base" == *.min.css ]]; then
    echo minified; exit 0
fi

# Sourcemap
if [[ "$base" == *.map ]]; then
    echo sourcemap; exit 0
fi

# Extra patterns
if [[ -n "$extra" && -f "$extra" ]]; then
    while IFS= read -r pattern || [[ -n "$pattern" ]]; do
        # strip leading/trailing whitespace
        pattern="${pattern#"${pattern%%[![:space:]]*}"}"
        pattern="${pattern%"${pattern##*[![:space:]]}"}"
        [[ -z "$pattern" ]] && continue
        [[ "$pattern" == \#* ]] && continue

        if [[ "$pattern" == */* ]]; then
            # path pattern
            # Strip trailing slash for directory-style patterns
            if [[ "$pattern" == */ ]]; then
                dir="${pattern%/}"
                if has_component "$dir"; then
                    echo custom; exit 0
                fi
                continue
            fi
            # shellcheck disable=SC2053
            if [[ "$path" == $pattern ]]; then
                echo custom; exit 0
            fi
            # shellcheck disable=SC2053
            if [[ "$path" == */$pattern ]]; then
                echo custom; exit 0
            fi
        else
            # basename pattern
            # shellcheck disable=SC2053
            if [[ "$base" == $pattern ]]; then
                echo custom; exit 0
            fi
        fi
    done < "$extra"
fi

exit 1
