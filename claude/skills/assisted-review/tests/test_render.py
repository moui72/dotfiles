"""Smoke tests for _render.py. Verifies real ESC bytes and key content
strings appear; does not pin exact layout."""

import re
import unittest

from conftest import make_state, make_chunk

import _render

ESC = "\x1b"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


class TestPreamble(unittest.TestCase):
    def test_contains_pr_title_author_url(self):
        s = make_state()
        out = _render.render_preamble(s)
        plain = strip_ansi(out)
        self.assertIn("acme/widget#42", plain)
        self.assertIn("@alice", plain)
        self.assertIn("fix(foo): bar baz", plain)
        self.assertIn("https://github.com/acme/widget/pull/42", plain)

    def test_emits_real_esc_bytes(self):
        s = make_state()
        out = _render.render_preamble(s)
        self.assertIn(ESC, out)

    def test_draft_warning_when_draft(self):
        s = make_state()
        s["preamble"]["is_draft"] = True
        out = strip_ansi(_render.render_preamble(s))
        self.assertIn("draft PR", out)

    def test_failing_ci_warns_not_mergeable(self):
        s = make_state()
        s["preamble"]["ci"]["failing"] = 2
        s["preamble"]["ci"]["failing_names"] = ["lint", "test"]
        out = strip_ansi(_render.render_preamble(s))
        self.assertIn("not currently mergeable", out)
        self.assertIn("2 failing", out)


class TestCard(unittest.TestCase):
    def test_contains_file_and_rating(self):
        s = make_state(chunks=[make_chunk("c1", file="src/foo.py", rating="medium")])
        s["cursor"]["queue"] = ["c1"]
        out = strip_ansi(_render.render_card(s, "c1"))
        self.assertIn("src/foo.py", out)
        self.assertIn("medium", out)
        self.assertIn("Chunk 1 of 1", out)

    def test_last_in_queue_drops_ask_ai(self):
        s = make_state(chunks=[make_chunk("c1")])
        s["cursor"]["queue"] = ["c1"]
        out = strip_ansi(_render.render_card(s, "c1"))
        self.assertNotIn("ask AI", out)
        self.assertIn("flag", out)

    def test_flagged_phase_drops_flag(self):
        s = make_state(chunks=[make_chunk("c1"), make_chunk("c2")])
        s["cursor"]["queue"] = ["c1", "c2"]
        s["cursor"]["phase"] = "flagged"
        out = strip_ansi(_render.render_card(s, "c1"))
        # "flag" only appears as the action label, which should be gone
        # (other words containing "flag" aren't in the menu)
        self.assertNotIn("[5]", out)

    def test_drafted_comment_hint(self):
        chunk = make_chunk("c1")
        chunk["comments"] = [{"side": "RIGHT", "start_line": None, "end_line": 5,
                              "body": "x", "in_reply_to": None}]
        s = make_state(chunks=[chunk])
        s["cursor"]["queue"] = ["c1"]
        out = strip_ansi(_render.render_card(s, "c1"))
        self.assertIn("drafted comment exists", out)

    def test_ai_notes_render_kinds(self):
        chunk = make_chunk("c1")
        chunk["ai_notes"] = [
            {"kind": "initial", "body": "INIT_NOTE"},
            {"kind": "investigation", "body": "INV_NOTE", "prompt": "why X?"},
            {"kind": "context", "body": "CTX_NOTE"},
        ]
        s = make_state(chunks=[chunk])
        s["cursor"]["queue"] = ["c1"]
        out = strip_ansi(_render.render_card(s, "c1"))
        self.assertIn("INIT_NOTE", out)
        self.assertIn("INV_NOTE", out)
        self.assertIn("CTX_NOTE", out)
        self.assertIn("why X?", out)


class TestEndOfReview(unittest.TestCase):
    def test_lists_drafts(self):
        chunk = make_chunk("c1", file="src/a.py")
        chunk["comments"] = [{
            "side": "RIGHT", "start_line": None, "end_line": 5,
            "body": "WELL ACTUALLY", "in_reply_to": None,
        }]
        s = make_state(chunks=[chunk])
        out = strip_ansi(_render.render_end_of_review(s))
        self.assertIn("1 chunks reviewed", out)
        self.assertIn("src/a.py:5", out)
        self.assertIn("WELL ACTUALLY", out)


class TestPrompts(unittest.TestCase):
    def test_verdict_default_shows_all_three(self):
        s = make_state()
        out = strip_ansi(_render.render_prompt(s, "verdict", []))
        self.assertIn("approve", out)
        self.assertIn("comment", out)
        self.assertIn("request changes", out)

    def test_verdict_self_authored_hides_approve(self):
        s = make_state()
        s["preamble"]["self_authored"] = True
        out = strip_ansi(_render.render_prompt(s, "verdict", []))
        self.assertNotIn("approve", out)
        self.assertIn("comment", out)

    def test_verdict_invalid(self):
        s = make_state()
        out = strip_ansi(_render.render_prompt(s, "verdict-invalid", []))
        self.assertIn("Unrecognized", out)

    def test_final_confirm_includes_url_and_verdict(self):
        s = make_state()
        s["draft_review"]["verdict"] = "APPROVE"
        s["draft_review"]["body"] = "lgtm"
        out = strip_ansi(_render.render_prompt(s, "final-confirm", []))
        self.assertIn("https://github.com/acme/widget/pull/42", out)
        self.assertIn("APPROVE", out)
        self.assertIn("lgtm", out)

    def test_anchor_error(self):
        s = make_state()
        out = strip_ansi(_render.render_prompt(s, "anchor-error", ["99"]))
        self.assertIn("99", out)

    def test_unknown_surface(self):
        s = make_state()
        out = strip_ansi(_render.render_prompt(s, "nonexistent", []))
        self.assertIn("unknown", out.lower())


class TestDrafts(unittest.TestCase):
    def test_empty_state(self):
        s = make_state(chunks=[make_chunk("c1")])
        out = strip_ansi(_render.render_drafts(s))
        self.assertIn("no comments drafted", out)

    def test_sorted_by_file_then_line(self):
        c1 = make_chunk("c1", file="b.py")
        c1["comments"] = [{"side": "RIGHT", "start_line": None, "end_line": 10,
                           "body": "B10", "in_reply_to": None}]
        c2 = make_chunk("c2", file="a.py")
        c2["comments"] = [{"side": "RIGHT", "start_line": None, "end_line": 1,
                           "body": "A1", "in_reply_to": None}]
        s = make_state(chunks=[c1, c2])
        out = strip_ansi(_render.render_drafts(s))
        # a.py should appear before b.py
        self.assertLess(out.index("a.py"), out.index("b.py"))


if __name__ == "__main__":
    unittest.main()
