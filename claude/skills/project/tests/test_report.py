"""`project report`: open todos, projects and unclaimed tracker issues in one read-only view."""
from datetime import date, timedelta

from test_linear import cli, cli_no_default, fake  # noqa: F401  (fixtures)


def todo(vault, slug, done="false", **fields):
    path = vault / "todo" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"done: {done}"] + [f"{k}: {v}" for k, v in fields.items()]
    path.write_text("---\n" + "\n".join(lines) + f"\n---\n# {slug}\n")


def test_report_groups_open_todos_and_flags_dates(cli_no_default, capsys):
    cli = cli_no_default
    today = date.today()
    todo(cli.vault, "pay-bill", title='"Pay the \\"big\\" bill"', area="home", due=today - timedelta(days=2))
    todo(cli.vault, "call", title='"Call back"', area="home", due=today + timedelta(days=3), issue="https://x.test/ENG-1")
    todo(cli.vault, "someday", title='"Someday"', area="", due="")
    todo(cli.vault, "completed/old", done="true", title='"Old"', area="home", due="")
    todo(cli.vault, "finished-in-place", done="true", title='"Finished"', area="home", due="")
    cli("init", "Side Thing")
    capsys.readouterr()
    cli("report")
    out = capsys.readouterr().out
    assert "== todos: 3 open" in out and "Old" not in out and "Finished" not in out
    assert '** OVERDUE 2d ** Pay the "big" bill' in out
    assert "** due in 3d ** Call back (https://x.test/ENG-1)  [todo/call.md]" in out
    assert out.index("(no area)") < out.index("home") and out.index("OVERDUE") < out.index("due in 3d")
    assert "== projects: 1" in out and "Side Thing [active] (local only) next:" in out
    assert "assigned to you" not in out  # no tracker anywhere


def test_report_without_a_todo_folder_says_so(cli_no_default, capsys):
    cli_no_default("report")
    assert "== todos: none kept on this machine" in capsys.readouterr().out


def test_report_lists_tracker_issues_no_note_claims(cli, capsys):
    cli("init", "Engine", "--team", "ENG")
    capsys.readouterr()
    cli("report")
    out = capsys.readouterr().out
    assert "== Linear: 1 assigned to you, in no project" in out and "OPS-1" in out and "ENG-1 [" not in out
    cli("report", "--offline")
    assert "Linear" not in capsys.readouterr().out


def test_report_survives_an_unreachable_tracker(cli, capsys, monkeypatch):
    import sys
    from backends import linear
    monkeypatch.setattr(linear.Backend, "my_open", lambda self: sys.exit("linear backend: no API key. Create one."))
    cli("init", "Side Thing")
    capsys.readouterr()
    cli("report")
    out = capsys.readouterr().out
    assert "== projects: 1" in out and "== linear: not reachable (linear backend: no API key)" in out
