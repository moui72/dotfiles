"""`project todo`: writes a todo note in the format Todos.base and `project report` read."""
import io
import json
import os
import sys

import pytest

from test_linear import cli_no_default, fake  # noqa: F401  (fixtures)


@pytest.fixture
def cli(cli_no_default):
    (cli_no_default.vault / "todo" / "completed").mkdir(parents=True)
    (cli_no_default.vault / "Todos.base").write_text('views:\n  - filters:\n      and:\n        - area == "home"\n        - area == "job search"\n')
    return cli_no_default


def test_todo_writes_the_note_and_report_reads_it(cli, capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n# Dup heading\n\nWhy it matters.\n- [ ] step\n"))
    cli("todo", '  Pay the "big"  bill: café ', "--area", "home", "--due", "2026-12-01", "--issue", "https://x.test/i/9", "--body", "-", "--no-commit")
    path = cli.vault / "todo" / "pay-the-big-bill-cafe.md"
    assert path.read_text() == ('---\ndone: false\ntitle: "Pay the \\"big\\" bill: café"\nissue: https://x.test/i/9\narea: home\n'
                                'due: 2026-12-01\n---\n# Pay the "big" bill: café\n\nWhy it matters.\n- [ ] step\n')
    capsys.readouterr()
    cli("report", "--offline")
    assert 'Pay the "big" bill: café (https://x.test/i/9)' in capsys.readouterr().out


def test_todo_validates_and_never_overwrites(cli, capsys):
    cli("todo", "First", "--no-commit")
    assert (cli.vault / "todo" / "first.md").read_text() == '---\ndone: false\ntitle: "First"\narea:\ndue:\n---\n# First\n'
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        cli("todo", "First", "--no-commit")
    (cli.vault / "todo" / "completed" / "old.md").write_text("x")
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        cli("todo", "Old", "--no-commit")
    with pytest.raises(SystemExit, match="real date"):
        cli("todo", "Bad date", "--due", "2026-02-30")
    with pytest.raises(SystemExit, match="no issue_url"):
        cli("todo", "Bare key", "--issue", "ENG-1")
    with pytest.raises(SystemExit, match="TITLE is required"):
        cli("todo", "  ")
    capsys.readouterr()
    cli("todo", "Elsewhere", "--area", "garden", "--dry-run")
    io_ = capsys.readouterr()
    assert "WARNING area 'garden'" in io_.err and "area: garden" in io_.out and not (cli.vault / "todo" / "elsewhere.md").exists()
    cli("todo", "--list-areas")
    assert capsys.readouterr().out == "home\njob search\n"


def test_a_bare_key_uses_the_profiles_issue_url(cli, monkeypatch, tmp_path, capsys):
    import importlib
    profile = json.loads((tmp_path / "profile.json").read_text())
    (tmp_path / "profile.json").write_text(json.dumps({**profile, "issue_url": "https://t.test/issue/{key}", "issue_field": "jira"}))
    sys.modules.pop("project", None)
    project = importlib.import_module("project")
    for arg in ("eng-7", "https://old.test/browse/ENG-7?x=1"):
        monkeypatch.setattr(sys, "argv", ["project", "todo", "Linked", "--issue", arg, "--dry-run"])
        project.main()
        assert "jira: https://t.test/issue/ENG-7\n" in capsys.readouterr().out
