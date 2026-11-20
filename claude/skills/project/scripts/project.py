#!/usr/bin/env python3
"""Project notes, optionally synced to an issue tracker. The note is the source of truth.

Commands:
  profile                    show this machine's profile (notes dir, tracker, config file)
  list                       one line per project note
  status NAME                note summary + staleness
  init NAME [--epic K --owns QUERY] [--alias A ...]
                             create a note (seeded from the tracker when there is one; never overwrites)
  sync [NAME]                dry-run plan: outbound, planned creates, comments to
                             post, inbound, conflicts
  sync NAME --apply [--only K1,K2] [--no-commit]
                             execute the plan; writes to the tracker. Stops at the first
                             failure and never advances last_synced after one.
  audit NAME [--since D] [--stamp]
                             read-only: compare the note to merged/open PRs and releases in
                             its `repos:`; --stamp records last_audited after the note is updated
  accept|reject NAME KEY     act on a line under ## Proposed status changes
  resolve NAME KEY --keep tracker|local
                             settle a sync conflict
  kick                       run the profile's `kick` command

Note sections the script reads: the managed story table, `## Planned`
(`- [ ] summary` = a story to create) and `## Comments to post`
(`- KEY: text`). Each tracker write is persisted to the note before the next one.
The tracker and notes dir come from the machine's profile (skill_profile.py).
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skill_profile  # noqa: E402
from backends import load_backend  # noqa: E402

PROFILE = skill_profile.load()
PROJECTS = PROFILE["notes_dir"]
DONE = tuple(PROFILE["done_statuses"])
IN_FLIGHT = tuple(PROFILE["in_flight_statuses"])
BEGIN, END = "<!-- jira:stories -->", "<!-- /jira:stories -->"  # marker names kept for existing notes
KEY_RE = r"[A-Z][A-Z0-9]*-\d+"


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def tracker():
    return load_backend(profile=PROFILE)


# ---------- note format (the script owns it) ----------

def parse_note(path):
    text = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        sys.exit(f"{path}: no frontmatter")
    meta = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        meta[k.strip()] = v
    return meta, m.group(2)


def read_table(body):
    """Managed table -> {key: {"status", "synced", "summary", "assignee"}}."""
    block = body.split(BEGIN)[1].split(END)[0] if BEGIN in body else ""
    rows = {}
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) in (4, 5) and re.match(rf"^{KEY_RE}$", cells[0]):
            rows[cells[0]] = {"status": cells[1], "synced": cells[2], "summary": cells[3],
                              "assignee": cells[4] if len(cells) == 5 else None}
    return rows


def render_table(rows):
    out = ["| key | status | synced | summary | assignee |", "|---|---|---|---|---|"]
    for key, r in rows.items():
        out.append(f"| {key} | {r['status']} | {r['synced']} | {r['summary']} | {r.get('assignee') or '?'} |")
    return "\n".join(out)


def section_lines(body, name, pattern):
    m = re.search(rf"^## {re.escape(name)}\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    return [x.groups() if len(x.groups()) > 1 else x.group(1) for x in re.finditer(pattern, m.group(1), re.M)] if m else []


def read_planned(body):
    return [s.strip() for s in section_lines(body=body, name="Planned", pattern=r"^- \[ \] (.+)$")]


def read_comments_to_post(body):
    return [(k, t.strip()) for k, t in section_lines(body=body, name="Comments to post", pattern=rf"^- ({KEY_RE}): (.+)$")]


def set_row(text, key, **cols):
    rows = read_table(text)
    rows.setdefault(key, {"status": "", "synced": "", "summary": "", "assignee": None}).update(cols)
    head, rest = text.split(BEGIN)
    return head + BEGIN + "\n" + render_table(rows) + "\n" + END + rest.split(END)[1]


def edit_section(text, name, fn):
    pat = rf"^## {re.escape(name)}\n(.*?)(?=^## |\Z)"
    if not re.search(pat, text, re.S | re.M):
        text = text.rstrip("\n") + f"\n\n## {name}\n"
    m = re.search(pat, text, re.S | re.M)
    lines = [l for l in m.group(1).strip("\n").splitlines()]
    new = fn(lines)
    return text[: m.start(1)] + ("\n".join(new) + "\n\n" if new else "\n") + text[m.end(1):]


def add_line(text, name, line, top=False):
    return edit_section(text=text, name=name, fn=lambda ls: [line, *ls] if top else [*ls, line])


def drop_line(text, name, line):
    return edit_section(text=text, name=name, fn=lambda ls: [l for l in ls if l.strip() != line.strip()])


def set_meta(text, key, value):
    return re.sub(rf"^{key}: .*$", f"{key}: {value}", text, count=1, flags=re.M)


def all_notes():
    return sorted(PROJECTS.glob("*.md")) if PROJECTS.exists() else []


def resolve(name):
    want = name.strip().lower()
    hits = []
    for p in all_notes():
        meta, _ = parse_note(p)
        names = [meta.get("title", ""), p.stem, meta.get("jira_epic", "")] + list(meta.get("aliases", []))
        if want in [n.lower() for n in names if n]:
            return p
        if any(want in n.lower() for n in names if n):
            hits.append(p)
    if len(hits) == 1:
        return hits[0]
    sys.exit(f"{'ambiguous' if hits else 'no project matches'} {name!r}: {[h.stem for h in hits] or [p.stem for p in all_notes()]}")


# ---------- plan ----------

def make_plan(tr, me, path):
    meta, body = parse_note(path)
    since = datetime.fromisoformat(meta["last_synced"])
    table = read_table(body)
    live = tr.owned(meta=meta)
    epic = meta.get("jira_epic")
    plan = {"meta": meta, "live": live, "transitions": [], "creates": [], "comments": [],
            "pull_status": [], "new_stories": [], "questions": [], "fyi": [], "conflicts": [], "blocked": []}

    for key, row in table.items():
        j = live.get(key)
        if not j:
            plan["fyi"].append(f"{key}: no longer matched by `owns` (moved or deleted in {tr.name})")
            continue
        js = j["status"]
        local_changed, remote_changed = row["status"] != row["synced"], js != row["synced"]
        if local_changed and remote_changed and row["status"] != js:
            plan["conflicts"].append(f"{key}: local {row['status']!r}, {tr.name} {js!r}, last synced {row['synced']!r}")
        elif local_changed and not remote_changed:
            via = tr.transition_via(key=key, to=row["status"])
            if via:
                plan["transitions"].append({"key": key, "frm": row["synced"], "to": row["status"], "via": via})
            else:
                plan["blocked"].append(f"{key}: no transition to {row['status']!r} from {row['synced']!r}")
        elif remote_changed:
            plan["pull_status"].append({"key": key, "status": js, "frm": row["synced"]})
        if row.get("assignee") not in (None, "?") and row["assignee"] != j["assignee"]:
            plan["fyi"].append(f"{key}: assignee changed {row['assignee']} -> {j['assignee']}")

    for key, j in live.items():
        if key not in table and key != epic and j["status"] not in DONE:
            plan["new_stories"].append({"key": key, "status": j["status"], "summary": j["summary"].replace("|", "/"),
                                        "reporter": j["reporter"], "assignee": j["assignee"]})
    # Scan every owned issue, closed ones included, but only those touched since the last
    # sync: a new comment bumps `updated`, so this skips most comment fetches.
    for key, j in live.items():
        if j["updated"] <= since:
            continue
        for day, who, text in tr.comments_since(key=key, since=since, me=me):
            plan["questions"].append({"key": key, "day": day, "who": who, "text": text})

    existing = {i["summary"].strip().lower() for i in live.values()}
    for s in read_planned(body):
        if s.lower() in existing:
            plan["blocked"].append(f"planned {s!r}: a story with this exact summary already exists under the epic")
        else:
            plan["creates"].append(s)
    for key, text in read_comments_to_post(body):
        if key in live:
            plan["comments"].append({"key": key, "text": text})
        else:
            plan["blocked"].append(f"comment on {key}: not under this project's `owns`")
    return plan


def print_plan(plan, tr):
    meta = plan["meta"]
    print(f"== {meta['title']}  (tracked {len(read_table(parse_note(Path(plan['path']))[1]))}, live {len(plan['live'])}, since {meta['last_synced'][:16]})")
    sections = [
        ("outbound transitions", [f"{t['key']}: {t['frm']} -> {t['to']} via {t['via']!r}" for t in plan["transitions"]]),
        ("planned creates", [f"CREATE {meta.get('jira_project', '')} Story under {meta.get('jira_epic', '')}: {s}" for s in plan["creates"]]),
        ("comments to post", [f"{c['key']}: {c['text']}" for c in plan["comments"]]),
        ("inbound", [f"{p['key']}: {tr.name} moved {p['frm']} -> {p['status']}" for p in plan["pull_status"]]
         + [f"{n['key']}: new under `owns` ({n['status']}, reporter {n['reporter']}): {n['summary']}" for n in plan["new_stories"]]
         + [f"{q['key']}: comment from {q['who']} on {q['day']}: {q['text']}" for q in plan["questions"]]
         + plan["fyi"]),
        ("BLOCKED", plan["blocked"]),
        ("CONFLICTS", plan["conflicts"]),
    ]
    for title, items in sections:
        print(f"  {title}: {'none' if not items else ''}")
        for i in items:
            print(f"    - {i}")


# ---------- apply ----------

def apply_plan(tr, path, plan, only, commit, pull_only=False, push=True):
    meta = plan["meta"]
    my_name = tr.my_name()
    keys = set(only) if only else None
    done = []
    text = lambda: path.read_text()  # noqa: E731

    def save(t):
        path.write_text(t)

    for t in ([] if pull_only else plan["transitions"]):
        if keys and t["key"] not in keys:
            continue
        tr.transition(key=t["key"], to=t["to"])
        save(set_row(text(), t["key"], synced=t["to"]))
        save(add_line(text=text(), name="Log", line=f"- {now_iso()[:10]}: {t['key']} {t['frm']} -> {t['to']} (pushed to {tr.name})"))
        done.append(f"transitioned {t['key']} -> {t['to']}")

    for c in ([] if pull_only else plan["comments"]):
        if keys and c["key"] not in keys:
            continue
        tr.comment(key=c["key"], text=c["text"])
        save(drop_line(text=text(), name="Comments to post", line=f"- {c['key']}: {c['text']}"))
        save(add_line(text=text(), name="Log", line=f"- {now_iso()[:10]}: commented on {c['key']}"))
        done.append(f"commented on {c['key']}")

    if keys:  # partial apply: outbound for named keys only
        print("applied (partial, no creates/inbound, last_synced unchanged):", *done, sep="\n  - ")
        return done

    for s in ([] if pull_only else plan["creates"]):
        key = tr.create(meta=meta, summary=s)
        save(set_row(drop_line(text=text(), name="Planned", line=f"- [ ] {s}"), key, status="To Do", synced="To Do",
                     summary=s.replace("|", "/"), assignee=my_name))
        save(add_line(text=text(), name="Log", line=f"- {now_iso()[:10]}: created {key}: {s}"))
        done.append(f"created {key}: {s}")

    t = text()
    for p in plan["pull_status"]:
        t = set_row(t, p["key"], status=p["status"], synced=p["status"])
        done.append(f"pulled {p['key']} -> {p['status']}")
    for n in plan["new_stories"]:
        t = set_row(t, n["key"], status=n["status"], synced=n["status"], summary=n["summary"], assignee=n["assignee"])
        done.append(f"adopted {n['key']}")
    for q in plan["questions"]:
        t = add_line(text=t, name="Questions for me", line=f"- [ ] {q['day']} {q['who']} on [{q['key']}]({tr.url(key=q['key'])}): {q['text']}")
        done.append(f"recorded comment from {q['who']} on {q['key']}")
    for key in read_table(t):
        if key in plan["live"]:
            t = set_row(t, key, assignee=plan["live"][key]["assignee"])
    for f in plan["fyi"]:
        t = add_line(text=t, name="Log", line=f"- {now_iso()[:10]}: {f}", top=False)
    if pull_only and not done and not plan["fyi"]:
        print(f"pulled (no {tr.name} writes):\n  - nothing to pull; note unchanged")
        return done
    save(set_meta(text=t, key="last_synced", value=now_iso()))

    if commit and done:
        commit_note(path=path, message=f"project: sync {meta['title']} ({len(done)} changes)", push=push)
    print(f"pulled (no {tr.name} writes):" if pull_only else "applied:", *(done or ["nothing to pull"]), sep="\n  - ")
    return done


def commit_note(path, message, push=True):
    """Commit only this note, if the notes dir is in a git repo. push=False (unattended runs) leaves the commit for the next interactive push."""
    git = ["git", "-C", str(path.parent)]
    run = lambda *a: subprocess.run([*git, *a], capture_output=True, text=True)  # noqa: E731
    if run("rev-parse", "--is-inside-work-tree").returncode:
        return
    run("add", "--", str(path))
    if run("diff", "--cached", "--quiet", "--", str(path)).returncode == 0:
        return
    r = run("commit", "-m", message, "--", str(path))
    if r.returncode:
        print("commit failed:", r.stderr.strip())
        return
    if not push:
        return
    if run("push").returncode:
        run("pull", "--rebase")
        r = run("push")
        print("pushed after rebase" if r.returncode == 0 else f"PUSH FAILED: {r.stderr.strip()}")


# ---------- audit: note vs code ----------

def gh_json(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode:
        return None
    return json.loads(r.stdout or "null")


def pr_keys(pr, prefix):
    first = next((l for l in (pr.get("body") or "").splitlines() if l.strip()), "")  # the story link line
    text = f"{pr['title']} {pr.get('headRefName', '')} {first}"
    return sorted(set(re.findall(rf"\b{prefix}-\d+\b", text)))


def key_prefix(meta, table):
    if meta.get("jira_project"):
        return meta["jira_project"]
    prefixes = {k.split("-")[0] for k in table}
    return prefixes.pop() if len(prefixes) == 1 else None


def cmd_audit(args):
    path = resolve(args.name)
    meta, body = parse_note(path)
    if args.stamp:
        text = path.read_text()
        text = set_meta(text=text, key="last_audited", value=now_iso()) if re.search(r"^last_audited:", text, re.M) \
            else text.replace("\nlast_synced:", f"\nlast_audited: {now_iso()}\nlast_synced:", 1)
        path.write_text(text)
        print(f"stamped last_audited on {path.name}")
        return
    repos = meta.get("repos", [])
    since = args.since or (meta.get("last_audited") or meta["last_synced"])[:10]
    table = read_table(body)
    prefix = key_prefix(meta=meta, table=table)
    tr = tracker()
    if tr.syncs:
        live = tr.owned(meta=meta)
        summary_of = lambda k: live[k]["summary"]  # noqa: E731
        status_of = lambda k: table[k]["status"] if k in table else live[k]["status"]  # noqa: E731
    else:
        live = table
        summary_of = lambda k: table[k]["summary"]  # noqa: E731
        status_of = lambda k: table[k]["status"]  # noqa: E731
    print(f"== audit: {meta['title']}  (PRs merged since {since}; repos: {', '.join(repos) or 'none'})")
    if not repos:
        print("  no `repos:` in frontmatter; only the note-mention check runs")

    by_key = {}
    for repo in repos:
        short = repo.split("/")[-1]
        fields = "number,title,headRefName,body,author,updatedAt,isDraft,mergedAt"
        opened = gh_json("pr", "list", "-R", repo, "--state", "open", "--limit", "100", "--json", fields) or []
        merged = gh_json("pr", "list", "-R", repo, "--state", "merged", "--search", f"merged:>={since}",
                         "--limit", "200", "--json", fields) or []
        print(f"\n-- {repo}: {len(opened)} open, {len(merged)} merged since {since}")
        rel = gh_json("release", "list", "-R", repo, "--limit", "1", "--json", "tagName,publishedAt")
        if rel:
            print(f"   latest release {rel[0]['tagName']} ({rel[0]['publishedAt'][:10]})")
        tags = gh_json("api", f"repos/{repo}/tags?per_page=100") or []
        pkg = [t_["name"] for t_ in tags if "/" in t_["name"]][:3]
        if pkg:
            print(f"   latest component tags: {', '.join(pkg)}")
        if not prefix:
            continue
        for state, prs in (("open", opened), ("merged", merged)):
            for pr in prs:
                for k in pr_keys(pr=pr, prefix=prefix):
                    by_key.setdefault(k, []).append((short, pr["number"], state, pr["title"][:70]))
        for pr in opened:
            if not pr_keys(pr=pr, prefix=prefix):
                continue
            print(f"   open  {short}#{pr['number']}{' [draft]' if pr['isDraft'] else ''} {pr['title'][:80]} ({pr['author']['login']}, upd {pr['updatedAt'][:10]})")

    flags, quiet, openprs = [], [], []
    for k in sorted(live, key=lambda x: int(x.split("-")[1])):
        if k == meta.get("jira_epic") or status_of(k) in DONE:
            continue
        prs = by_key.get(k, [])
        if any(s == "merged" for _, _, s, _ in prs) and not any(s == "open" for _, _, s, _ in prs):
            flags.append(f"{k} [{status_of(k)}]: all PRs merged ({', '.join(f'{r}#{n}' for r, n, s, _ in prs)}): {summary_of(k)[:60]}")
        elif any(s == "open" for _, _, s, _ in prs):
            openprs.append(f"{k} [{status_of(k)}]: open {', '.join(f'{r}#{n}' for r, n, s, _ in prs if s == 'open')}")
        elif status_of(k) in IN_FLIGHT and not prs:
            quiet.append(f"{k} [{status_of(k)}]: in flight but no PR found: {summary_of(k)[:60]}")
    for title, items in (("OPEN STORIES WHOSE PRs ARE ALL MERGED (candidates for Done)", flags),
                         ("open stories with an open PR", openprs),
                         ("in-flight stories with no PR found", quiet)):
        print(f"\n{title}: {'none' if not items else ''}")
        for i in items:
            print(f"  - {i}")

    # PR references in the note whose state contradicts nearby "open" wording.
    # `owner/repo#N` always counts; a bare `repo#N` needs the profile's github_org.
    org = PROFILE["github_org"]
    print("\nNOTE PR REFERENCES:")
    seen = {}
    for line in body.splitlines():
        line = re.sub(r"\]\([^)]*\)", "]", line)  # drop markdown link targets so wording stays close to the reference
        for m in re.finditer(r"\b(?:([\w.-]+)/)?([a-z][\w.-]+)#(\d+)\b", line):
            owner, repo, num = m.group(1) or org, m.group(2), m.group(3)
            if not owner or (repo, num) in seen:
                continue
            v = gh_json("pr", "view", num, "-R", f"{owner}/{repo}", "--json", "state,mergedAt,title")
            if not v:
                continue
            seen[(repo, num)] = v["state"]
            win = line[max(0, m.start() - 60): m.end() + 60]  # wording near this reference only
            says_open = bool(re.search(r"\bopen\b", win, re.I)) and not re.search(r"\bopen(ed)? (PR )?(not|yet)|not open", win, re.I)
            says_merged = bool(re.search(r"\b(merged|released|deployed|done)\b", win, re.I))
            if v["state"] != "OPEN" and says_open:
                print(f"  {repo}#{num} is {v['state']} {(v.get('mergedAt') or '')[:10]}, but the note says open: ...{win.strip()}...")
            elif v["state"] == "OPEN" and says_merged and not says_open:
                print(f"  {repo}#{num} is still OPEN, but the note says merged/done: ...{win.strip()}...")
    print(f"  ({len(seen)} PR references checked)")
    print("\nNext: update the note's current state, set story statuses in the table, "
          + ("run `sync` for the tracker plan, " if tr.syncs else "")
          + "then `audit --stamp`.")


# ---------- commands ----------

PROPOSAL_RE = r"^- \[ \] ({key}): (.+?) -> (.+?): (.*)$"


def find_proposal(body, key):
    s = re.search(r"^## Proposed status changes\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    m = re.search(PROPOSAL_RE.format(key=re.escape(key)), s.group(1), re.M) if s else None
    if not m:
        sys.exit(f"no proposal for {key} under ## Proposed status changes")
    return m


def cmd_accept(args):
    """Accept a proposal: set the story's status cell to its target; the next `sync` pushes it."""
    path = resolve(args.name)
    t = path.read_text()
    m = find_proposal(body=parse_note(path)[1], key=args.key)
    target = m.group(3).strip()
    if args.key not in read_table(t):
        sys.exit(f"{args.key} isn't in the story table")
    t = set_row(t, args.key, status=target)
    t = drop_line(text=t, name="Proposed status changes", line=m.group(0))
    t = add_line(text=t, name="Log", line=f"- {now_iso()[:10]}: accepted proposal {args.key} -> {target}")
    path.write_text(t)
    print(f"{args.key} status cell -> {target!r}." + (f" Run `project sync {path.stem}` to see the tracker plan, then --apply."
                                                      if PROFILE["tracker"] != "none" else ""))


