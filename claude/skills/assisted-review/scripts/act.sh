#!/usr/bin/env bash
# act.sh — per-card / end-of-review driver for assisted-review.
#
# Reads $STATE_FILE (via env file), applies a state mutation, persists, and
# optionally prints the next card as a JSON doc for Claude to render.
#
# Usage:
#   act.sh <env-file> <subcommand> [args...]
#
# Subcommands (state-mutating + emit next card):
#   dismiss <cid>                  mark chunk dismissed, advance
#   flag <cid>                     flag chunk, advance
#   defer <cid>                    move chunk to bottom of queue (action 4)
#   back                           undo last queue op (restore previous chunk)
#   comment <cid> <anchor> <body> [in_reply_to]
#       anchor: "" (whole hunk), "L45", "L20-22", "L-12"
#
# Subcommands (state-mutating only, no card):
#   add-note <cid> <kind> <body> [prompt]
#   set-verdict <APPROVE|COMMENT|REQUEST_CHANGES>
#   set-body <text>
#   edit-comment <cid> <idx> <body>
#
# Subcommands (read-only):
#   next                  print current queue[0] card (no mutation)
#   render <cid>          print a specific chunk's card
#   stats                 print review summary stats
#   drafts                print drafts dump
#   end-of-review         print end-of-review summary + drafts JSON
#
# Submit (wraps submit-review.sh):
#   submit [--dry-run]

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -lt 2 ]]; then
    echo "usage: act.sh <env-file> <subcommand> [args...]" >&2
    exit 2
fi

ENV_FILE="$1"; shift
EMIT_JSON=0
if [[ "${1:-}" == "--json" ]]; then
    EMIT_JSON=1
    shift
fi
SUB="$1"; shift

if [[ ! -f "$ENV_FILE" ]]; then
    echo "act: env file not found: $ENV_FILE" >&2
    exit 2
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

if [[ ! -f "$STATE_FILE" ]]; then
    echo "act: state file not found: $STATE_FILE" >&2
    exit 2
fi

STATE_PY="$SCRIPT_DIR/_state.py"

render_card() {
    # Args: <state_file> <cid>
    # Prints JSON for one chunk card.
    local cid="$1"
    # Determine bat availability for this call
    local bat_mode
    bat_mode=$("$SCRIPT_DIR/bat-check.sh" 2>/dev/null || true)
    python3 - "$STATE_FILE" "$cid" "$bat_mode" <<'PY'
import json, os, subprocess, sys
state_file, cid, bat_mode = sys.argv[1], sys.argv[2], sys.argv[3]
s = json.load(open(state_file))
chunk = next((c for c in s["chunks"] if c["id"] == cid), None)
if chunk is None:
    print(json.dumps({"kind": "error", "message": f"chunk not found: {cid}"}))
    sys.exit(0)

# index is original order (c1=1, c2=2, ...)
try:
    idx = int(cid.lstrip("c"))
except ValueError:
    idx = 0

phase = s["cursor"]["phase"]
queue = s["cursor"]["queue"]
is_last = (len(queue) == 1 and queue[0] == cid)

# Render diff (bat if available + diff longer than ~15 lines)
diff_text = chunk["diff"]
line_count = diff_text.count("\n")
rendered = diff_text
if bat_mode == "HIGHLIGHT" and line_count > 15:
    try:
        r = subprocess.run(
            ["bat", "-l", "diff", "--style=plain", "--paging=never", "--color=always"],
            input=diff_text, capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            rendered = r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

drafted = chunk["comments"][-1] if chunk["comments"] else None

out = {
    "kind": "card",
    "chunk_id": cid,
    "chunk_index": idx,
    "total_chunks": len(s["chunks"]),
    "phase": phase,
    "rating": chunk["rating"],
    "file": chunk["file"],
    "hunk_header": chunk["hunk_header"],
    "members_count": len(chunk["members"]),
    "new_range": chunk["new_range"],
    "old_range": chunk["old_range"],
    "rendered_diff": rendered,
    "diff_line_count": line_count,
    "is_last_in_queue": is_last,
    "existing_threads": chunk["existing_threads"],
    "ai_notes": chunk["ai_notes"],
    "drafted_comment": drafted,
    "queue_remaining": len(queue),
}
print(json.dumps(out, indent=2))
PY
}

emit_next() {
    # If queue empty in main phase but flagged_queue non-empty → promote.
    python3 "$STATE_PY" "$STATE_FILE" promote-flagged 2>/dev/null
    local head
    head=$(python3 -c "import json,sys; s=json.load(open(sys.argv[1])); print(s['cursor']['queue'][0] if s['cursor']['queue'] else '')" "$STATE_FILE")
    if [[ -z "$head" ]]; then
        local phase
        phase=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['cursor']['phase'])" "$STATE_FILE")
        local flagged_count
        flagged_count=$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('flagged_queue',[])))" "$STATE_FILE")
        python3 -c "
import json
print(json.dumps({'kind': 'queue_empty', 'phase': '$phase', 'flagged_count': $flagged_count}, indent=2))
"
        return
    fi
    render_card "$head"
}

