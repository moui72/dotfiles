#!/usr/bin/env python3
"""Claude Code Stop hook: don't let a session end a turn with project upkeep owed.

Blocks the stop (once per checkpoint) when all of these hold:
  - the session hit a checkpoint: a Bash call that ran `gh pr create|merge|ready` as a command
    (heredoc bodies and other text inside a command don't count; commits and pushes aren't checkpoints);
  - the session relates to a tracked project: the human's prompts, those checkpoint commands, or the
    cwd's git branch name a tracked story key or a project's title/alias (same matching as
    project_context.py);
  - no `project.py ... sync` ran after the latest checkpoint.
The reason asks the agent to update the note and run the dry-run sync, or to say why the work isn't
project work. The agent can then stop: `stop_hook_active` and a per-session record of the last
checkpoint it was blocked for keep it from looping. A no-op in the unattended upkeep run
(PROJECT_UPKEEP_HEADLESS=1), and when the machine's profile has no tracker (nothing to sync).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_context import KEY_RE, TRACKER, matches, projects  # noqa: E402

STATE = Path.home() / ".claude" / "state" / "project_stop"
# A command in command position: start of a line or after ; & | ( && ||, optionally behind VAR=... prefixes.
CMD_POS = r"(?:^|[;&|(]|&&|\|\|)\s*(?:\w+=\S*\s+)*"
CHECKPOINT = re.compile(CMD_POS + r"gh\s+pr\s+(create|merge|ready)\b", re.M)
SYNC = re.compile(r"(?:project(?:\.py)?[\"']?|\$\{?P\}?[\"']?)\s+sync\b")  # `project sync`, `project.py sync`, `$P sync`
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?^\s*\1\s*$", re.S | re.M)


def command_text(cmd):
    """The command without heredoc bodies, which are data (scripts, file contents), not commands."""
    return HEREDOC.sub(" ", cmd)


def human_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def scan(transcript_path):
    """-> (human prompt text, [(tool_use_id, command)] checkpoints, index of last sync, indexed events)."""
    prompts, events = [], []
    with open(transcript_path) as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            msg = e.get("message") or {}
            if e.get("type") == "user" and not e.get("isMeta"):
                t = human_text(msg.get("content"))
                if t and not t.startswith("<"):  # skip command/hook wrappers
                    prompts.append(t)
            elif e.get("type") == "assistant":
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Bash":
                        events.append((b.get("id"), (b.get("input") or {}).get("command", "")))
    return " ".join(prompts), events


def main():
    data = json.load(sys.stdin)
    if data.get("stop_hook_active") or os.environ.get("PROJECT_UPKEEP_HEADLESS") or TRACKER == "none":
        return
    path = data.get("transcript_path")
    if not path or not os.path.exists(path):
        return
    prompts, events = scan(path)
    last_cp, last_sync, cp_cmds = None, -1, []
    for i, (tid, cmd) in enumerate(events):
        bare = command_text(cmd)
        if SYNC.search(bare):
            last_sync = i
        elif CHECKPOINT.search(bare):
            hit = CHECKPOINT.search(bare)
            line = bare[hit.start():].lstrip(";&|( \n").splitlines()[0]
            last_cp = (i, tid, line)
            cp_cmds.append(cmd)
    if not last_cp or last_cp[0] < last_sync:
        return
    projs = projects()
    branch = subprocess.run(["git", "-C", data.get("cwd") or ".", "branch", "--show-current"],
                            capture_output=True, text=True, timeout=5).stdout.strip()
    # The commits/PRs and branch are the strong signal; fall back to the prompts only when they name nothing.
    # Commands can carry arbitrary text (heredocs, file contents), so only their story keys count, not titles/aliases.
    cmd_keys = " ".join(KEY_RE.findall(" ".join(cp_cmds)))
    hits = matches(text=" ".join([branch, cmd_keys]), projs=projs) or matches(text=prompts, projs=projs)
    if not hits:
        return
    STATE.mkdir(parents=True, exist_ok=True)
    state_file = STATE / f"{data.get('session_id', 'unknown')}.json"
    try:
        if json.loads(state_file.read_text()).get("blocked_for") == last_cp[1]:
            return  # already asked about this checkpoint; the agent chose to stop
    except (OSError, ValueError):
        pass
    state_file.write_text(json.dumps({"blocked_for": last_cp[1]}))
    names = ", ".join(f"*{p['title']}* ({p['path']})" for p, _ in hits)
    print(json.dumps({"decision": "block", "reason": (
        f"Project upkeep check: this session hit a checkpoint (`{last_cp[2][:120]}`) for {names}, "
        "and no `project.py sync` has run since. If the work belongs to that project: update the note "
        "(Current state, next:, a Log line, story status cells) with the `project` skill, run the dry-run "
        "`sync NAME`, pull inbound with `--pull`, and show any tracker writes as a plan for the human's yes. "
        "If it doesn't (a passing mention), say so in one line and stop.")}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # a hook must never wedge a session
        print(f"project_stop hook error: {e}", file=sys.stderr)
