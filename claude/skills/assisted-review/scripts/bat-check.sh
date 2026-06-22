#!/usr/bin/env bash
set -uo pipefail

MARKER="$HOME/.claude/skills/assisted-review/.bat-skip"

case "${1:-}" in
    --mark-skip)
        mkdir -p "$(dirname "$MARKER")"
        touch "$MARKER"
        exit 0
        ;;
    --install)
        if ! command -v brew >/dev/null 2>&1; then
            echo "brew not found" >&2
            exit 4
        fi
        brew install bat
        exit $?
        ;;
    "")
        if command -v bat >/dev/null 2>&1; then
            echo "HIGHLIGHT"
            exit 0
        fi
        if [ -f "$MARKER" ]; then
            echo "PLAIN_SKIPPED"
            exit 0
        fi
        echo "MISSING_PROMPT"
        exit 2
        ;;
    *)
        echo "unknown arg: $1" >&2
        exit 3
        ;;
esac