def cmd_reject(args):
    path = resolve(args.name)
    m = find_proposal(body=parse_note(path)[1], key=args.key)
    t = drop_line(text=path.read_text(), name="Proposed status changes", line=m.group(0))
    path.write_text(add_line(text=t, name="Log", line=f"- {now_iso()[:10]}: rejected proposal {args.key} -> {m.group(3).strip()}"))
    print(f"dropped the proposal for {args.key}")


def cmd_resolve(args):
    """Resolve a conflict: --keep tracker takes the tracker's status; --keep local pushes the note's on the next sync."""
    path = resolve(args.name)
    t = path.read_text()
    row = read_table(t).get(args.key) or sys.exit(f"{args.key} isn't in the story table")
    tr = tracker()
    js = tr.get(key=args.key)["status"]
    if args.keep in ("tracker", "jira"):
        t = set_row(t, args.key, status=js, synced=js)
        msg = f"took {tr.name}'s {js!r}"
    else:
        t = set_row(t, args.key, synced=js)
        msg = f"kept local {row['status']!r}; the next sync transitions {tr.name} from {js!r}"
    path.write_text(add_line(text=t, name="Log", line=f"- {now_iso()[:10]}: resolved conflict on {args.key}: {msg}"))
    print(f"{args.key}: {msg}")


