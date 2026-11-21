#!/usr/bin/env python3
"""Claude Code hook: make sessions notice when their work belongs to a tracked project.

SessionStart: inject the project index and the upkeep rule (plus a match if the current git branch
is named for a tracked story). UserPromptSubmit: if the prompt names a tracked story key or a
project's title/alias, inject which project it is; otherwise print nothing.

Reads only the local project notes (no tracker, no network), so it is fast and free.
Notes dir and tracker come from the machine's profile (scripts/skill_profile.py); with no notes, it prints nothing.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import skill_profile  # noqa: E402
from backends import linked, tracker_name  # noqa: E402

PROFILE = skill_profile.load()
NOTES = PROFILE["notes_dir"]
TRACKER = PROFILE["tracker"]
CLOSED = {"done", "wont do", "won't do", "closed", "cancelled", "canceled", "duplicate"} | {s.lower() for s in PROFILE["done_statuses"]}
KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")

SYNC_RULE = """Project upkeep. Applies when this session's work relates to a tracked project: a tracked story key, the project's title or alias, or a git branch named for one of its stories. Skip it when a project is only mentioned in passing.
- At checkpoints (a PR opened or merged, a story finished or blocked, a decision made, new work found, someone's question answered), update the project's note with the `project` skill: `## Current state` (declarative, point-in-time, linked), `next:`, a dated `## Log` line, the story's `status` cell (never the `synced` cell), new work under `## Planned`.
- Before finishing such a session, run the dry run `sync NAME`. Inbound changes may be pulled without asking with `sync NAME --pull` (it changes only the note). Anything that writes to the tracker ({tracker}: outbound transitions, comments to post, planned creates) is shown to the user as the plan and waits for their yes; then `sync NAME --apply`.
- A project marked "local only" in the index has no tracker link: keep its note current and skip the sync steps.
- A merged PR is evidence, not proof: ask about acceptance criteria and human steps before marking a story Done.
- Tell the user in one line when you update a project note."""

LOCAL_RULE = """Project upkeep. Applies when this session's work relates to a tracked project: its title or alias, a story key in its table, or a git branch named for one. Skip it when a project is only mentioned in passing.
- At checkpoints (a PR opened or merged, a story finished or blocked, a decision made, new work found), update the project's note with the `project` skill: `## Current state` (declarative, point-in-time, linked), `next:`, a dated `## Log` line, story `status` cells, new work under `## Planned`. There is no tracker on this machine; the note is the whole record.
- A merged PR is evidence, not proof: ask about acceptance criteria and human steps before marking a story Done.
- Tell the user in one line when you update a project note."""


def rule(projs):
    """The sync rule when any project is linked to a tracker (each note may name its own), else the local one."""
    trackers = sorted({p["tracker"] for p in projs if p["linked"]})
    return SYNC_RULE.format(tracker=" or ".join(trackers)) if trackers else LOCAL_RULE


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, flags=re.S)
    meta = {}
    for line in (m.group(1).splitlines() if m else []):
        k, _, v = line.partition(":")
        v = v.strip()
        meta[k.strip()] = [x.strip() for x in v[1:-1].split(",") if x.strip()] if v.startswith("[") and v.endswith("]") else v
    return meta


def open_keys(text):
    keys = []
    for line in text.split("<!-- jira:stories -->", 1)[-1].split("<!-- /jira:stories -->", 1)[0].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and KEY_RE.fullmatch(cells[0]) and cells[1].lower() not in CLOSED:
            keys.append(cells[0])
    return keys


def projects():
    out = []
    for path in sorted(NOTES.glob("*.md")) if NOTES.exists() else []:
        try:
            text = path.read_text()
        except OSError:
            continue
        meta = frontmatter(text)
        if not meta.get("title"):
            continue
        names = [meta["title"]] + [a for a in meta.get("aliases", []) if not KEY_RE.fullmatch(a)]
        out.append({"title": meta["title"], "path": str(path), "epic": meta.get("jira_epic", ""),
                    "names": names, "repos": meta.get("repos", []), "linked": linked(profile=PROFILE, meta=meta),
                    "tracker": tracker_name(profile=PROFILE, meta=meta), "keys": open_keys(text), "next": meta.get("next", "")})
    return out


def matches(text, projs):
    keys = set(KEY_RE.findall(text))
    hits = []
    for p in projs:
        why = sorted(keys & (set(p["keys"]) | ({p["epic"]} if p["epic"] else set())))
        named = [n for n in p["names"] if len(n) >= 4 and re.search(r"(?<![\w-]){}(?![\w-])".format(re.escape(n)), text, flags=re.I)]
        if why or named:
            hits.append((p, why + ["'{}'".format(n) for n in named]))
    return hits


def say(event, context):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    event = data.get("hook_event_name", "")
    projs = projects()
    if not projs:
        return
    if event == "SessionStart":
        lines = ["Tracked projects (notes in {}; use the `project` skill):".format(NOTES)]
        any_linked = any(p["linked"] for p in projs)
        for p in projs:
            lines.append("- {}{}{} aliases: {} | repos: {} | open: {}".format(
                p["title"], " [{}]".format(p["epic"]) if p["epic"] else "", "" if p["linked"] or not any_linked else " (local only)", ", ".join(p["names"][1:]) or "-", ", ".join(p["repos"]) or "-", ", ".join(p["keys"]) or "-"))
        branch = subprocess.run(["git", "-C", data.get("cwd") or ".", "branch", "--show-current"],
                                capture_output=True, text=True, timeout=5).stdout.strip()
        for p, why in matches(text=branch, projs=projs):
            lines.append("This session's git branch `{}` is named for {} in project *{}* ({}). The upkeep rule applies.".format(
                branch, ", ".join(why), p["title"], p["path"]))
        if PROFILE["instructions"]:
            lines.append("Machine-specific project conventions: read {} before syncing.".format(PROFILE["instructions"]))
        say(event=event, context="\n".join(lines + ["", rule(projs=projs)]))
    elif event == "UserPromptSubmit":
        hits = matches(text=data.get("prompt", ""), projs=projs)
        if hits:
            say(event=event, context="\n".join(
                "This prompt may relate to project *{}* ({}; matched {}). If the work does, follow the project upkeep rule.".format(
                    p["title"], p["path"], ", ".join(why)) for p, why in hits))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # a hook must never block a session
        print("project_context hook error: {}".format(e), file=sys.stderr)
