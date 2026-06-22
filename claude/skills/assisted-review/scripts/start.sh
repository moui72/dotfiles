#!/usr/bin/env bash
# start.sh — single-call startup orchestrator for assisted-review.
#
# Usage:
#   start.sh "<text containing a PR url or owner/repo#N>"
#
# Folds parse-ref → fetch → bat-check → parse-diff → filter-skip → override
# fetches → bot detection → state-file write into one Bash call. Prints a
# JSON status doc on stdout describing what Claude needs to do next:
#
#   { "status": "ok|resume|bat_prompt|invalid_ref|fetch_failed",
#     "env_file": "...",
#     "state_file": "...",
#     "bat_mode": "HIGHLIGHT|PLAIN_SKIPPED|MISSING_PROMPT",
#     "preamble": { ...precomputed values... }
#   }
#
# On resume, the existing state file is preserved and `status=resume` is
# returned with the elapsed time and progress so Claude can show the resume
# prompt. The state file is loaded by Claude via Read for everything else.
#
# Exit codes:
#   0  ok (status field in JSON tells Claude what to do next)
#   1  irrecoverable failure (fetch / gh auth)
#   2  invalid ref

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -lt 1 ]]; then
    echo '{"status":"invalid_ref","message":"usage: start.sh <ref>"}'
    exit 2
fi

REF_INPUT="$*"

# ---------------------------------------------------------------------------
# 1. parse-ref
# ---------------------------------------------------------------------------
ENV_FILE="$("$SCRIPT_DIR/parse-ref.sh" "$REF_INPUT" 2>/tmp/start-parse-err)" || {
    msg="$(cat /tmp/start-parse-err)"
    rm -f /tmp/start-parse-err
    python3 -c "import json,sys; print(json.dumps({'status':'invalid_ref','message':sys.argv[1]}))" "$msg"
    exit 2
}
rm -f /tmp/start-parse-err

# shellcheck disable=SC1090
source "$ENV_FILE"

# ---------------------------------------------------------------------------
# 2. Resume check (silently treat 0-byte or invalid JSON as no-state)
# ---------------------------------------------------------------------------
if [[ -s "$STATE_FILE" ]] && python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$STATE_FILE" 2>/dev/null; then
    python3 - "$ENV_FILE" "$STATE_FILE" <<'PY'
import json, os, sys, time
env_file, state_file = sys.argv[1], sys.argv[2]
state = json.load(open(state_file))
started = state.get("started_at", "")
mtime = os.path.getmtime(state_file)
elapsed_sec = int(time.time() - mtime)
done = sum(1 for c in state["chunks"] if c["status"] != "pending")
total = len(state["chunks"])
print(json.dumps({
    "status": "resume",
    "env_file": env_file,
    "state_file": state_file,
    "started_at": started,
    "elapsed_seconds": elapsed_sec,
    "progress": {"done": done, "total": total},
}))
PY
    exit 0
fi

# ---------------------------------------------------------------------------
# 3. Fetch PR data (5 gh calls in parallel)
# ---------------------------------------------------------------------------
fetch_out=$("$SCRIPT_DIR/fetch.sh" "$ENV_FILE" 2>/tmp/start-fetch-err)
fetch_rc=$?
if [[ $fetch_rc -ne 0 ]]; then
    msg="$(cat /tmp/start-fetch-err)"
    rm -f /tmp/start-fetch-err
    python3 -c "import json,sys; print(json.dumps({'status':'fetch_failed','message':sys.argv[1]}))" "$msg" >&2
    cat /tmp/start-fetch-err 2>/dev/null
    echo "{\"status\":\"fetch_failed\",\"message\":$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$msg")}"
    exit 1
fi
rm -f /tmp/start-fetch-err
# shellcheck disable=SC1090
eval "$fetch_out"

# ---------------------------------------------------------------------------
# 4. bat check
# ---------------------------------------------------------------------------
BAT_MODE=$("$SCRIPT_DIR/bat-check.sh" 2>/dev/null || true)

# ---------------------------------------------------------------------------
# 5. Diff parse + filter + rubric overrides + state build
# ---------------------------------------------------------------------------
HEAD_SHA=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('headRefOid',''))" "$META_FILE")
HEAD_SHORT="${HEAD_SHA:0:8}"

