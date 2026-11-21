"""Linear backend and the tracker-neutral CLI paths, run against an in-memory fake of Linear's GraphQL API.

Run: python3 -m pytest claude/skills/project/tests
"""
import importlib
import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


class FakeLinear:
    """Answers the queries linear.py sends. Issues are stored the way the API returns them."""

    def __init__(self):
        self.states = {"Backlog": "s-backlog", "Todo": "s-todo", "In Progress": "s-prog", "Done": "s-done", "Canceled": "s-canc"}
        self.types = {"Backlog": "backlog", "Todo": "unstarted", "In Progress": "started", "Done": "completed", "Canceled": "canceled"}
        self.issues = {}
        self.comments = {}
        self.calls = []
        self.page_size = 100
        self.add(key="ENG-1", title="First", state="Todo", project="Core")
        self.add(key="ENG-2", title="Second", state="In Progress")
        self.add(key="ENG-3", title="Old", state="Done")
        self.add(key="OPS-1", title="Other team", state="Todo")

    def add(self, key, title, state, project=None, assignee="Me Myself", updated="2026-01-02T00:00:00.000Z"):
        self.issues[key] = {"id": f"uuid-{key}", "identifier": key, "title": title, "url": f"https://linear.app/x/issue/{key}",
                            "updatedAt": updated, "state": {"name": state}, "assignee": {"name": assignee} if assignee else None,
                            "creator": {"name": "Pat Reporter"}, "_project": project,
                            "_assignee_id": "me-id" if assignee == "Me Myself" else "other"}

    def _match(self, issue, flt):
        team = flt.get("team", {}).get("key", {}).get("eq")
        if team and issue["identifier"].split("-")[0] != team:
            return False
        if "project" in flt and issue["_project"] != flt["project"]["name"]["eq"]:
            return False
        if "state" in flt and self.types[issue["state"]["name"]] in flt["state"]["type"]["nin"]:
            return False
        if "assignee" in flt and issue["_assignee_id"] != flt["assignee"]["id"]["eq"]:
            return False
        return True

    def __call__(self, query, variables=None):
        v = variables or {}
        self.calls.append((query, v))
        if "viewer" in query:
            return {"viewer": {"id": "me-id", "name": "Me Myself"}}
        if "issueUpdate" in query:
            issue = next(i for i in self.issues.values() if i["id"] == v["id"])
            issue["state"] = {"name": next(n for n, sid in self.states.items() if sid == v["s"])}
            return {"issueUpdate": {"success": True, "issue": issue}}
        if "issueCreate" in query:
            key = f"ENG-{len(self.issues) + 10}"
            self.add(key=key, title=v["i"]["title"], state="Backlog", project="Core" if v["i"].get("projectId") else None)
            self.issues[key]["_input"] = v["i"]
            return {"issueCreate": {"success": True, "issue": self.issues[key]}}
        if "commentCreate" in query:
            self.comments.setdefault(v["i"]["issueId"], []).append(v["i"]["body"])
            return {"commentCreate": {"success": True}}
        if "teams(" in query:
            nodes = [{"id": "team-eng", "states": {"nodes": [{"id": i, "name": n} for n, i in self.states.items()]}}]
            return {"teams": {"nodes": nodes if v["k"] == "ENG" else []}}
        if "projects(" in query:
            return {"projects": {"nodes": [{"id": "proj-core"}] if v["n"] == "Core" else []}}
        if "comments(" in query:
            return {"issue": {"comments": {"nodes": self.issues[v["id"]].get("_comments", [])}}}
        if "issue(id" in query:
            return {"issue": self.issues[v["id"]]}
        if "issues(" in query:
            hits = [i for i in self.issues.values() if self._match(issue=i, flt=v["f"])]
            start = int(v["after"] or 0)
            page = hits[start:start + self.page_size]
            more = start + self.page_size < len(hits)
            return {"issues": {"nodes": page, "pageInfo": {"hasNextPage": more, "endCursor": str(start + self.page_size)}}}
        raise AssertionError(f"unexpected query: {query}")


@pytest.fixture
def fake(monkeypatch):
    from backends import linear
    f = FakeLinear()
    monkeypatch.setattr(linear.Backend, "_gql", lambda self, query, variables=None: f(query=query, variables=variables))
    return f