def cmd_profile(args):
    print(f"profile file: {PROFILE['path'] or f'(none at {skill_profile.profile_path()}; defaults apply)'}")
    for k in ("notes_dir", "tracker", "github_org", "done_statuses", "in_flight_statuses", "instructions", "kick"):
        print(f"{k}: {PROFILE[k]}")


def cmd_kick(args):
    if not PROFILE["kick"]:
        sys.exit("no `kick` command in this machine's profile")
    sys.exit(subprocess.run(["bash", "-c", PROFILE["kick"]]).returncode)


def cmd_list(args):
    for p in all_notes():
        meta, _ = parse_note(p)
        print(f"{p.stem:30} {meta.get('status', '?'):16} next: {meta.get('next', '-')}")


def cmd_status(args):
    p = resolve(args.name)
    meta, body = parse_note(p)
    age = (datetime.now().astimezone() - datetime.fromisoformat(meta["last_synced"])).days
    if meta.get("repos"):
        la = meta.get("last_audited")
        aud = (datetime.now().astimezone() - datetime.fromisoformat(la)).days if la else None
        if aud is None or aud > int(meta.get("stale_days", 7)):
            print(f"** code audit {'never run' if aud is None else f'{aud}d old'}: run `audit {meta['title']}` **")
    print(p)
    print(f"status: {meta.get('status')} | next: {meta.get('next')} | last synced {age}d ago"
          + ("  ** STALE **" if PROFILE["tracker"] != "none" and age > int(meta.get("stale_days", 7)) else ""))
    print(body)


