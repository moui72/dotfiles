#!/usr/bin/env python3
"""Parse a unified diff into a JSON array of hunks for the PR-review skill."""

import argparse
import json
import re
import sys


HUNK_HEADER_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$"
)


def warn(msg):
    print(f"parse-diff.py: warning: {msg}", file=sys.stderr)


def parse_git_diff_paths(line):
    """Extract (old, new) paths from a `diff --git a/<old> b/<new>` line.

    Returns (None, None) for ambiguous cases (e.g. paths containing " b/");
    caller should fall back to --- / +++ lines.
    """
    rest = line[len("diff --git "):]
    if rest.startswith("a/"):
        idx = rest.find(" b/")
        if idx != -1:
            old = rest[2:idx]
            new = rest[idx + 3:].rstrip("\n")
            return old, new
    return None, None


def extract_path_from_marker(line, prefix):
    """Extract path from `--- a/<path>` or `+++ b/<path>` line."""
    s = line[len(prefix):].rstrip("\n")
    if s == "/dev/null":
        return None
    if s.startswith("a/") or s.startswith("b/"):
        s = s[2:]
    # Strip optional trailing tab + timestamp
    tab_idx = s.find("\t")
    if tab_idx != -1:
        s = s[:tab_idx]
    return s


def parse_diff(text):
    lines = text.splitlines()
    chunks = []
    chunk_counter = 0

    i = 0
    n = len(lines)

    # Per-file state
    cur_old_path = None
    cur_new_path = None
    is_binary = False

    # Per-hunk state
    in_hunk = False
    hunk_header_line = None
    hunk_body = []
    hunk_old_start = 0
    hunk_old_count = 0
    hunk_new_start = 0
    hunk_new_count = 0
    hunk_context = ""

    def finalize_hunk():
        nonlocal in_hunk, hunk_header_line, hunk_body, chunk_counter
        if not in_hunk:
            return
        # Determine file path
        if cur_new_path is not None:
            file_path = cur_new_path
        elif cur_old_path is not None:
            file_path = cur_old_path
        else:
            warn("hunk encountered with no known file path; skipping")
            in_hunk = False
            hunk_body = []
            return

        chunk_counter += 1
        # Per spec: if count omitted, treat as 1; if count == 0, use [X, X].
        if hunk_old_count == 0:
            old_range = [hunk_old_start, hunk_old_start]
        else:
            old_range = [hunk_old_start, hunk_old_start + hunk_old_count - 1]
        if hunk_new_count == 0:
            new_range = [hunk_new_start, hunk_new_start]
        else:
            new_range = [hunk_new_start, hunk_new_start + hunk_new_count - 1]

        diff_text = "\n".join([hunk_header_line] + hunk_body)
        chunk = {
            "id": f"c{chunk_counter}",
            "file": file_path,
            "hunk_header": hunk_header_line,
            "old_range": old_range,
            "new_range": new_range,
            "context": hunk_context.strip(),
            "diff": diff_text,
        }
        chunks.append(chunk)
        in_hunk = False
        hunk_body = []

    while i < n:
        line = lines[i]

        if line.startswith("diff --git "):
            finalize_hunk()
            cur_old_path, cur_new_path = parse_git_diff_paths(line)
            is_binary = False
            i += 1
            continue

        if line.startswith("Binary files ") and line.endswith("differ"):
            finalize_hunk()
            is_binary = True
            i += 1
            continue

        if is_binary:
            # Skip lines until next diff --git
            i += 1
            continue

        if line.startswith("--- "):
            finalize_hunk()
            p = extract_path_from_marker(line, "--- ")
            if p is not None:
                cur_old_path = p
            i += 1
            continue

        if line.startswith("+++ "):
            finalize_hunk()
            p = extract_path_from_marker(line, "+++ ")
            if p is not None:
                cur_new_path = p
            i += 1
            continue

        if (
            line.startswith("index ")
            or line.startswith("similarity ")
            or line.startswith("dissimilarity ")
            or line.startswith("rename ")
            or line.startswith("copy ")
            or line.startswith("new file mode")
            or line.startswith("deleted file mode")
            or line.startswith("old mode")
            or line.startswith("new mode")
            or line.startswith("GIT binary patch")
        ):
            i += 1
            continue

        m = HUNK_HEADER_RE.match(line)
        if m:
            finalize_hunk()
            hunk_old_start = int(m.group(1))
            hunk_old_count = int(m.group(2)) if m.group(2) is not None else 1
            hunk_new_start = int(m.group(3))
            hunk_new_count = int(m.group(4)) if m.group(4) is not None else 1
            hunk_context = m.group(5) or ""
            hunk_header_line = line
            hunk_body = []
            in_hunk = True
            i += 1
            continue

        if in_hunk:
            if line.startswith(("+", "-", " ", "\\")):
                hunk_body.append(line)
                i += 1
                continue
            else:
                # Unexpected line inside hunk — end the hunk and reprocess.
                finalize_hunk()
                continue

        # Unknown line outside a hunk — skip silently if blank, else warn.
        if line.strip() == "":
            i += 1
            continue
        warn(f"skipping unrecognized line: {line!r}")
        i += 1

    finalize_hunk()
    return chunks


def _singleton_group(ch):
    """Wrap a single hunk in a group structure with a `members` array."""
    return {
        "id": ch["id"],
        "file": ch["file"],
        "hunk_header": ch["hunk_header"],
        "old_range": list(ch["old_range"]),
        "new_range": list(ch["new_range"]),
        "context": ch.get("context", ""),
        "diff": ch["diff"],
        "members": [{
            "hunk_header": ch["hunk_header"],
            "old_range": list(ch["old_range"]),
            "new_range": list(ch["new_range"]),
        }],
    }


def group_chunks(chunks, gap):
    """Merge adjacent hunks in the same file when separated by <= `gap`
    unchanged new-file lines. Returns groups; each group has a `members` array
    listing the original hunk boundaries. ID and hunk_header carry over from
    the first member. `diff` is the literal concatenation of member diffs
    (each retains its own `@@ ... @@` header, so bat renders them naturally).

    With `gap <= 0`, every chunk becomes a one-member group (no merging).
    """
    if not chunks:
        return []
    groups = [_singleton_group(chunks[0])]
    if gap <= 0:
        for ch in chunks[1:]:
            groups.append(_singleton_group(ch))
        return groups
    for ch in chunks[1:]:
        cur = groups[-1]
        same_file = ch["file"] == cur["file"]
        prev_end = cur["new_range"][1]
        this_start = ch["new_range"][0]
        new_gap = max(0, this_start - prev_end - 1)
        if same_file and new_gap <= gap:
            cur["diff"] = cur["diff"] + "\n" + ch["diff"]
            cur["new_range"][1] = ch["new_range"][1]
            cur["old_range"][1] = ch["old_range"][1]
            cur["members"].append({
                "hunk_header": ch["hunk_header"],
                "old_range": list(ch["old_range"]),
                "new_range": list(ch["new_range"]),
            })
        else:
            groups.append(_singleton_group(ch))
    return groups


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="Path to diff file, or '-' for stdin")
    ap.add_argument(
        "--group-gap",
        type=int,
        default=20,
        help=(
            "Merge adjacent hunks in the same file when separated by <= N "
            "unchanged new-file lines. 0 disables grouping. Default: 20."
        ),
    )
    args = ap.parse_args()

    if args.path == "-":
        text = sys.stdin.read()
    else:
        with open(args.path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

    chunks = parse_diff(text)
    groups = group_chunks(chunks, args.group_gap)
    print(json.dumps(groups, indent=2, sort_keys=False))


if __name__ == "__main__":
    main()