@pytest.fixture
def backend(fake):
    from backends import linear
    return linear.Backend(profile={})


TEAM = {"linear_team": "ENG"}


def test_owned_is_the_whole_team_and_pages(backend, fake):
    fake.page_size = 2
    assert list(backend.owned(meta=TEAM)) == ["ENG-1", "ENG-2", "ENG-3"]
    assert backend.owned(meta=TEAM)["ENG-2"]["status"] == "In Progress"


def test_a_project_narrows_ownership(backend):
    assert list(backend.owned(meta={**TEAM, "linear_project": "Core"})) == ["ENG-1"]


def test_open_owned_leaves_out_closed_issues(backend):
    assert [i["key"] for i in backend.open_owned(meta=TEAM)] == ["ENG-1", "ENG-2"]


def test_any_team_status_can_be_set_directly(backend, fake):
    assert backend.transition_via(key="ENG-1", to="done") == "set status Done"
    assert backend.transition_via(key="ENG-1", to="Shipped") is None
    backend.transition(key="ENG-1", to="Done")
    assert fake.issues["ENG-1"]["state"]["name"] == "Done"
    with pytest.raises(RuntimeError):
        backend.transition(key="ENG-1", to="Shipped")


def test_comments_since_skips_mine_and_old_ones(backend, fake):
    from datetime import datetime, timezone
    fake.issues["ENG-1"]["_comments"] = [
        {"createdAt": "2026-03-02T10:00:00.000Z", "body": "new\nfrom Pat", "user": {"id": "pat", "name": "Pat"}, "botActor": None, "externalUser": None},
        {"createdAt": "2026-03-02T11:00:00.000Z", "body": "mine", "user": {"id": "me-id", "name": "Me"}, "botActor": None, "externalUser": None},
        {"createdAt": "2026-01-01T00:00:00.000Z", "body": "old", "user": {"id": "pat", "name": "Pat"}, "botActor": None, "externalUser": None},
        {"createdAt": "2026-03-03T00:00:00.000Z", "body": "synced", "user": None, "botActor": {"name": "GitHub"}, "externalUser": None},
    ]
    got = backend.comments_since(key="ENG-1", since=datetime(2026, 3, 1, tzinfo=timezone.utc), me="me-id")
    assert got == [("2026-03-02", "Pat", "new from Pat"), ("2026-03-03", "GitHub", "synced")]


def test_create_assigns_me_and_reports_the_real_status(backend, fake):
    made = backend.create(meta={**TEAM, "linear_project": "Core"}, summary="New thing")
    assert made["status"] == "Backlog"
    assert fake.issues[made["key"]]["_input"] == {"teamId": "team-eng", "title": "New thing", "assigneeId": "me-id", "projectId": "proj-core"}
    with pytest.raises(RuntimeError):
        backend.create(meta={**TEAM, "linear_project": "Nope"}, summary="x")


def test_comment_goes_to_the_issue_uuid(backend, fake):
    backend.comment(key="ENG-2", text="hello")
    assert fake.comments == {"uuid-ENG-2": ["hello"]}


def test_init_meta(backend):
    assert backend.init_meta(args=Namespace(team="ENG", project="Core")) == ["linear_team: ENG", "linear_project: Core"]
    assert backend.init_meta(args=Namespace(team=None, project=None)) == []


def test_no_key_is_only_an_error_once_the_api_is_needed(monkeypatch, tmp_path):
    from backends import linear
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    b = linear.Backend(profile={"linear": {"api_key_file": str(tmp_path / "missing")}})
    assert b.init_meta(args=Namespace(team=None, project=None)) == []
    with pytest.raises(SystemExit):
        b.me()


def test_key_file_and_env(monkeypatch, tmp_path):
    from backends import linear
    (tmp_path / "k").write_text("lin_file\n")
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    assert linear.Backend(profile={"linear": {"api_key_file": str(tmp_path / "k")}})._api_key() == "lin_file"
    assert linear.Backend(profile={"linear": {"api_key_cmd": "echo lin_cmd"}})._api_key() == "lin_cmd"
    monkeypatch.setenv("LINEAR_API_KEY", "lin_env")
    assert linear.Backend(profile={})._api_key() == "lin_env"


# ---------- the CLI end to end ----------