# Try override files (don't fail if missing)
SKIP_FILE_OVERRIDE=$("$SCRIPT_DIR/fetch-repo-file.sh" "$OWNER/$REPO" "$HEAD_SHA" .claude/review-skip.txt 2>/dev/null) || SKIP_FILE_OVERRIDE=""
RUBRIC_FILE_OVERRIDE=$("$SCRIPT_DIR/fetch-repo-file.sh" "$OWNER/$REPO" "$HEAD_SHA" .claude/review-rubric.md 2>/dev/null) || RUBRIC_FILE_OVERRIDE=""

# Parse diff once → file
CHUNKS_FILE="${STATE_FILE%.json}.chunks.json"
"$SCRIPT_DIR/parse-diff.py" "$DIFF_FILE" > "$CHUNKS_FILE" || {
    echo '{"status":"fetch_failed","message":"parse-diff failed"}'
    exit 1
}

# Build state JSON via Python (filter + bot-detect inline). All inputs are
# passed via env to avoid shell-quoting hazards with diff contents.
ME_LOGIN="$(tr -d '\n' < "$ME_FILE")"

export AR_OWNER="$OWNER" AR_REPO="$REPO" AR_NUMBER="$NUMBER" AR_URL="$URL"
export AR_HEAD_SHA="$HEAD_SHA" AR_ME="$ME_LOGIN"
export AR_SKIP_OVERRIDE="$SKIP_FILE_OVERRIDE" AR_RUBRIC_OVERRIDE="$RUBRIC_FILE_OVERRIDE"
export AR_CHUNKS_FILE="$CHUNKS_FILE" AR_META_FILE="$META_FILE"
export AR_COMMENTS_FILE="$COMMENTS_FILE" AR_CHECKS_FILE="$CHECKS_FILE"
export AR_SCRIPT_DIR="$SCRIPT_DIR"

STATE_TMP="${STATE_FILE}.tmp"
python3 - > "$STATE_TMP" <<'PY' || { rm -f "$STATE_TMP"; echo '{"status":"fetch_failed","message":"state build failed"}'; exit 1; }
import json, os, subprocess, sys, datetime

owner = os.environ["AR_OWNER"]
repo = os.environ["AR_REPO"]
number = int(os.environ["AR_NUMBER"])
url = os.environ["AR_URL"]
head_sha = os.environ["AR_HEAD_SHA"]
me = os.environ["AR_ME"]
skip_override = os.environ.get("AR_SKIP_OVERRIDE", "")
rubric_override = os.environ.get("AR_RUBRIC_OVERRIDE", "")

chunks_in = json.load(open(os.environ["AR_CHUNKS_FILE"]))
meta = json.load(open(os.environ["AR_META_FILE"]))
comments = json.load(open(os.environ["AR_COMMENTS_FILE"]))
script_dir = os.environ["AR_SCRIPT_DIR"]

# --- filter generated/vendored ---
def is_skipped(path):
    args = [os.path.join(script_dir, "filter-skip.sh"), path]
    if skip_override:
        args.append(skip_override)
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout.strip() or "skipped"
    return None

skipped_generated = []
kept_chunks = []
file_skip_cache = {}
for c in chunks_in:
    f = c["file"]
    if f not in file_skip_cache:
        file_skip_cache[f] = is_skipped(f)
    reason = file_skip_cache[f]
    if reason:
        skipped_generated.append({"file": f, "reason": reason, "chunk_id": c["id"]})
    else:
        kept_chunks.append(c)

# --- bot detect for existing-comment authors ---
def detect_bot(login):
    if not login:
        return False
    r = subprocess.run([os.path.join(script_dir, "detect-bot.sh"), login],
                       capture_output=True)
    return r.returncode == 0

# Auto-mark anything starting with 🤖 as bot regardless
def looks_like_bot_body(body):
    return bool(body) and body.lstrip().startswith("🤖")

