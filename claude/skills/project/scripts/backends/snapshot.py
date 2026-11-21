"""Connector mode: sync through an agent's tracker connector (MCP) instead of an API credential.

This process can't reach a connector; only the agent can. So the agent carries the data both ways:

  1. `project snapshot NAME` prints what to fetch. The agent fetches it with the connector and
     writes it to a snapshot file.
  2. `project sync NAME --snapshot FILE` plans from that file and lists the tracker writes it wants.
  3. After the user's yes, the agent makes those writes with the connector and records each
     outcome in a results file.
  4. `project sync NAME --apply --snapshot FILE --results RESULTS` records them in the note.

Reads come from the snapshot. Writes are never made here: `transition`, `comment` and `create`
look up the outcome the agent recorded, and raise when one is missing or failed, so the usual
apply rules hold (stop at the first failure, never advance last_synced after one).

Snapshot file (connector field names are accepted as they come: `id` for `key`, `createdBy` for
`creator`; `author` may be a name or an object with a `name`):
  {"me": "My Name",
   "statuses": ["Backlog", "Todo", "In Progress", "Done"],
   "issues": [{"key": "ENG-1", "title": "...", "status": "Todo", "assignee": "My Name" or null,
               "creator": "...", "updatedAt": "2026-01-02T03:04:05Z", "url": "...",
               "comments": [{"createdAt": "...", "author": "...", "body": "..."}]}]}

A sync snapshot holds only the issues updated since the note's last_synced, so it is `partial`:
a table row with no issue in the snapshot is unchanged, not gone. The note's last_synced advances
to the snapshot file's modified time, not to now, so nothing that changed in between is skipped.

Results file: a list of
  {"op": "transition", "key": "ENG-1", "ok": true, "status": "Done"}
  {"op": "comment", "key": "ENG-1", "ok": true}
  {"op": "create", "summary": "...", "ok": true, "key": "ENG-9", "status": "Backlog"}
  {"op": ..., "ok": false, "error": "why"}
"""
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _name(v):
    return (v.get("name") if isinstance(v, dict) else v) or None


class Backend:
    syncs = True
    partial = True

    def __init__(self, profile, real, snapshot, results=None):
        self.profile = profile
        mod = importlib.import_module(f"backends.{real}")
        self.name = mod.Backend.name
        self._real = object.__new__(mod.Backend)  # for its note-format helpers only; never initialized, never online
        path = Path(snapshot).expanduser()
        if not path.exists():
            sys.exit(f"snapshot file not found: {path}")
        data = json.loads(path.read_text())
        self.as_of = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        self._me = data.get("me") or sys.exit("snapshot: `me` (your name in the tracker) is required")
        self._statuses = {s.lower(): s for s in data.get("statuses") or []}
        self._issues, self._comments, self._urls = {}, {}, {}
        for raw in data.get("issues") or []:
            key = raw.get("key") or raw.get("id")
            updated = raw.get("updatedAt") or raw.get("updated")
            self._issues[key] = {
                "key": key, "summary": raw.get("title") or raw.get("summary") or "",
                "status": _name(raw.get("status")) or "?",
                "assignee": _name(raw.get("assignee")) or "Unassigned",
                "reporter": _name(raw.get("creator") or raw.get("createdBy") or raw.get("reporter")) or "?",
                "updated": _ts(updated) if updated else datetime.now(timezone.utc)}
            self._comments[key] = raw.get("comments") or []
            self._urls[key] = raw.get("url") or ""
        self._results = json.loads(Path(results).expanduser().read_text()) if results else []

    # ----- reads: from the snapshot -----

    def me(self):
        return self._me

    def my_name(self):
        return self._me

    def owned(self, meta):
        return dict(self._issues)

    def open_owned(self, meta):
        closed = {s.lower() for s in self.profile["done_statuses"]}
        return sorted((i for i in self._issues.values() if i["status"].lower() not in closed),
                      key=lambda i: int(i["key"].split("-")[1]))

    def get(self, key):
        if key not in self._issues:
            sys.exit(f"{key} isn't in the snapshot: fetch it with the connector and add it to the file")
        return self._issues[key]

    def my_open(self):
        sys.exit("connector mode syncs one project at a time: name a project")

    def transition_via(self, key, to):
        if not self._statuses:
            return f"set status {to}"
        real = self._statuses.get(to.lower())
        return f"set status {real}" if real else None

    def comments_since(self, key, since, me):
        out = []
        for c in sorted(self._comments.get(key, []), key=lambda c: c.get("createdAt") or ""):
            created = _ts(c["createdAt"])
            who = _name(c.get("author") or c.get("user")) or "an integration"
            if who == me or created <= since:
                continue
            out.append((created.date().isoformat(), who, " ".join((c.get("body") or "").split())[:300]))
        return out

    def url(self, key):
        return self._urls.get(key, "")

    # ----- writes: replay what the agent did with the connector -----

    def _result(self, op, **match):
        for r in self._results:
            if r.get("op") == op and all(r.get(k) == v for k, v in match.items()):
                if not r.get("ok"):
                    raise RuntimeError(f"{op} {match}: the connector write failed: {r.get('error', 'no reason recorded')}")
                return r
        raise RuntimeError(f"{op} {match}: no outcome recorded. Make this write with the connector, "
                           "add it to the results file, and pass --results")

    def transition(self, key, to):
        got = self._result(op="transition", key=key).get("status")
        if got and got.lower() != to.lower():
            raise RuntimeError(f"{key}: status is {got!r} after the connector write, expected {to!r}")

    def comment(self, key, text):
        self._result(op="comment", key=key)

    def create(self, meta, summary):
        r = self._result(op="create", summary=summary)
        if not r.get("key") or not r.get("status"):
            raise RuntimeError(f"create {summary!r}: the recorded outcome needs the new issue's `key` and `status`")
        return {"key": r["key"], "status": r["status"]}

    # ----- note format: the real backend's, which needs no credentials -----

    def create_target(self, meta):
        return self._real.create_target(meta=meta)

    def init_meta(self, args):
        return self._real.init_meta(args=args)

    def project_status(self, meta):
        epic = self._issues.get(meta.get("jira_epic"))
        return epic["status"] if epic else "active"
