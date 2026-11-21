"""Linear backend. Talks to Linear's GraphQL API with the standard library only.

Profile settings (all optional):
  "linear": {"api_key_file": "~/.config/project-skill/linear-api-key", "api_key_cmd": ""}
The personal API key comes from, in order: $LINEAR_API_KEY, the stdout of `api_key_cmd`
(e.g. a password-manager read), then `api_key_file`. Nothing is read until the first API call,
so local-only commands work with no key at all.

Note frontmatter: linear_team (the team key, e.g. ENG), and optionally linear_project (a project
name). A note owns every issue in the team, or only those in the project when one is named. A note
with no linear_team is local-only and is never synced.

Linear has no workflow transitions: any status of the issue's team can be set directly.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

LINK_KEY = "linear_team"
API = "https://api.linear.app/graphql"
DEFAULT_KEY_FILE = "~/.config/project-skill/linear-api-key"
CLOSED_TYPES = ["completed", "canceled", "duplicate"]
ISSUE = "id identifier title url updatedAt state { name } assignee { name } creator { name }"


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class Backend:
    name = "Linear"
    syncs = True

    def __init__(self, profile):
        self.cfg = profile.get("linear") or {}
        self._key = None
        self._viewer = None
        self._teams = {}   # team key -> {"id", "states": {lowercased name: (id, name)}}
        self._ids = {}     # issue key -> uuid
        self._urls = {}    # issue key -> url

    # ----- transport -----

    def _api_key(self):
        if self._key:
            return self._key
        key = os.environ.get("LINEAR_API_KEY", "").strip()
        if not key and self.cfg.get("api_key_cmd"):
            r = subprocess.run(["bash", "-c", self.cfg["api_key_cmd"]], capture_output=True, text=True)
            if r.returncode:
                sys.exit(f"linear backend: api_key_cmd failed: {r.stderr.strip()}")
            key = r.stdout.strip()
        if not key:
            path = Path(self.cfg.get("api_key_file") or DEFAULT_KEY_FILE).expanduser()
            if path.exists():
                key = path.read_text().strip()
        if not key:
            sys.exit("linear backend: no API key. Create a personal key in Linear (Settings > Security & access), "
                     f"then set $LINEAR_API_KEY or save it to {DEFAULT_KEY_FILE} (chmod 600). "
                     "Inside a Claude session with a Linear connector, connector mode needs no key: "
                     "run `project snapshot NAME` and follow SKILL.md.")
        self._key = key
        return key

    def _gql(self, query, variables=None):
        req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": self._api_key()})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                out = json.load(resp)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Linear API {e.code}: {e.read().decode(errors='replace')[:300]}") from None
        if out.get("errors"):
            raise RuntimeError("Linear API: " + "; ".join(e.get("message", "?") for e in out["errors"]))
        return out["data"]

    # ----- helpers -----

    def _flat(self, raw):
        key = raw["identifier"]
        self._ids[key], self._urls[key] = raw["id"], raw["url"]
        return {"key": key, "summary": raw["title"], "status": raw["state"]["name"],
                "assignee": raw["assignee"]["name"] if raw.get("assignee") else "Unassigned",
                "reporter": raw["creator"]["name"] if raw.get("creator") else "?",
                "updated": _ts(raw["updatedAt"])}

    def _issues(self, flt):
        issues, after = [], None
        while True:
            page = self._gql(
                query="query($f: IssueFilter, $after: String) { issues(filter: $f, first: 100, after: $after) "
                      "{ nodes { " + ISSUE + " } pageInfo { hasNextPage endCursor } } }",
                variables={"f": flt, "after": after})["issues"]
            issues += [self._flat(raw=n) for n in page["nodes"]]
            if not page["pageInfo"]["hasNextPage"]:
                return sorted(issues, key=lambda i: int(i["key"].split("-")[1]))
            after = page["pageInfo"]["endCursor"]

    def _owns(self, meta):
        flt = {"team": {"key": {"eq": meta["linear_team"]}}}
        if meta.get("linear_project"):
            flt["project"] = {"name": {"eq": meta["linear_project"]}}
        return flt

    def _team(self, team_key):
        if team_key not in self._teams:
            nodes = self._gql(
                query="query($k: String!) { teams(filter: {key: {eq: $k}}) { nodes { id states { nodes { id name } } } } }",
                variables={"k": team_key})["teams"]["nodes"]
            if not nodes:
                raise RuntimeError(f"no Linear team with key {team_key!r}")
            self._teams[team_key] = {"id": nodes[0]["id"],
                                     "states": {s["name"].lower(): (s["id"], s["name"]) for s in nodes[0]["states"]["nodes"]}}
        return self._teams[team_key]

    def _state(self, key, to):
        return self._team(team_key=key.split("-")[0])["states"].get(to.lower())

    def _uuid(self, key):
        if key not in self._ids:
            self.get(key=key)
        return self._ids[key]

    def _me(self):
        if self._viewer is None:
            self._viewer = self._gql(query="{ viewer { id name } }")["viewer"]
        return self._viewer

    # ----- interface -----

    def me(self):
        return self._me()["id"]

    def my_name(self):
        return self._me()["name"]

    def owned(self, meta):
        return {i["key"]: i for i in self._issues(flt=self._owns(meta=meta))}

    def open_owned(self, meta):
        return self._issues(flt={**self._owns(meta=meta), "state": {"type": {"nin": CLOSED_TYPES}}})

    def get(self, key):
        return self._flat(raw=self._gql(query="query($id: String!) { issue(id: $id) { " + ISSUE + " } }",
                                        variables={"id": key})["issue"])

    def my_open(self):
        return self._issues(flt={"assignee": {"id": {"eq": self.me()}}, "state": {"type": {"nin": CLOSED_TYPES}}})

    def transition_via(self, key, to):
        state = self._state(key=key, to=to)
        return f"set status {state[1]}" if state else None

    def transition(self, key, to):
        state = self._state(key=key, to=to)
        if not state:
            raise RuntimeError(f"{key}: its team has no status {to!r}")
        r = self._gql(
            query="mutation($id: String!, $s: String!) { issueUpdate(id: $id, input: {stateId: $s}) "
                  "{ success issue { state { name } } } }",
            variables={"id": self._uuid(key=key), "s": state[0]})["issueUpdate"]
        got = r["issue"]["state"]["name"] if r.get("issue") else None
        if not r["success"] or (got or "").lower() != to.lower():
            raise RuntimeError(f"{key}: status is {got!r} after the update, expected {to!r}")

    def comment(self, key, text):
        r = self._gql(query="mutation($i: CommentCreateInput!) { commentCreate(input: $i) { success } }",
                      variables={"i": {"issueId": self._uuid(key=key), "body": text}})
        if not r["commentCreate"]["success"]:
            raise RuntimeError(f"{key}: comment was not created")

    def comments_since(self, key, since, me):
        nodes = self._gql(
            query="query($id: String!) { issue(id: $id) { comments(first: 100) { nodes "
                  "{ createdAt body user { id name } botActor { name } externalUser { name } } } } }",
            variables={"id": key})["issue"]["comments"]["nodes"]
        out = []
        for c in sorted(nodes, key=lambda n: n["createdAt"]):
            created = _ts(c["createdAt"])
            if (c.get("user") or {}).get("id") == me or created <= since:
                continue
            who = (c.get("user") or c.get("externalUser") or c.get("botActor") or {}).get("name") or "an integration"
            out.append((created.date().isoformat(), who, " ".join((c.get("body") or "").split())[:300]))
        return out

    def create(self, meta, summary):
        team = meta["linear_team"]
        fields = {"teamId": self._team(team_key=team)["id"], "title": summary, "assigneeId": self.me()}
        if meta.get("linear_project"):
            nodes = self._gql(
                query="query($n: String!, $k: String!) { projects(filter: {name: {eq: $n}, "
                      "accessibleTeams: {some: {key: {eq: $k}}}}) { nodes { id } } }",
                variables={"n": meta["linear_project"], "k": team})["projects"]["nodes"]
            if not nodes:
                raise RuntimeError(f"no Linear project named {meta['linear_project']!r} in team {team}")
            fields["projectId"] = nodes[0]["id"]
        r = self._gql(query="mutation($i: IssueCreateInput!) { issueCreate(input: $i) { success issue { " + ISSUE + " } } }",
                      variables={"i": fields})["issueCreate"]
        if not r["success"] or not r.get("issue"):
            raise RuntimeError(f"create failed for {summary!r}")
        made = self._flat(raw=r["issue"])
        return {"key": made["key"], "status": made["status"]}

    def create_target(self, meta):
        where = f"team {meta.get('linear_team', '')}"
        return f"issue in {where}, project {meta['linear_project']!r}" if meta.get("linear_project") else f"issue in {where}"

    def project_status(self, meta):
        return "active"

    def url(self, key):
        if key not in self._urls:
            self.get(key=key)
        return self._urls[key]

    def init_meta(self, args):
        if not args.team:
            if args.project:
                sys.exit("init: --project needs --team KEY")
            return []  # a local-only note
        return [f"linear_team: {args.team}"] + ([f"linear_project: {args.project}"] if args.project else [])
