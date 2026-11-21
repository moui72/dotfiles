"""Tracker backends. A backend publishes the notes to an issue tracker; the note stays the source of truth.

Every backend is a module here exposing `Backend(profile)`. Issues cross the boundary as flat dicts:
  {"key", "summary", "status", "assignee", "reporter", "updated" (aware datetime)}
so nothing above this layer reads a tracker's raw JSON.

The profile's `tracker` is the machine's default. A note can override it with `tracker: <name>` in
its frontmatter (`tracker: none` keeps a note local on a machine whose default is a real tracker).

A note is linked to its tracker when its frontmatter has that backend's LINK_KEY (Jira: `owns`,
Linear: `linear_team`). Notes without it are local-only, even on a machine that has a tracker.

snapshot.py is not a tracker: it stands in for one in connector mode, reading from a file an agent
fetched through the tracker's connector (see its docstring).

Interface (see none.py for the minimal one, jira.py and linear.py for full ones):
  LINK_KEY                  module-level: the frontmatter key that links a note to this tracker
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
  create(meta, summary)     new story under the project; returns {"key", "status"}
  create_target(meta)       where a planned story would be created, for the dry-run plan
  project_status(meta)      the `status:` a new linked note starts with
  url(key)                  browse link
  init_meta(args)           frontmatter lines for a new note (list of "k: v"); [] = a local-only note
"""
import importlib


def tracker_name(profile, meta=None):
    """The tracker a note uses: its own `tracker:` if it has one, else the profile's default."""
    return ((meta or {}).get("tracker") or profile["tracker"]).strip().lower()


def _module(name):
    if not name.isidentifier():
        raise ModuleNotFoundError(f"no tracker backend named {name!r}")
    return importlib.import_module(f"backends.{name}")


def load_backend(profile, name=None):
    name = name or tracker_name(profile=profile)
    try:
        return _module(name=name).Backend(profile=profile)
    except ModuleNotFoundError:
        raise SystemExit(f"no tracker backend named {name!r} (looked for backends/{name}.py)") from None


def linked(profile, meta):
    """True when this note is tied to its tracker. Needs no credentials and no network."""
    try:
        key = _module(name=tracker_name(profile=profile, meta=meta)).LINK_KEY
    except ModuleNotFoundError:
        return False
    return bool(key and meta.get(key))
