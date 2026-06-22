"""Shared fixtures for assisted-review unit tests.

Adds scripts/ to sys.path so `_state` and `_render` import cleanly.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def make_state(**overrides):
    s = {
        "pr": {
            "owner": "acme", "repo": "widget", "number": 42,
            "head_sha": "abc123", "url": "https://github.com/acme/widget/pull/42",
        },
        "preamble": {
            "title": "fix(foo): bar baz",
            "author": "alice", "base_ref": "main", "head_ref": "feat/x",
            "head_short": "abc123", "is_draft": False, "mergeable": True,
            "self_authored": False, "ai_summary": "",
            "ci": {"passing": 3, "failing": 0, "skipped": 1, "failing_names": []},
            "existing_threads_authors": [], "existing_threads_open": 0,
        },
        "rubric_source": "default",
        "skipped": {"generated": [], "no_risk": []},
        "chunks": [],
        "cursor": {"phase": "main", "queue": []},
        "flagged_queue": [],
        "history": [],
        "draft_review": {"verdict": None, "body": None},
    }
    s.update(overrides)
    return s


def make_chunk(cid, file="src/x.py", rating="low", **k):
    c = {
        "id": cid, "file": file,
        "hunk_header": "@@ -1,3 +1,5 @@",
        "old_range": [1, 3], "new_range": [1, 5],
        "members": [{
            "old_range": [1, 3], "new_range": [1, 5],
            "hunk_header": "@@ -1,3 +1,5 @@",
        }],
        "diff": "@@ -1,3 +1,5 @@\n line1\n+added1\n+added2\n line2\n line3\n",
        "rating": rating,
        "ai_notes": [],
        "existing_threads": [],
        "status": "pending",
        "comments": [],
    }
    c.update(k)
    return c
