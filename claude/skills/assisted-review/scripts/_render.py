"""Terminal-ready UI rendering for assisted-review.

Replaces template literals in templates.md with real ANSI escape bytes (0x1B).
Called by act.sh `print <surface> [args]`. The LLM consumes stdout verbatim.

Surfaces:
  preamble
  card [cid]                    (cid defaults to current queue head)
  end-of-review                 summary + draft list (no verdict prompt — separate)
  drafts
  threads <cid>                 expanded threads on a chunk
  prompt verdict                end-of-review verdict prompt
  prompt body                   end-of-review body prompt
  prompt body-frame <text>      "proposed body" frame for AI-generated body
  prompt final-confirm
  prompt submitted <url> <archive_path>
  prompt flagged-banner
  prompt quit
  prompt resume <relative-time> <done> <total>
  prompt bat-install
  prompt anchor-error <line>
  prompt verdict-invalid
  prompt open-threads <cid>
  prompt no-threads
  prompt drafted-comment-exists
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

E = "\x1b"

# Palette (codes from palette.md, with real ESC byte)
C = {
    "bcyan": f"{E}[1;36m",
    "bold": f"{E}[1m",
    "bwhite": f"{E}[1;37m",
    "cyan": f"{E}[36m",
    "dim": f"{E}[2m",
    "dimmag": f"{E}[2;35m",
    "yellow": f"{E}[33m",
    "byellow": f"{E}[1;33m",
    "bred": f"{E}[1;31m",
    "bgreen": f"{E}[1;32m",
    "red": f"{E}[31m",
    "green": f"{E}[32m",
    "r": f"{E}[0m",
}

RATING_STYLE = {
    "low": (C["bgreen"], "🟢"),
    "medium": (C["byellow"], "🟡"),
    "high": (C["bred"], "🔴"),
}

VERDICT_STYLE = {
    "APPROVE": C["bgreen"],
    "COMMENT": C["bcyan"],
    "REQUEST_CHANGES": C["bred"],
}


def _bracket(key: str) -> str:
    return f"{C['dim']}[{C['r']}{key}{C['dim']}]{C['r']}"


def _load(path: str) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Preamble
# ---------------------------------------------------------------------------

def render_preamble(state: dict[str, Any]) -> str:
    p = state["preamble"]
    pr = state["pr"]
    out: list[str] = []

    title = p.get("title", "")
    out.append(
        f"{C['bcyan']}PR {C['bwhite']}{pr['owner']}/{pr['repo']}#{pr['number']}{C['r']}"
        f"{C['bcyan']} — \"{title}\"{C['r']}"
    )
    out.append(
        f"{C['bold']}Author:{C['r']} @{p.get('author', '?')}  ·  "
        f"{C['bold']}Base:{C['r']} {p.get('base_ref', '?')} ← "
        f"{C['bold']}Head:{C['r']} {p.get('head_ref', '?')}  ·  "
        f"{C['bold']}HEAD:{C['r']} {p.get('head_short', '?')}"
    )
    draft = "yes" if p.get("is_draft") else "no"
    merge = p.get("mergeable")
    if merge is True or merge == "yes" or merge == "MERGEABLE":
        merge_styled = f"{C['green']}yes{C['r']}"
    elif merge is False or merge == "no" or merge == "CONFLICTING":
        merge_styled = f"{C['bred']}no (CONFLICTING){C['r']}"
    else:
        merge_styled = f"{C['dim']}unknown{C['r']}"
    out.append(
        f"{C['bold']}Draft:{C['r']} {draft}  ·  "
        f"{C['bold']}Mergeable:{C['r']} {merge_styled}"
    )

    ci = p.get("ci") or {}
    passing = ci.get("passing", 0)
    failing = ci.get("failing", 0)
    skipped = ci.get("skipped", 0)
    ci_parts = [f"{C['green']}{passing} passing{C['r']}"]
    if failing:
        ci_parts.append(f"{C['red']}{failing} failing{C['r']}")
    ci_parts.append(f"{C['dim']}{skipped} skipped/pending{C['r']}")
    line = f"{C['bold']}CI:{C['r']} " + ", ".join(ci_parts)
    failing_names = ci.get("failing_names") or []
    if failing_names:
        line += f"  {C['red']}{', '.join(failing_names)}{C['r']}"
    out.append(line)
    out.append(f"{C['bold']}URL:{C['r']} {C['cyan']}{pr['url']}{C['r']}")

    if p.get("is_draft"):
        out.append("")
        out.append(
            f"{C['byellow']}Warning:{C['r']} this is a draft PR. "
            "The author may not be ready for feedback."
        )

    not_mergeable = (
        merge in (False, "no", "CONFLICTING") or failing
    )
    if not_mergeable:
        out.append(f"{C['byellow']}Note:{C['r']} PR is not currently mergeable.")

    summary = p.get("ai_summary") or ""
    if summary:
        out.append("")
        out.append(summary)

    total = len(state["chunks"])
    skipped_gen = len((state.get("skipped") or {}).get("generated") or [])
    skipped_norisk = len((state.get("skipped") or {}).get("no_risk") or [])
    queued = len(state["cursor"]["queue"])
    out.append("")
    out.append(f"{C['bold']}{total} hunks total{C['r']}")
    if skipped_gen:
        out.append(
            f"  · {C['dim']}{skipped_gen} auto-skipped as generated/lockfiles{C['r']} "
            f"(type `{C['bold']}S{C['r']}` to list)"
        )
    if skipped_norisk:
        out.append(
            f"  · {C['dim']}{skipped_norisk} auto-skipped as no-risk{C['r']} "
            f"(type `{C['bold']}s{C['r']}` to inspect)"
        )
    out.append(f"  · {C['bwhite']}{queued} chunks queued for review{C['r']}")

    rs = state.get("rubric_source") or "default"
    out.append(f"  {C['dim']}Rubric: {rs}{C['r']}")

    threads_open = p.get("existing_threads_open", 0)
    threads_authors = p.get("existing_threads_authors") or []
    if threads_open:
        out.append("")
        out.append(
            f"{C['dim']}{threads_open} existing review thread(s) from "
            f"{', '.join(threads_authors)} will be shown on their chunks.{C['r']}"
        )

    out.append("")
    out.append(
        f"Press {C['bold']}Enter{C['r']} to begin "
        f"(or `{C['bold']}s{C['r']}` / `{C['bold']}S{C['r']}` to inspect skips first)."
    )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------

def _bat_mode() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        r = subprocess.run(
            [os.path.join(script_dir, "bat-check.sh")],
            capture_output=True, text=True, timeout=2,
        )
        return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _render_diff(diff_text: str, bat_mode: str) -> str:
    line_count = diff_text.count("\n")
    if bat_mode != "HIGHLIGHT" or line_count <= 15:
        return diff_text
    try:
        r = subprocess.run(
            ["bat", "-l", "diff", "--style=plain", "--paging=never", "--color=always"],
            input=diff_text, capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return diff_text


def render_card(state: dict[str, Any], cid: str | None) -> str:
    queue = state["cursor"]["queue"]
    phase = state["cursor"]["phase"]
    if not cid:
        if not queue:
            return _no_queue_msg(state)
        cid = queue[0]
    chunk = next((c for c in state["chunks"] if c["id"] == cid), None)
    if chunk is None:
        return f"{C['bred']}chunk not found: {cid}{C['r']}"

    try:
        idx = int(cid.lstrip("c"))
    except ValueError:
        idx = 0
    total = len(state["chunks"])
    rating = chunk.get("rating", "low")
    color, emoji = RATING_STYLE.get(rating, RATING_STYLE["low"])
    is_last = len(queue) == 1 and queue[0] == cid
    members = chunk.get("members") or []
    members_suffix = f" · {len(members)} hunks" if len(members) > 1 else ""

    out: list[str] = []
    dashes = "──────────────────────────────"
    out.append(
        f"{C['bcyan']}─── Chunk {idx} of {total} · {C['r']}"
        f"{color}{emoji} {rating}{C['r']}"
        f"{C['bcyan']}{members_suffix} {dashes}{C['r']}"
    )
    extra = f", +{len(members) - 1} more" if len(members) > 1 else ""
    out.append(
        f"{C['bwhite']}{chunk['file']}{C['r']}  "
        f"{C['dimmag']}{chunk['hunk_header']}{extra}{C['r']}"
    )
    out.append("")
    bat_mode = _bat_mode()
    out.append(_render_diff(chunk["diff"], bat_mode).rstrip("\n"))
    out.append("")

    # AI notes
    notes = chunk.get("ai_notes") or []
    if notes:
        out.append(f"{C['bold']}AI notes{C['r']}")
        for n in notes:
            kind = n.get("kind", "initial")
            body = n.get("body", "")
            if kind == "initial":
                out.append(f"  {body}")
            elif kind == "investigation":
                prompt = n.get("prompt", "")
                out.append(f"  {C['dim']}↳ asked:{C['r']} {prompt}")
                out.append(f"  {body}")
            elif kind == "context":
                out.append(f"  {C['dim']}↳ context:{C['r']} {body}")
            elif kind == "error":
                out.append(f"  {C['bred']}↳ error:{C['r']} {body}")
            else:
                out.append(f"  {body}")
        out.append("")

    # Existing threads
    threads = chunk.get("existing_threads") or []
    open_threads = [t for t in threads if t.get("is_open", True) and not t.get("resolved")]
    resolved_threads = [t for t in threads if not (t.get("is_open", True) and not t.get("resolved"))]
    if open_threads:
        out.append(f"{C['bold']}Existing threads{C['r']}")
        for t in open_threads:
            author = t.get("author", "?")
            bot = f"{C['yellow']}[bot]{C['r']}" if t.get("is_bot") else ""
            body = (t.get("body") or "").replace("\n", " ")
            if len(body) > 80:
                body = body[:77] + "…"
            out.append(f"  @{author}{bot} (open): \"{body}\"")
        if resolved_threads:
            out.append(f"  {C['dim']}({len(resolved_threads)} resolved — type `R` to view){C['r']}")
        out.append("")

    # Drafted comment hint
    if chunk.get("comments"):
        out.append(
            f"  {C['dim']}(drafted comment exists — re-comment to overwrite){C['r']}"
        )

    # Action menu
    out.append(f"{C['bold']}Actions{C['r']}")
    actions_main = [
        ("1", "more context"), ("2", "mark viewed"), ("3", "comment"),
        ("4", "ask AI"), ("5", "flag"), ("b", "back"),
        ("D", "dump drafts"), ("T", "show threads"), ("q", "quit & save"),
    ]
    if phase == "flagged":
        actions_main = [a for a in actions_main if a[0] != "5"]
    if is_last:
        actions_main = [a for a in actions_main if a[0] != "4"]

    # Group 3 per line for layout
    lines: list[str] = []
    cur: list[str] = []
    for key, label in actions_main:
        cur.append(f"{_bracket(key)} {label}")
        if len(cur) == 3:
            lines.append("  " + "   ".join(cur))
            cur = []
    if cur:
        lines.append("  " + "   ".join(cur))
    out.extend(lines)
    out.append(f"{C['bold']}>{C['r']}")

    return "\n".join(out)


def _no_queue_msg(state: dict[str, Any]) -> str:
    phase = state["cursor"]["phase"]
    flagged = len(state.get("flagged_queue") or [])
    if phase == "main" and flagged:
        return (
            f"{C['bcyan']}Main pass complete.{C['r']} "
            f"{C['bold']}{flagged}{C['r']} chunk(s) flagged for second look."
        )
    return f"{C['bcyan']}All chunks reviewed.{C['r']}"


# ---------------------------------------------------------------------------
# End-of-review
# ---------------------------------------------------------------------------

def render_end_of_review(state: dict[str, Any]) -> str:
    chunks = state["chunks"]
    drafts: list[tuple[str, dict[str, Any], int]] = []
    for c in chunks:
        for i, cm in enumerate(c["comments"]):
            drafts.append((c["file"], {**cm, "chunk_id": c["id"]}, i))
    drafts.sort(key=lambda x: (x[0], x[1].get("end_line") or 0))

    total_comments = sum(len(c["comments"]) for c in chunks)
    replies = sum(1 for c in chunks for x in c["comments"] if x.get("in_reply_to"))
    drafted_chunks = sum(1 for c in chunks if c["comments"])
    flagged = len(state.get("flagged_queue") or [])

    out: list[str] = []
    out.append(f"{C['bcyan']}Review complete.{C['r']}")
    out.append(f"  · {C['bold']}{len(chunks)}{C['r']} chunks reviewed")
    out.append(
        f"  · {C['bold']}{total_comments}{C['r']} comments drafted across "
        f"{C['bold']}{drafted_chunks}{C['r']} chunks"
    )
    out.append(f"  · {C['bold']}{replies}{C['r']} replies to existing threads")
    out.append(f"  · {C['bold']}{flagged}{C['r']} flagged chunks resolved on second pass")
    out.append("")

    if drafts:
        for file, cm, _idx in drafts:
            start, end = cm.get("start_line"), cm.get("end_line")
            line_label = f"{start}-{end}" if start and end and start != end else f"{end}"
            out.append(f"{C['bwhite']}{file}:{line_label}{C['r']}")
            body = cm.get("body", "")
            if cm.get("in_reply_to"):
                out.append(f"  {C['bold']}[reply to thread]:{C['r']} {body}")
            else:
                out.append(f"  {C['bold']}[new comment]:{C['r']} {body}")
        out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Drafts dump (action D)
# ---------------------------------------------------------------------------

def render_drafts(state: dict[str, Any]) -> str:
    rows: list[str] = []
    for c in state["chunks"]:
        for cm in c["comments"]:
            start, end = cm.get("start_line"), cm.get("end_line")
            line_label = f"{start}-{end}" if start and end and start != end else f"{end}"
            rows.append((c["file"], end or 0, line_label, cm))

    if not rows:
        return f"{C['dim']}(no comments drafted yet){C['r']}"

    rows.sort(key=lambda r: (r[0], r[1]))
    out: list[str] = []
    for file, _, line_label, cm in rows:
        out.append(f"{C['bwhite']}{file}:{line_label}{C['r']}")
        body = cm.get("body", "")
        if cm.get("in_reply_to"):
            out.append(f"  {C['bold']}[reply to thread]:{C['r']} {body}")
        else:
            out.append(f"  {C['bold']}[new comment]:{C['r']} {body}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Threads expanded (action T)
# ---------------------------------------------------------------------------

def render_threads(state: dict[str, Any], cid: str) -> str:
    chunk = next((c for c in state["chunks"] if c["id"] == cid), None)
    if chunk is None:
        return f"{C['bred']}chunk not found: {cid}{C['r']}"
    threads = chunk.get("existing_threads") or []
    if not threads:
        return f"{C['dim']}(no existing threads on this chunk){C['r']}"
    out = [f"{C['bold']}Existing threads (expanded){C['r']}"]
    for t in threads:
        author = t.get("author", "?")
        bot = f"{C['yellow']}[bot]{C['r']}" if t.get("is_bot") else ""
        body = t.get("body") or ""
        out.append(f"  {C['bold']}@{author}{C['r']}{bot}")
        for line in body.splitlines() or [""]:
            out.append(f"    {line}")
        for reply in (t.get("replies") or []):
            r_author = reply.get("author", "?")
            r_bot = f"{C['yellow']}[bot]{C['r']}" if reply.get("is_bot") else ""
            out.append(f"  {C['dim']}↳{C['r']} {C['bold']}@{r_author}{C['r']}{r_bot}")
            for line in (reply.get("body") or "").splitlines() or [""]:
                out.append(f"    {line}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def render_prompt(state: dict[str, Any], name: str, args: list[str]) -> str:
    if name == "verdict":
        self_auth = state["preamble"].get("self_authored", False)
        parts = []
        if not self_auth:
            parts.append(f"{_bracket('a')} {C['bgreen']}approve{C['r']}")
        parts.append(f"{_bracket('c')} {C['bcyan']}comment{C['r']}")
        parts.append(f"{_bracket('r')} {C['bred']}request changes{C['r']}")
        return (
            f"{C['bold']}Verdict:{C['r']}  " + "   ".join(parts) + f"\n{C['bold']}>{C['r']}"
        )

    if name == "verdict-invalid":
        return (
            f"{C['bred']}Unrecognized — pick one of a / c / r{C['r']} "
            f"(or `e <chunk-id>` to edit a draft)."
        )

    if name == "body":
        return (
            f"{C['bold']}Overall review body:{C['r']}  "
            f"{C['dim']}[type it / g to AI-generate / s to skip]{C['r']}\n"
            f"{C['bold']}>{C['r']}"
        )

    if name == "body-frame":
        body = args[0] if args else ""
        return (
            f"{C['bcyan']}─── proposed body ───{C['r']}\n"
            f"{body}\n"
            f"{C['bcyan']}──────────────────────{C['r']}\n"
            f"\n"
            f"{_bracket('e')} edit   {_bracket('a')} accept   {_bracket('r')} regenerate\n"
            f"{C['bold']}>{C['r']}"
        )

    if name == "final-confirm":
        dv = state["draft_review"]
        verdict = dv.get("verdict") or "?"
        vcolor = VERDICT_STYLE.get(verdict, C["bold"])
        body = dv.get("body") or ""
        body_preview = body[:200] + ("…" if len(body) > 200 else "") if body else f"{C['dim']}(empty){C['r']}"
        total_comments = sum(len(c["comments"]) for c in state["chunks"])
        replies = sum(1 for c in state["chunks"] for x in c["comments"] if x.get("in_reply_to"))
        inline = total_comments - replies
        url = state["pr"]["url"]
        return (
            f"{C['bcyan']}About to submit{C['r']} to {C['cyan']}{url}{C['r']}:\n"
            f"  {C['bold']}Event:{C['r']}    {vcolor}{verdict}{C['r']}\n"
            f"  {C['bold']}Body:{C['r']}     {body_preview}\n"
            f"  {C['bold']}Comments:{C['r']} {total_comments}  "
            f"{C['dim']}({inline} inline, {replies} replies){C['r']}\n"
            f"\n"
            f"  {_bracket('y')} submit   {_bracket('n')} cancel "
            f"{C['dim']}(keep draft){C['r']}\n"
            f"{C['bold']}>{C['r']}"
        )

    if name == "submitted":
        url = args[0] if args else ""
        archive = args[1] if len(args) > 1 else ""
        verdict = state["draft_review"].get("verdict") or "?"
        vcolor = VERDICT_STYLE.get(verdict, C["bold"])
        return (
            f"{C['bgreen']}Submitted:{C['r']} {vcolor}{verdict}{C['r']}\n"
            f"  {C['cyan']}{url}{C['r']}\n"
            f"\n"
            f"{C['dim']}State archived to {archive}{C['r']}"
        )

    if name == "flagged-banner":
        flagged = len(state.get("flagged_queue") or [])
        return (
            f"{C['bcyan']}Main pass complete.{C['r']} "
            f"{C['bold']}{flagged}{C['r']} chunk(s) flagged for second look.\n"
            f"{C['bcyan']}Beginning flagged review.{C['r']}"
        )

    if name == "quit":
        return (
            f"{C['bgreen']}Saved.{C['r']} Resume with "
            f"{C['bold']}assisted-review {state['pr']['url']}{C['r']}."
        )

    if name == "resume":
        rel = args[0] if args else "?"
        done = args[1] if len(args) > 1 else "?"
        total = args[2] if len(args) > 2 else "?"
        return (
            f"{C['byellow']}Found in-progress review{C['r']} from {rel} ago "
            f"({C['bold']}{done}{C['r']} of {C['bold']}{total}{C['r']} chunks complete).\n"
            f"  {_bracket('r')} resume   {_bracket('n')} restart   {_bracket('c')} cancel"
        )

    if name == "bat-install":
        return (
            f"{C['byellow']}bat is not installed{C['r']}, "
            "so diffs will render without syntax highlighting.\n"
            f"  {_bracket('y')} install now   {_bracket('n')} skip this time   "
            f"{_bracket('s')} skip and don't ask again"
        )

    if name == "anchor-error":
        line = args[0] if args else "?"
        return f"{C['bred']}line {line} not in hunk range, retry{C['r']}"

    if name == "open-threads":
        cid = args[0] if args else None
        chunk = next((c for c in state["chunks"] if c["id"] == cid), None) if cid else None
        if not chunk:
            return f"{C['bred']}chunk not found{C['r']}"
        threads = [t for t in (chunk.get("existing_threads") or [])
                   if t.get("is_open", True) and not t.get("resolved")]
        if not threads:
            return f"{C['dim']}(no open threads on this chunk){C['r']}"
        out = [f"This chunk has {C['bold']}{len(threads)}{C['r']} open thread(s):"]
        for i, t in enumerate(threads, 1):
            author = t.get("author", "?")
            bot = f"{C['yellow']}[bot]{C['r']}" if t.get("is_bot") else ""
            body = (t.get("body") or "").replace("\n", " ")
            if len(body) > 60:
                body = body[:57] + "…"
            out.append(f"  {_bracket(str(i))} @{author}{bot}: \"{body}\"")
        out.append(
            f"Reply to one (type number), or {_bracket('n')} new top-level comment?"
        )
        out.append(f"{C['bold']}>{C['r']}")
        return "\n".join(out)

    if name == "no-threads":
        return f"{C['dim']}(no existing threads on this chunk){C['r']}"

    if name == "comment-body":
        return (
            f"{C['bold']}Comment body{C['r']} "
            f"{C['dim']}(end with a blank line — or fence with `:::done` if the body itself contains a blank line){C['r']}:\n"
            f"{C['bold']}>{C['r']}"
        )

    return f"{C['bred']}unknown prompt: {name}{C['r']}"


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: _render.py <state_file> <surface> [args...]", file=sys.stderr)
        return 2
    state_file, surface, *rest = argv[1:]
    state = _load(state_file)

    if surface == "preamble":
        print(render_preamble(state))
    elif surface == "card":
        cid = rest[0] if rest else None
        print(render_card(state, cid))
    elif surface == "end-of-review":
        print(render_end_of_review(state))
    elif surface == "drafts":
        print(render_drafts(state))
    elif surface == "threads":
        if not rest:
            print(f"{C['bred']}threads: missing cid{C['r']}", file=sys.stderr)
            return 2
        print(render_threads(state, rest[0]))
    elif surface == "prompt":
        if not rest:
            print(f"{C['bred']}prompt: missing name{C['r']}", file=sys.stderr)
            return 2
        print(render_prompt(state, rest[0], rest[1:]))
    else:
        print(f"{C['bred']}unknown surface: {surface}{C['r']}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
