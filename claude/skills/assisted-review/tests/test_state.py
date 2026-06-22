"""Unit tests for _state.py action functions and anchor parsing."""

import unittest

from conftest import make_state, make_chunk

import _state


class TestDismiss(unittest.TestCase):
    def test_removes_from_queue_and_marks_status(self):
        s = make_state(chunks=[make_chunk("c1"), make_chunk("c2")])
        s["cursor"]["queue"] = ["c1", "c2"]
        _state.action_dismiss(s, "c1")
        self.assertEqual(s["cursor"]["queue"], ["c2"])
        self.assertEqual(s["chunks"][0]["status"], "dismissed")
        self.assertEqual(s["history"][-1]["op"], "dismiss")


class TestFlag(unittest.TestCase):
    def test_moves_to_flagged_queue(self):
        s = make_state(chunks=[make_chunk("c1")])
        s["cursor"]["queue"] = ["c1"]
        _state.action_flag(s, "c1")
        self.assertEqual(s["cursor"]["queue"], [])
        self.assertEqual(s["flagged_queue"], ["c1"])
        self.assertEqual(s["chunks"][0]["status"], "flagged")


class TestDefer(unittest.TestCase):
    def test_moves_to_bottom(self):
        s = make_state(chunks=[make_chunk("c1"), make_chunk("c2"), make_chunk("c3")])
        s["cursor"]["queue"] = ["c1", "c2", "c3"]
        _state.action_defer(s, "c1")
        self.assertEqual(s["cursor"]["queue"], ["c2", "c3", "c1"])


class TestComment(unittest.TestCase):
    def test_drafts_and_dismisses(self):
        s = make_state(chunks=[make_chunk("c1")])
        s["cursor"]["queue"] = ["c1"]
        _state.action_comment(s, "c1", None, "nit: rename")
        self.assertEqual(s["cursor"]["queue"], [])
        cm = s["chunks"][0]["comments"][0]
        self.assertEqual(cm["body"], "nit: rename")
        self.assertEqual(cm["side"], "RIGHT")
        self.assertEqual(cm["end_line"], 5)  # last new-file line
        self.assertIsNone(cm["start_line"])

    def test_reply_records_in_reply_to(self):
        s = make_state(chunks=[make_chunk("c1")])
        s["cursor"]["queue"] = ["c1"]
        _state.action_comment(s, "c1", None, "ack", in_reply_to="t99")
        self.assertEqual(s["chunks"][0]["comments"][0]["in_reply_to"], "t99")
        self.assertEqual(s["history"][-1]["op"], "reply")


class TestAnchorParsing(unittest.TestCase):
    def setUp(self):
        self.chunk = make_chunk("c1")  # old [1,3], new [1,5]

    def test_whole_hunk_defaults(self):
        side, start, end = _state.parse_anchor("", self.chunk)
        self.assertEqual((side, start, end), ("RIGHT", None, 5))

    def test_single_line_right(self):
        side, start, end = _state.parse_anchor("L3", self.chunk)
        self.assertEqual((side, start, end), ("RIGHT", None, 3))

    def test_range_right(self):
        side, start, end = _state.parse_anchor("L2-4", self.chunk)
        self.assertEqual((side, start, end), ("RIGHT", 2, 4))

    def test_single_line_left(self):
        side, start, end = _state.parse_anchor("L-2", self.chunk)
        self.assertEqual((side, start, end), ("LEFT", None, 2))

    def test_out_of_range_raises(self):
        with self.assertRaises(SystemExit):
            _state.parse_anchor("L99", self.chunk)

    def test_malformed_raises(self):
        with self.assertRaises(SystemExit):
            _state.parse_anchor("not-a-line", self.chunk)


class TestBack(unittest.TestCase):
    def test_restores_dismiss(self):
        s = make_state(chunks=[make_chunk("c1"), make_chunk("c2")])
        s["cursor"]["queue"] = ["c1", "c2"]
        _state.action_dismiss(s, "c1")
        op = _state.action_back(s)
        self.assertEqual(op, "dismiss")
        self.assertEqual(s["cursor"]["queue"][0], "c1")
        self.assertEqual(s["chunks"][0]["status"], "pending")

    def test_restores_comment_keeps_draft(self):
        s = make_state(chunks=[make_chunk("c1")])
        s["cursor"]["queue"] = ["c1"]
        _state.action_comment(s, "c1", None, "draft")
        _state.action_back(s)
        # Comment draft is preserved, chunk back in queue
        self.assertEqual(s["cursor"]["queue"][0], "c1")
        self.assertEqual(len(s["chunks"][0]["comments"]), 1)

    def test_noop_on_empty_history(self):
        s = make_state(chunks=[make_chunk("c1")])
        s["cursor"]["queue"] = ["c1"]
        self.assertIsNone(_state.action_back(s))


class TestPromoteToFlagged(unittest.TestCase):
    def test_promotes_when_main_empty_and_flagged_present(self):
        s = make_state(chunks=[make_chunk("c1")])
        s["cursor"]["queue"] = []
        s["flagged_queue"] = ["c1"]
        self.assertTrue(_state.promote_to_flagged_phase(s))
        self.assertEqual(s["cursor"]["phase"], "flagged")
        self.assertEqual(s["cursor"]["queue"], ["c1"])

    def test_noop_when_already_flagged_phase(self):
        s = make_state()
        s["cursor"]["phase"] = "flagged"
        self.assertFalse(_state.promote_to_flagged_phase(s))

    def test_noop_when_main_has_chunks(self):
        s = make_state()
        s["cursor"]["queue"] = ["c1"]
        s["flagged_queue"] = ["c2"]
        self.assertFalse(_state.promote_to_flagged_phase(s))


class TestAddNote(unittest.TestCase):
    def test_initial_dedupes(self):
        s = make_state(chunks=[make_chunk("c1")])
        _state.action_add_note(s, "c1", "initial", "first")
        _state.action_add_note(s, "c1", "initial", "second")
        notes = s["chunks"][0]["ai_notes"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["body"], "first")

    def test_investigation_appends(self):
        s = make_state(chunks=[make_chunk("c1")])
        _state.action_add_note(s, "c1", "initial", "init")
        _state.action_add_note(s, "c1", "investigation", "found X", prompt="check Y")
        notes = s["chunks"][0]["ai_notes"]
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[1]["prompt"], "check Y")


class TestVerdict(unittest.TestCase):
    def test_valid(self):
        s = make_state()
        _state.action_set_verdict(s, "APPROVE")
        self.assertEqual(s["draft_review"]["verdict"], "APPROVE")

    def test_invalid_raises(self):
        s = make_state()
        with self.assertRaises(SystemExit):
            _state.action_set_verdict(s, "MAYBE")


class TestStats(unittest.TestCase):
    def test_counts(self):
        s = make_state(chunks=[make_chunk("c1"), make_chunk("c2")])
        s["cursor"]["queue"] = ["c1", "c2"]
        _state.action_comment(s, "c1", None, "x")
        _state.action_comment(s, "c2", None, "y", in_reply_to="t1")
        stats = _state.stats(s)
        self.assertEqual(stats["reviewed"], 2)
        self.assertEqual(stats["drafted"], 2)
        self.assertEqual(stats["drafted_chunks"], 2)
        self.assertEqual(stats["replies"], 1)


if __name__ == "__main__":
    unittest.main()