def load_cli(monkeypatch, tmp_path, default):
    """project.py loaded against a temp profile whose default tracker is `default`; returns run(*argv)."""
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"notes_dir": str(tmp_path / "notes"), "tracker": default,
                                   "done_statuses": ["Done", "Canceled"]}))
    monkeypatch.setenv("PROJECT_SKILL_PROFILE", str(profile))
    monkeypatch.delenv("PROJECT_NOTES_DIR", raising=False)
    monkeypatch.delenv("PROJECT_TRACKER", raising=False)
    sys.modules.pop("project", None)
    project = importlib.import_module("project")

    def run(*argv, capsys=None):
        monkeypatch.setattr(sys, "argv", ["project", *argv])
        project.main()

    run.notes = tmp_path / "notes"
    return run


@pytest.fixture
def cli(fake, monkeypatch, tmp_path):
    return load_cli(monkeypatch=monkeypatch, tmp_path=tmp_path, default="linear")


@pytest.fixture
def cli_no_default(fake, monkeypatch, tmp_path):
    return load_cli(monkeypatch=monkeypatch, tmp_path=tmp_path, default="none")


def test_init_sync_apply_round_trip(cli, fake, capsys):
    cli("init", "Engine", "--team", "ENG", "--alias", "eng")
    note = cli.notes / "engine.md"
    text = note.read_text()
    assert "linear_team: ENG" in text and "| ENG-1 | Todo | Todo | First |" in text and "ENG-3" not in text

    text = text.replace("| ENG-1 | Todo | Todo |", "| ENG-1 | In Progress | Todo |")
    text = text.replace("## Planned\n", "## Planned\n- [ ] Brand new\n").replace("## Comments to post\n", "## Comments to post\n- ENG-2: shipped it\n")
    note.write_text(text)
    fake.issues["ENG-2"]["state"] = {"name": "Done"}  # someone closed it in Linear

    capsys.readouterr()
    cli("sync", "engine")
    plan = capsys.readouterr().out
    assert "ENG-1: Todo -> In Progress via 'set status In Progress'" in plan
    assert "CREATE issue in team ENG: Brand new" in plan
    assert "ENG-2: shipped it" in plan
    assert "ENG-2: Linear moved In Progress -> Done" in plan
    assert fake.issues["ENG-1"]["state"]["name"] == "Todo"  # a dry run writes nothing

    cli("sync", "engine", "--apply", "--no-commit")
    after = note.read_text()
    assert fake.issues["ENG-1"]["state"]["name"] == "In Progress"
    assert fake.comments == {"uuid-ENG-2": ["shipped it"]}
    assert "| ENG-1 | In Progress | In Progress |" in after and "| ENG-2 | Done | Done |" in after
    assert "| Backlog | Backlog | Brand new |" in after and "- [ ] Brand new" not in after

    capsys.readouterr()
    cli("sync", "engine")
    assert "outbound transitions: none" in capsys.readouterr().out


def test_local_only_notes_are_left_out_of_sync(cli, fake, capsys):
    cli("init", "Side Thing")
    cli("init", "Engine", "--team", "ENG")
    assert "linear_team" not in (cli.notes / "side-thing.md").read_text()
    capsys.readouterr()
    cli("sync")
    out = capsys.readouterr().out
    assert "== Engine" in out and "Side Thing" not in out
    assert "unclaimed (assigned to you, in no project): 1" in out and "OPS-1" in out
    with pytest.raises(SystemExit, match="local-only"):
        cli("sync", "side thing")
    capsys.readouterr()
    cli("status", "side thing")
    assert "STALE" not in capsys.readouterr().out


# ---------- per-note tracker override ----------

def test_a_note_can_name_a_tracker_the_profile_does_not_default_to(cli_no_default, fake, capsys):
    cli = cli_no_default
    cli("init", "Plain")
    cli("init", "Engine", "--tracker", "linear", "--team", "ENG")
    text = (cli.notes / "engine.md").read_text()
    assert "tracker: linear\nlinear_team: ENG" in text and "| ENG-1 | Todo | Todo |" in text
    assert "tracker:" not in (cli.notes / "plain.md").read_text()

    (cli.notes / "engine.md").write_text(text.replace("| ENG-1 | Todo | Todo |", "| ENG-1 | Done | Todo |"))
    capsys.readouterr()
    cli("sync")
    out = capsys.readouterr().out
    assert "ENG-1: Todo -> Done" in out and "Plain" not in out and "OPS-1" in out
    cli("sync", "engine", "--apply", "--no-commit")
    assert fake.issues["ENG-1"]["state"]["name"] == "Done"
    with pytest.raises(SystemExit, match="local-only"):
        cli("sync", "plain")


