"""Shared state-file helpers for the assisted-review skill.

This module is imported by start.sh and act.sh (both call `python3 -m _state ...`
or `python3 _state.py ...`). All read/write of the state JSON goes through here
so the script surface stays small and predictable for permission allowlisting.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# State I/O
# ---------------------------------------------------------------------------

def load(path: str) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def save(path: str, state: dict[str, Any]) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def find_chunk(state: dict[str, Any], cid: str) -> dict[str, Any]:
    for c in state["chunks"]:
        if c["id"] == cid:
            return c
    raise SystemExit(f"_state: chunk not found: {cid}")


# ---------------------------------------------------------------------------
# Line-anchor parsing for action `3`
# ---------------------------------------------------------------------------

_LINE_RE = re.compile(r"^L(-?)(\d+)(?:-(\d+))?$")


def parse_anchor(spec: str | None, chunk: dict[str, Any]) -> tuple[str, int | None, int]:
    """Parse a comment anchor like 'L45', 'L20-22', 'L-12', or '' / None.

    Returns (side, start_line_or_None, end_line). Defaults: whole-hunk →
    side RIGHT, end_line = last new-file line, start_line None.
    """
    if not spec:
        new_end = chunk["new_range"][1]
        return ("RIGHT", None, new_end)
    m = _LINE_RE.match(spec.strip())
    if not m:
        raise SystemExit(f"bad anchor: {spec!r} (expected L<n>, L<a>-<b>, L-<n>, L-<a>-<b>)")
    side = "LEFT" if m.group(1) == "-" else "RIGHT"
    a = int(m.group(2))
    b = int(m.group(3)) if m.group(3) else a
    start, end = (a, b) if a <= b else (b, a)
    # Validate against members[]
    rng_key = "old_range" if side == "LEFT" else "new_range"
    if not any(m[rng_key][0] <= start and end <= m[rng_key][1] for m in chunk["members"]):
        raise SystemExit(f"line {start}-{end} not in any member range of {chunk['id']} ({side})")
    if start == end:
        return (side, None, end)
    return (side, start, end)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def action_dismiss(state: dict[str, Any], cid: str) -> None:
    c = find_chunk(state, cid)
    c["status"] = "dismissed"
    q = state["cursor"]["queue"]
    state["cursor"]["queue"] = [x for x in q if x != cid]
    _push_history(state, "dismiss", cid)


def action_flag(state: dict[str, Any], cid: str) -> None:
    c = find_chunk(state, cid)
    c["status"] = "flagged"
    q = state["cursor"]["queue"]
    state["cursor"]["queue"] = [x for x in q if x != cid]
    state.setdefault("flagged_queue", []).append(cid)
    _push_history(state, "flag", cid)


def action_defer(state: dict[str, Any], cid: str) -> None:
    """Move chunk to bottom of current queue (action 4 — ask AI)."""
    q = state["cursor"]["queue"]
    if cid in q:
        q.remove(cid)
        q.append(cid)
    _push_history(state, "defer", cid)


def action_back(state: dict[str, Any]) -> str | None:
    """Undo the most recent dismiss/flag/comment, restoring to queue front."""
    hist = state.get("history", [])
    if not hist:
        return None
    last = hist.pop()
    op = last["op"]
    cid = last["cid"]
    c = find_chunk(state, cid)
    if op in ("dismiss", "comment", "reply"):
        c["status"] = "pending"
        if cid not in state["cursor"]["queue"]:
            state["cursor"]["queue"].insert(0, cid)
    elif op == "flag":
        # Leave on flagged queue; just surface to user via return value
        pass
    elif op == "defer":
        q = state["cursor"]["queue"]
        if cid in q:
            q.remove(cid)
            q.insert(0, cid)
    return op


def action_comment(state: dict[str, Any], cid: str, anchor: str | None, body: str,
                   in_reply_to: str | None = None) -> None:
    c = find_chunk(state, cid)
    side, start, end = parse_anchor(anchor, c)
    c["comments"].append({
        "side": side,
        "start_line": start,
        "end_line": end,
        "body": body,
        "in_reply_to": in_reply_to,
    })
    c["status"] = "dismissed"
    q = state["cursor"]["queue"]
    state["cursor"]["queue"] = [x for x in q if x != cid]
    _push_history(state, "reply" if in_reply_to else "comment", cid)


def action_add_note(state: dict[str, Any], cid: str, kind: str, body: str,
                    prompt: str | None = None) -> None:
    c = find_chunk(state, cid)
    note = {"kind": kind, "body": body}
    if prompt is not None:
        note["prompt"] = prompt
    # For 'initial', dedupe: only one initial note per chunk
    if kind == "initial" and any(n.get("kind") == "initial" for n in c["ai_notes"]):
        return
    c["ai_notes"].append(note)


def action_set_verdict(state: dict[str, Any], verdict: str) -> None:
    if verdict not in ("APPROVE", "COMMENT", "REQUEST_CHANGES"):
        raise SystemExit(f"bad verdict: {verdict}")
    state["draft_review"]["verdict"] = verdict


def action_set_body(state: dict[str, Any], body: str) -> None:
    state["draft_review"]["body"] = body


def action_set_summary(state: dict[str, Any], summary: str) -> None:
    state["preamble"]["ai_summary"] = summary


def action_edit_comment(state: dict[str, Any], cid: str, idx: int, body: str) -> None:
    c = find_chunk(state, cid)
    c["comments"][idx]["body"] = body


def _push_history(state: dict[str, Any], op: str, cid: str) -> None:
    state.setdefault("history", []).append({"op": op, "cid": cid, "t": int(time.time())})


# ---------------------------------------------------------------------------
# Promotion to flagged-queue pass
# ---------------------------------------------------------------------------

def promote_to_flagged_phase(state: dict[str, Any]) -> bool:
    """If main queue empty and flagged_queue non-empty, switch phases.

    Returns True iff a transition happened.
    """
    if state["cursor"].get("phase") == "flagged":
        return False
    if state["cursor"]["queue"]:
        return False
    fq = state.get("flagged_queue", [])
    if not fq:
        return False
    state["cursor"]["phase"] = "flagged"
    state["cursor"]["queue"] = list(fq)
    return True


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def stats(state: dict[str, Any]) -> dict[str, Any]:
    drafts = sum(len(c["comments"]) for c in state["chunks"])
    replies = sum(1 for c in state["chunks"] for x in c["comments"] if x.get("in_reply_to"))
    drafted_chunks = sum(1 for c in state["chunks"] if c["comments"])
    flagged_resolved = sum(1 for c in state["chunks"] if c["status"] == "dismissed"
                           and c["id"] in state.get("flagged_queue", []))
    return {
        "reviewed": len(state["chunks"]),
        "drafted": drafts,
        "drafted_chunks": drafted_chunks,
        "replies": replies,
        "flagged_resolved": flagged_resolved,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: _state.py <state-file> <op> [args...]", file=sys.stderr)
        return 2
    path = argv[1]
    op = argv[2]
    state = load(path)
    rest = argv[3:]

    if op == "dismiss":
        action_dismiss(state, rest[0])
    elif op == "flag":
        action_flag(state, rest[0])
    elif op == "defer":
        action_defer(state, rest[0])
    elif op == "back":
        action_back(state)
    elif op == "comment":
        # comment <cid> <anchor-or-empty> <body> [in_reply_to]
        cid = rest[0]
        anchor = rest[1] or None
        body = rest[2]
        in_reply_to = rest[3] if len(rest) > 3 and rest[3] else None
        action_comment(state, cid, anchor, body, in_reply_to)
    elif op == "add-note":
        # add-note <cid> <kind> <body> [prompt]
        cid = rest[0]
        kind = rest[1]
        body = rest[2]
        prompt = rest[3] if len(rest) > 3 else None
        action_add_note(state, cid, kind, body, prompt)
    elif op == "set-verdict":
        action_set_verdict(state, rest[0])
    elif op == "set-body":
        action_set_body(state, rest[0])
    elif op == "set-summary":
        action_set_summary(state, rest[0])
    elif op == "edit-comment":
        action_edit_comment(state, rest[0], int(rest[1]), rest[2])
    elif op == "promote-flagged":
        if not promote_to_flagged_phase(state):
            print("NO_TRANSITION", file=sys.stderr)
            return 3
    elif op == "stats":
        print(json.dumps(stats(state), indent=2))
        return 0
    else:
        print(f"_state: unknown op: {op}", file=sys.stderr)
        return 2

    save(path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
