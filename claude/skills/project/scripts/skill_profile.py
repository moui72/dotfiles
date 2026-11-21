"""Per-machine profile for the project skill.

The profile is a JSON file that lives on the machine, never in the dotfiles repo:
  $PROJECT_SKILL_PROFILE, else ~/.config/project-skill/profile.json
With no file, the defaults apply: tracker "none", vault ~/Documents, notes in <vault_dir>/projects.

Keys (all optional):
  vault_dir           the notes vault: holds todo/ and Todos.base (`project todo`, `project report`)
  notes_dir           where the project notes live (one <slug>.md per project); default <vault_dir>/projects
  tracker             "none" | "jira" | "linear" (a backend module under backends/). This is the
                      default; a note's own `tracker:` frontmatter overrides it for that project
  issue_url           browse-URL template for a tracker key, e.g. https://example.atlassian.net/browse/{key}
                      (`project todo` turns `--issue KEY` into this link)
  issue_field         frontmatter field `project todo` stores the issue link in (default "issue")
  github_org          default owner for bare `repo#123` references in notes
  done_statuses       statuses that count as closed (also hides stories from the hooks)
  in_flight_statuses  statuses that mean "being worked on" (audit flags these when no PR exists)
  instructions        path to a markdown file of machine-specific conventions; the SessionStart
                      hook tells the agent to read it
  kick                shell command `project kick` runs (e.g. refresh a token, restart a job)
  jira, linear        backend settings, see backends/jira.py and backends/linear.py

Env overrides: OBSIDIAN_VAULT (vault_dir), PROJECT_NOTES_DIR (notes_dir), PROJECT_TRACKER (tracker).

CLI for shell scripts: `skill_profile.py get KEY` prints one value (paths expanded, lists one per line).
"""
import json
import os
from pathlib import Path

DEFAULTS = {
    "vault_dir": "~/Documents",
    "notes_dir": "",
    "issue_url": "",
    "issue_field": "issue",
    "tracker": "none",
    "github_org": "",
    "done_statuses": ["Done"],
    "in_flight_statuses": ["In Progress", "In Review"],
    "instructions": "",
    "kick": "",
}


def profile_path():
    return Path(os.environ.get("PROJECT_SKILL_PROFILE") or "~/.config/project-skill/profile.json").expanduser()


def load():
    prof = dict(DEFAULTS)
    path = profile_path()
    if path.exists():
        prof.update(json.loads(path.read_text()))
    if os.environ.get("OBSIDIAN_VAULT"):
        prof["vault_dir"] = os.environ["OBSIDIAN_VAULT"]
    if os.environ.get("PROJECT_NOTES_DIR"):
        prof["notes_dir"] = os.environ["PROJECT_NOTES_DIR"]
    if os.environ.get("PROJECT_TRACKER"):
        prof["tracker"] = os.environ["PROJECT_TRACKER"]
    prof["vault_dir"] = Path(prof["vault_dir"]).expanduser()
    prof["notes_dir"] = Path(prof["notes_dir"]).expanduser() if prof["notes_dir"] else prof["vault_dir"] / "projects"
    prof["path"] = path if path.exists() else None
    return prof


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != "get":
        sys.exit("usage: skill_profile.py get KEY")
    val = load().get(sys.argv[2], "")
    print("\n".join(map(str, val)) if isinstance(val, list) else ("" if val is None else val))
