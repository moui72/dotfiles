"""Per-machine profile for the project skill.

The profile is a JSON file that lives on the machine, never in the dotfiles repo:
  $PROJECT_SKILL_PROFILE, else ~/.config/project-skill/profile.json
With no file, the defaults apply: tracker "none", notes in ~/Documents/projects.

Keys (all optional):
  notes_dir           where the project notes live (one <slug>.md per project)
  tracker             "none" | "jira" (a backend module under backends/)
  github_org          default owner for bare `repo#123` references in notes
  done_statuses       statuses that count as closed (also hides stories from the hooks)
  in_flight_statuses  statuses that mean "being worked on" (audit flags these when no PR exists)
  instructions        path to a markdown file of machine-specific conventions; the SessionStart
                      hook tells the agent to read it
  kick                shell command `project kick` runs (e.g. refresh a token, restart a job)
  jira                backend settings, see backends/jira.py

Env overrides: PROJECT_NOTES_DIR (notes_dir), PROJECT_TRACKER (tracker).
"""
import json
import os
from pathlib import Path

DEFAULTS = {
    "notes_dir": "~/Documents/projects",
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
    if os.environ.get("PROJECT_NOTES_DIR"):
        prof["notes_dir"] = os.environ["PROJECT_NOTES_DIR"]
    if os.environ.get("PROJECT_TRACKER"):
        prof["tracker"] = os.environ["PROJECT_TRACKER"]
    prof["notes_dir"] = Path(prof["notes_dir"]).expanduser()
    prof["path"] = path if path.exists() else None
    return prof
