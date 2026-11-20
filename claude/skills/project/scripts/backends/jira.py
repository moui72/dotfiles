"""Jira Cloud backend.

Profile settings:
  "jira": {"client_dir": "<dir holding _client.py>"}
`_client.py` must expose get_clients() -> (atlassian.Jira, _) and make_adf(text) -> ADF dict. The
backend chdirs into client_dir before loading it, because some token loaders resolve paths from there.

Note frontmatter: jira_epic (KEY-1), jira_project (KEY), owns (JQL for the project's issues).
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

FIELDS = "key,summary,status,assignee,reporter,created,updated"


def _ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z")


def _adf_text(node):
    if isinstance(node, list):
        return "".join(_adf_text(node=n) for n in node)
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    return _adf_text(node=node.get("content", [])) + (" " if node.get("type") in ("paragraph", "heading") else "")


def _flat(raw):
    f = raw["fields"]
    return {"key": raw["key"], "summary": f["summary"], "status": f["status"]["name"],
            "assignee": f["assignee"]["displayName"] if f.get("assignee") else "Unassigned",
            "reporter": f["reporter"]["displayName"] if f.get("reporter") else "?",
            "updated": _ts(f["updated"])}


class Backend:
    name = "Jira"
    syncs = True

    def __init__(self, profile):
        cfg = profile.get("jira") or {}
        client_dir = Path(cfg.get("client_dir") or "").expanduser()
        if not (client_dir / "_client.py").exists():
            sys.exit(f"jira backend: profile jira.client_dir must hold _client.py (got {str(client_dir)!r})")
        os.chdir(client_dir)
        sys.path.insert(0, str(client_dir))
        from _client import get_clients, make_adf
        self.jira, _ = get_clients()
        self._make_adf = make_adf
        self._me = None

    def _search(self, jql):
        issues, token = [], None
        while True:
            params = {"jql": jql, "fields": FIELDS, "maxResults": 100}
            if token:
                params["nextPageToken"] = token
            r = self.jira.get(path="rest/api/3/search/jql", params=params)
            issues += [_flat(raw=i) for i in r["issues"]]
            token = r.get("nextPageToken")
            if not token:
                return issues

    def _myself(self):
        if self._me is None:
            self._me = self.jira.get(path="rest/api/3/myself")
        return self._me

    def me(self):
        return self._myself()["accountId"]

    def my_name(self):
        return self._myself()["displayName"]

    def owned(self, meta):
        return {i["key"]: i for i in self._search(jql=f"({meta['owns']}) OR key = {meta['jira_epic']}")}

    def open_owned(self, meta):
        return self._search(jql=f"({meta['owns']}) AND statusCategory != Done ORDER BY key")

    def get(self, key):
        return self._search(jql=f"key = {key}")[0]

    def my_open(self):
        return self._search(jql="assignee = currentUser() AND statusCategory != Done ORDER BY created DESC")

    def _transition(self, key, to):
        for t in self.jira.get(path=f"rest/api/3/issue/{key}/transitions")["transitions"]:
            if t["to"]["name"].lower() == to.lower():
                return t
        return None

    def transition_via(self, key, to):
        t = self._transition(key=key, to=to)
        return t["name"] if t else None

    def transition(self, key, to):
        t = self._transition(key=key, to=to)
        if not t:
            raise RuntimeError(f"{key}: no transition to {to!r}")
        self.jira._session.post(f"{self.jira.url}/rest/api/3/issue/{key}/transitions",
                                json={"transition": {"id": str(t["id"])}}).raise_for_status()
        got = self.get(key=key)["status"]
        if got.lower() != to.lower():
            raise RuntimeError(f"{key}: transitioned but status is {got!r}, expected {to!r}")

    def comment(self, key, text):
        self.jira.post(path=self.jira.resource_url("issue", api_version=3) + f"/{key}/comment",
                       data={"body": self._make_adf(text)})

    def comments_since(self, key, since, me):
        out = []
        for c in self.jira.get(path=f"rest/api/3/issue/{key}/comment", params={"maxResults": 100}).get("comments", []):
            created = _ts(c["created"])
            if c["author"]["accountId"] != me and created > since:
                text = re.sub(r"\s+", " ", _adf_text(node=c.get("body"))).strip()
                out.append((created.date().isoformat(), c["author"]["displayName"], text[:300]))
        return out

    def create(self, meta, summary):
        project_id = self.jira.get(path=f"rest/api/3/project/{meta['jira_project']}")["id"]
        me = self.me()
        fields = {"project": {"id": project_id}, "issuetype": {"name": "Story"}, "summary": summary,
                  "parent": {"key": meta["jira_epic"]}, "reporter": {"accountId": me}, "assignee": {"accountId": me}}
        r = self.jira._session.post(f"{self.jira.url}/rest/api/3/issue", json={"fields": fields})
        if r.status_code != 201:
            raise RuntimeError(f"create failed {r.status_code}: {r.text}")
        return r.json()["key"]

    def url(self, key):
        return f"{self.jira.url}/browse/{key}"

    def init_meta(self, args):
        if not args.epic or not args.owns:
            sys.exit("init with the jira tracker needs --epic KEY-1 and --owns JQL")
        return [f"jira_epic: {args.epic}", f"jira_project: {args.epic.split('-')[0]}", f"owns: {args.owns}"]