def cmd_init(args):
    tr = tracker()
    path = PROJECTS / f"{re.sub(r'[^a-z0-9]+', '-', args.name.lower()).strip('-')}.md"
    if path.exists():
        sys.exit(f"{path} exists; not overwriting")
    extra = tr.init_meta(args=args)
    aliases = ", ".join(([args.epic] if args.epic else []) + (args.alias or []))
    rows, status = {}, "active"
    if tr.syncs:
        meta = dict(line.split(": ", 1) for line in extra)
        status = tr.get(key=meta["jira_epic"])["status"]
        rows = {i["key"]: {"status": i["status"], "synced": i["status"], "summary": i["summary"].replace("|", "/"),
                           "assignee": i["assignee"]} for i in tr.open_owned(meta=meta)}
    now = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    head = [f"title: {args.name}", f"aliases: [{aliases}]", f"status: {status}", *extra,
            "next: ", "stale_days: 7", f"last_synced: {now}"]
    origin = f"from {tr.name} ({len(rows)} open stories)" if tr.syncs else "(no tracker)"
    path.write_text(
        "---\n" + "\n".join(head) + f"\n---\n# {args.name}\n\n"
        f"## Current state\n\n## Questions for me\n\n## Open stories\n{BEGIN}\n{render_table(rows)}\n{END}\n\n"
        f"## Planned\n\n## Comments to post\n\n## Log\n- {now[:10]}: note created {origin}\n"
    )
    print(f"created {path} {origin}")