# --- group existing comments into threads, attach to chunks by line ---
threads_by_chunk = {c["id"]: [] for c in kept_chunks}
bot_cache = {}
for cm in comments:
    login = (cm.get("user") or {}).get("login", "")
    if login not in bot_cache:
        bot_cache[login] = detect_bot(login)
    is_bot = bot_cache[login] or looks_like_bot_body(cm.get("body", ""))
    line = cm.get("line") or cm.get("original_line")
    side = cm.get("side") or "RIGHT"
    path = cm.get("path", "")
    cid_target = None
    for c in kept_chunks:
        if c["file"] != path:
            continue
        rng_key = "new_range" if side == "RIGHT" else "old_range"
        if any(m[rng_key][0] <= (line or 0) <= m[rng_key][1] for m in c["members"]):
            cid_target = c["id"]; break
    if cid_target is None:
        continue
    threads_by_chunk[cid_target].append({
        "id": str(cm.get("id")),
        "author": login,
        "is_bot": is_bot,
        "state": "open",  # GH "comments" endpoint returns active comments
        "line": line,
        "side": side,
        "body": cm.get("body", ""),
    })

# --- assemble chunks for state ---
chunks_out = []
queue = []
for c in kept_chunks:
    chunks_out.append({
        "id": c["id"],
        "file": c["file"],
        "hunk_header": c["hunk_header"],
        "old_range": c["old_range"],
        "new_range": c["new_range"],
        "members": c["members"],
        "diff": c["diff"],
        "rating": "low",  # default; Claude can revise via add-note path or rubric pass
        "ai_notes": [],
        "existing_threads": threads_by_chunk[c["id"]],
        "status": "pending",
        "comments": [],
    })
    queue.append(c["id"])

# --- CI tally ---
ci_pass = ci_fail = ci_skip = 0
failing = []
try:
    with open(os.environ["AR_CHECKS_FILE"]) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            status = parts[1].lower()
            name = parts[0]
            if status == "pass":
                ci_pass += 1
            elif status == "fail":
                ci_fail += 1
                failing.append(name)
            else:
                ci_skip += 1
except FileNotFoundError:
    pass

author = (meta.get("author") or {}).get("login", "")
existing_open = sum(len(t) for t in threads_by_chunk.values())
authors_set = sorted({t["author"] for ts in threads_by_chunk.values() for t in ts})

state = {
    "pr": {"owner": owner, "repo": repo, "number": number, "head_sha": head_sha, "url": url},
    "started_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "rubric_source": ("project:.claude/review-rubric.md@" + head_sha[:8]) if rubric_override else "default",
    "preamble": {
        "title": meta.get("title", ""),
        "ai_summary": "",  # Claude fills this in when printing preamble
        "ci": {"passing": ci_pass, "failing": ci_fail, "skipped": ci_skip, "failing_names": failing},
        "is_draft": bool(meta.get("isDraft")),
        "mergeable": (meta.get("mergeable") or "").upper() == "MERGEABLE",
        "self_authored": author == me,
        "author": author,
        "base_ref": meta.get("baseRefName", ""),
        "head_ref": meta.get("headRefName", ""),
        "head_short": head_sha[:8],
        "body_snippet": (meta.get("body") or "")[:600],
        "existing_threads_authors": authors_set,
        "existing_threads_open": existing_open,
    },
    "skipped": {"generated": skipped_generated, "no_risk": []},
    "chunks": chunks_out,
    "cursor": {"phase": "main", "queue": queue},
    "flagged_queue": [],
    "history": [],
    "draft_review": {"verdict": None, "body": None},
}
print(json.dumps(state, indent=2))
PY
mv "$STATE_TMP" "$STATE_FILE"

# ---------------------------------------------------------------------------
# 6. Emit status doc for Claude
# ---------------------------------------------------------------------------
python3 - "$ENV_FILE" "$STATE_FILE" "$BAT_MODE" <<'PY'
import json, sys
env_file, state_file, bat_mode = sys.argv[1], sys.argv[2], sys.argv[3]
s = json.load(open(state_file))
out = {
    "status": "ok",
    "env_file": env_file,
    "state_file": state_file,
    "bat_mode": bat_mode,
    "total_chunks": len(s["chunks"]),
    "skipped_generated_count": len(s["skipped"]["generated"]),
    "preamble": s["preamble"],
    "pr": s["pr"],
    "rubric_source": s["rubric_source"],
    "first_chunk_id": s["cursor"]["queue"][0] if s["cursor"]["queue"] else None,
}
print(json.dumps(out, indent=2))
PY