def test_tracker_none_keeps_a_note_local_under_a_default_tracker(cli, fake, capsys):
    cli("init", "Engine", "--team", "ENG")
    note = cli.notes / "engine.md"
    note.write_text(note.read_text().replace("linear_team: ENG", "tracker: none\nlinear_team: ENG"))
    with pytest.raises(SystemExit, match="local-only"):
        cli("sync", "engine")
    cli("init", "Offline", "--tracker", "none")
    assert "tracker: none" in (cli.notes / "offline.md").read_text()


def test_with_no_tracker_anywhere_sync_explains_itself(cli_no_default):
    cli_no_default("init", "Plain")
    with pytest.raises(SystemExit, match="nothing to sync"):
        cli_no_default("sync")


def test_an_unknown_tracker_is_a_clear_error_and_never_breaks_the_hooks(cli_no_default):
    from backends import linked
    with pytest.raises(SystemExit, match="no tracker backend named 'trello'"):
        cli_no_default("init", "X", "--tracker", "trello")
    assert linked(profile={"tracker": "none"}, meta={"tracker": "trello", "linear_team": "ENG"}) is False


def test_hook_index_follows_each_notes_tracker(cli_no_default, monkeypatch):
    cli_no_default("init", "Plain Project")
    cli_no_default("init", "Engine", "--tracker", "linear", "--team", "ENG")
    sys.path.insert(0, str(SCRIPTS.parent / "hooks"))
    sys.modules.pop("project_context", None)
    ctx = importlib.import_module("project_context")
    projs = {p["title"]: p for p in ctx.projects()}
    assert projs["Engine"]["linked"] and projs["Engine"]["tracker"] == "linear"
    assert not projs["Plain Project"]["linked"]
    assert "linear" in ctx.rule(projs=list(projs.values()))
    assert ctx.rule(projs=[projs["Plain Project"]]) == ctx.LOCAL_RULE


# ---------- connector mode: the agent carries the data ----------

def write_json(path, data):
    path.write_text(json.dumps(data))
    return str(path)