LOCK_BUSY = 75  # EX_TEMPFAIL: the unattended job treats it as "skip this run"


def plan_json(plan, done):
    """The parts of a plan an upkeep dashboard reads (no raw tracker issues)."""
    keep = ("transitions", "creates", "comments", "pull_status", "new_stories", "questions", "fyi", "conflicts", "blocked")
    return {"title": plan["meta"]["title"], "path": plan["path"], "last_synced": plan["meta"].get("last_synced"),
            "applied": done, **{k: plan[k] for k in keep}}


class SyncLock:
    """Exclusive lock so two sessions can't apply a sync to the notes at the same moment."""

    def __enter__(self):
        import fcntl
        PROJECTS.mkdir(parents=True, exist_ok=True)
        self.fh = open(PROJECTS / ".sync.lock", "w")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fh.close()
            print("another session is applying a project sync right now; run the dry run again in a moment", file=sys.stderr)
            sys.exit(LOCK_BUSY)
        return self

    def __exit__(self, *exc):
        self.fh.close()


def cmd_sync(args):
    if args.apply and not args.name:
        sys.exit("--apply needs a project NAME (--pull may run across all projects)")
    if PROFILE["tracker"] == "none":
        sys.exit("tracker is 'none' in this machine's profile: the notes are the only record, nothing to sync")
    if args.json:  # the human-readable report goes to stderr; stdout carries only the JSON
        import contextlib
        with contextlib.redirect_stdout(sys.stderr):
            result = run_sync(args)
        print(json.dumps(result, indent=1))
    else:
        run_sync(args)


