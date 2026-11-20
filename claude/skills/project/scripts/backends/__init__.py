"""Tracker backends. A backend publishes the notes to an issue tracker; the note stays the source of truth.

Every backend is a module here exposing `Backend(profile)`. Issues cross the boundary as flat dicts:
  {"key", "summary", "status", "assignee", "reporter", "updated" (aware datetime)}
so nothing above this layer reads a tracker's raw JSON.

Interface (see none.py for the minimal one, jira.py for a full one):
  name                      label used in plans and messages ("Jira")
  syncs                     False -> sync/resolve/init-from-tracker are unavailable
  me()                      the user's id in the tracker
  my_name()                 the user's display name
  owned(meta)               {key: issue} for everything the note's frontmatter claims
  open_owned(meta)          [issue] still open, for `init`
  get(key)                  one issue
  my_open()                 [issue] open and assigned to the user (for "unclaimed")
  transition_via(key, to)   name of the transition that reaches status `to`, or None
  transition(key, to)       move the issue; verify it landed; raise on failure
  comment(key, text)
  comments_since(key, since, me) -> [(YYYY-MM-DD, author, text)] from others
  create(meta, summary)     new story under the project; returns its key
  url(key)                  browse link
  init_meta(args)           frontmatter lines for a new note (list of "k: v")
"""
import importlib


def load_backend(profile):
    return importlib.import_module(f"backends.{profile['tracker']}").Backend(profile=profile)