def test_connector_mode_round_trip(cli, fake, capsys, tmp_path, monkeypatch):
    cli("init", "Engine", "--team", "ENG")           # seeded through the fake API
    note = cli.notes / "engine.md"
    text = note.read_text().replace("| ENG-1 | Todo | Todo |", "| ENG-1 | Done | Todo |")
    note.write_text(text.replace("## Planned\n", "## Planned\n- [ ] Brand new\n")
                    .replace("## Comments to post\n", "## Comments to post\n- ENG-1: shipped it\n")
                    .replace("last_synced: ", "last_synced: 2026-02-01T00:00:00+00:00\nx_was: "))
    monkeypatch.setattr(type(fake), "__call__", lambda *a, **k: pytest.fail("connector mode must not call the API"))

    # Shaped the way the Linear connector returns issues; ENG-1 is absent because it hasn't changed.
    snap = write_json(tmp_path / "snap.json", {"me": "Me Myself", "statuses": ["Todo", "In Progress", "Done"], "issues": [
        {"id": "ENG-2", "title": "Second", "status": "Done", "assignee": "Me Myself", "createdBy": "Pat Reporter",
         "updatedAt": "2026-03-01T00:00:00.000Z", "url": "https://linear.app/x/issue/ENG-2",
         "comments": [{"createdAt": "2026-03-01T00:00:00.000Z", "author": {"name": "Pat Reporter"}, "body": "is this live?"},
                      {"createdAt": "2026-03-01T01:00:00.000Z", "author": "Me Myself", "body": "yes"}]},
        {"id": "ENG-7", "title": "Filed by Pat", "status": "Todo", "assignee": None, "createdBy": "Pat Reporter",
         "updatedAt": "2026-03-02T00:00:00.000Z"}]})

    capsys.readouterr()
    cli("sync", "engine", "--snapshot", snap)
    out = capsys.readouterr().out
    assert "ENG-1: Todo -> Done via 'set status Done'" in out and "no longer matched" not in out
    assert "ENG-2: Linear moved In Progress -> Done" in out and "ENG-7: new under" in out
    assert "comment from Pat Reporter" in out and "yes" not in out.split("connector mode")[0].split("inbound")[1]
    writes = json.loads(out[out.index("[\n"):])
    assert writes == [{"op": "transition", "key": "ENG-1", "to": "Done"},
                      {"op": "comment", "key": "ENG-1", "text": "shipped it"},
                      {"op": "create", "summary": "Brand new", "assignee": "me", "where": {"linear_team": "ENG"}}]

    before = note.read_text()
    with pytest.raises(RuntimeError, match="no outcome recorded"):   # apply with no results writes nothing
        cli("sync", "engine", "--apply", "--no-commit", "--snapshot", snap)
    assert note.read_text() == before

    results = write_json(tmp_path / "results.json", [
        {"op": "transition", "key": "ENG-1", "ok": True, "status": "Done"},
        {"op": "comment", "key": "ENG-1", "ok": True},
        {"op": "create", "summary": "Brand new", "ok": True, "key": "ENG-9", "status": "Backlog"}])
    cli("sync", "engine", "--apply", "--no-commit", "--snapshot", snap, "--results", results)
    after = note.read_text()
    assert "| ENG-1 | Done | Done |" in after and "| ENG-2 | Done | Done |" in after
    assert "| ENG-9 | Backlog | Backlog | Brand new |" in after and "| ENG-7 | Todo | Todo | Filed by Pat |" in after
    assert "Pat Reporter on [ENG-2](https://linear.app/x/issue/ENG-2): is this live?" in after
    assert "- ENG-1: shipped it" not in after and "- [ ] Brand new" not in after
    stamped = [l for l in after.splitlines() if l.startswith("last_synced: ")][0]
    assert "2026-02-01" not in stamped and stamped <= "last_synced: " + sys.modules["project"].now_iso()


def test_a_failed_connector_write_stops_the_apply(cli, fake, tmp_path):
    cli("init", "Engine", "--team", "ENG")
    note = cli.notes / "engine.md"
    note.write_text(note.read_text().replace("| ENG-1 | Todo | Todo |", "| ENG-1 | Done | Todo |"))
    synced = [l for l in note.read_text().splitlines() if l.startswith("last_synced")]
    snap = write_json(tmp_path / "snap.json", {"me": "Me Myself", "statuses": ["Todo", "Done"], "issues": []})
    results = write_json(tmp_path / "r.json", [{"op": "transition", "key": "ENG-1", "ok": False, "error": "forbidden"}])
    with pytest.raises(RuntimeError, match="forbidden"):
        cli("sync", "engine", "--apply", "--no-commit", "--snapshot", snap, "--results", results)
    after = note.read_text()
    assert "| ENG-1 | Done | Todo |" in after and [l for l in after.splitlines() if l.startswith("last_synced")] == synced


def test_connector_pull_and_init_need_no_results(cli_no_default, tmp_path, capsys):
    cli = cli_no_default
    snap = write_json(tmp_path / "snap.json", {"me": "Me Myself", "issues": [
        {"id": "ENG-1", "title": "First", "status": "Todo", "assignee": "Me Myself", "createdBy": "Pat"},
        {"id": "ENG-3", "title": "Old", "status": "Done", "assignee": None, "createdBy": "Pat"}]})
    cli("init", "Engine", "--tracker", "linear", "--team", "ENG", "--snapshot", snap)
    text = (cli.notes / "engine.md").read_text()
    assert "| ENG-1 | Todo | Todo | First | Me Myself |" in text and "ENG-3" not in text
    capsys.readouterr()
    cli("snapshot", "engine")
    req = json.loads(capsys.readouterr().out)
    assert req["scope"] == {"linear_team": "ENG"} and req["tracker"] == "linear" and req["updated_after"]
    cli("sync", "engine", "--pull", "--no-commit", "--snapshot", snap)
    with pytest.raises(SystemExit, match="one project at a time"):
        cli("sync", "--snapshot", snap)