# Terminal-ready post-mutation output. Picks the right surface based on
# queue state so a single Bash call per user action is sufficient:
#  - main queue still has chunks → card
#  - main empties + flagged>0     → flagged-banner + card (queue auto-promoted)
#  - both queues empty            → end-of-review + verdict prompt
emit_next_print() {
    local prev_phase
    prev_phase=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['cursor']['phase'])" "$STATE_FILE")
    python3 "$STATE_PY" "$STATE_FILE" promote-flagged 2>/dev/null
    local head new_phase
    head=$(python3 -c "import json,sys; s=json.load(open(sys.argv[1])); print(s['cursor']['queue'][0] if s['cursor']['queue'] else '')" "$STATE_FILE")
    new_phase=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['cursor']['phase'])" "$STATE_FILE")
    if [[ -z "$head" ]]; then
        # Both queues empty → end of review
        python3 "$SCRIPT_DIR/_render.py" "$STATE_FILE" end-of-review
        echo
        python3 "$SCRIPT_DIR/_render.py" "$STATE_FILE" prompt verdict
        return
    fi
    if [[ "$prev_phase" == "main" && "$new_phase" == "flagged" ]]; then
        python3 "$SCRIPT_DIR/_render.py" "$STATE_FILE" prompt flagged-banner
        echo
    fi
    python3 "$SCRIPT_DIR/_render.py" "$STATE_FILE" card "$head"
}

# Pick emit mode based on global --json flag (parsed below).
emit_after_mutation() {
    if [[ "${EMIT_JSON:-0}" == "1" ]]; then
        emit_next
    else
        emit_next_print
    fi
}

case "$SUB" in
    dismiss)
        python3 "$STATE_PY" "$STATE_FILE" dismiss "$1"; emit_after_mutation ;;
    flag)
        python3 "$STATE_PY" "$STATE_FILE" flag "$1"; emit_after_mutation ;;
    defer)
        python3 "$STATE_PY" "$STATE_FILE" defer "$1"; emit_after_mutation ;;
    back)
        python3 "$STATE_PY" "$STATE_FILE" back; emit_after_mutation ;;
    comment)
        cid="$1"; anchor="$2"; body="$3"; reply_to="${4:-}"
        python3 "$STATE_PY" "$STATE_FILE" comment "$cid" "$anchor" "$body" "$reply_to"
        emit_after_mutation ;;
    add-note)
        cid="$1"; kind="$2"; body="$3"; prompt="${4:-}"
        python3 "$STATE_PY" "$STATE_FILE" add-note "$cid" "$kind" "$body" "$prompt" ;;
    set-verdict)
        python3 "$STATE_PY" "$STATE_FILE" set-verdict "$1" ;;
    set-body)
        python3 "$STATE_PY" "$STATE_FILE" set-body "$1" ;;
    set-summary)
        python3 "$STATE_PY" "$STATE_FILE" set-summary "$1" ;;
    edit-comment)
        python3 "$STATE_PY" "$STATE_FILE" edit-comment "$1" "$2" "$3" ;;
    next)
        emit_next ;;
    render)
        render_card "$1" ;;
    print)
        # Terminal-ready UI. Usage: print <surface> [args...]
        python3 "$SCRIPT_DIR/_render.py" "$STATE_FILE" "$@" ;;
    stats)
        python3 "$STATE_PY" "$STATE_FILE" stats ;;
    drafts)
        python3 - "$STATE_FILE" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
drafts = []
for c in s["chunks"]:
    for i, cm in enumerate(c["comments"]):
        drafts.append({
            "chunk_id": c["id"],
            "file": c["file"],
            "side": cm["side"],
            "start_line": cm["start_line"],
            "end_line": cm["end_line"],
            "in_reply_to": cm["in_reply_to"],
            "body": cm["body"],
            "index": i,
        })
# Sort by file then line
drafts.sort(key=lambda d: (d["file"], d["end_line"] or 0))
print(json.dumps(drafts, indent=2))
PY
        ;;
    end-of-review)
        python3 - "$STATE_FILE" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
drafts = []
for c in s["chunks"]:
    for i, cm in enumerate(c["comments"]):
        drafts.append({
            "chunk_id": c["id"], "file": c["file"], "side": cm["side"],
            "start_line": cm["start_line"], "end_line": cm["end_line"],
            "in_reply_to": cm["in_reply_to"], "body": cm["body"], "index": i,
        })
drafts.sort(key=lambda d: (d["file"], d["end_line"] or 0))
total_comments = sum(len(c["comments"]) for c in s["chunks"])
replies = sum(1 for c in s["chunks"] for x in c["comments"] if x.get("in_reply_to"))
drafted_chunks = sum(1 for c in s["chunks"] if c["comments"])
flagged = len(s.get("flagged_queue", []))
out = {
    "kind": "end_of_review",
    "stats": {
        "reviewed": len(s["chunks"]),
        "drafted": total_comments,
        "drafted_chunks": drafted_chunks,
        "replies": replies,
        "flagged_resolved": flagged,
    },
    "drafts": drafts,
    "self_authored": s["preamble"].get("self_authored", False),
}
print(json.dumps(out, indent=2))
PY
        ;;
    submit)
        # Optional --dry-run flag
        if [[ "${1:-}" == "--dry-run" ]]; then
            "$SCRIPT_DIR/submit-review.sh" "$ENV_FILE" --dry-run
        else
            "$SCRIPT_DIR/submit-review.sh" "$ENV_FILE"
        fi
        ;;
    *)
        echo "act: unknown subcommand: $SUB" >&2
        exit 2 ;;
esac