def run_sync(args):
    tr = tracker()
    me = tr.me()
    paths = [resolve(args.name)] if args.name else all_notes()
    claimed, out = set(), {"generated": now_iso(), "mode": "pull" if args.pull else "apply" if args.apply else "dry-run",
                           "projects": [], "unclaimed": None}
    for p in paths:
        plan = make_plan(tr=tr, me=me, path=p)
        plan["path"] = str(p)
        print_plan(plan=plan, tr=tr)
        claimed |= set(plan["live"]) | set(read_table(parse_note(p)[1]))
        done = []
        if args.apply or args.pull:
            if plan["conflicts"]:
                print("  (conflicting keys are left untouched; resolve them in the note)")
            with SyncLock():
                plan = make_plan(tr=tr, me=me, path=p)  # re-plan under the lock: another session may have just synced
                plan["path"] = str(p)
                done = apply_plan(tr=tr, path=p, plan=plan, only=[k for k in (args.only or "").split(",") if k],
                                  commit=not args.no_commit, pull_only=args.pull, push=not args.no_push)
        out["projects"].append(plan_json(plan=plan, done=done))
    if not args.name:
        for p in all_notes():
            claimed |= set(read_table(parse_note(p)[1]))
        unclaimed = [i for i in tr.my_open() if i["key"] not in claimed]
        print(f"== unclaimed (assigned to you, in no project): {len(unclaimed)}")
        for i in unclaimed:
            print(f"    - {i['key']} [{i['status']}] reporter {i['reporter']}: {i['summary']}")
        out["unclaimed"] = [{"key": i["key"], "status": i["status"], "summary": i["summary"], "reporter": i["reporter"]}
                            for i in unclaimed]
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("profile").set_defaults(fn=cmd_profile)
    sub.add_parser("kick").set_defaults(fn=cmd_kick)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("status"); s.add_argument("name"); s.set_defaults(fn=cmd_status)
    i = sub.add_parser("init"); i.add_argument("name"); i.add_argument("--epic")
    i.add_argument("--owns"); i.add_argument("--alias", action="append"); i.set_defaults(fn=cmd_init)
    y = sub.add_parser("sync"); y.add_argument("name", nargs="?")
    y.add_argument("--apply", action="store_true"); y.add_argument("--pull", action="store_true"); y.add_argument("--only"); y.add_argument("--no-commit", action="store_true")
    y.add_argument("--no-push", action="store_true", help="commit the note locally but don't push (unattended runs)")
    y.add_argument("--json", action="store_true", help="print the plan and what was applied as JSON on stdout")
    y.set_defaults(fn=cmd_sync)
    u = sub.add_parser("audit"); u.add_argument("name"); u.add_argument("--since"); u.add_argument("--stamp", action="store_true")
    u.set_defaults(fn=cmd_audit)
    for verb, fn in (("accept", cmd_accept), ("reject", cmd_reject)):
        a = sub.add_parser(verb, help=f"{verb} a line under ## Proposed status changes")
        a.add_argument("name"); a.add_argument("key"); a.set_defaults(fn=fn)
    r = sub.add_parser("resolve", help="resolve a sync conflict on one story")
    r.add_argument("name"); r.add_argument("key"); r.add_argument("--keep", choices=["tracker", "jira", "local"], required=True)
    r.set_defaults(fn=cmd_resolve)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
