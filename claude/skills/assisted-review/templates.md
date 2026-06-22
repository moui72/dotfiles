# UI templates

Loaded by SKILL.md when rendering printed UI. All templates use the palette in [palette.md](palette.md). Do not wrap any of these in markdown code blocks when emitting — the terminal must interpret the escape codes.

## Resume prompt (state file exists)

```
\e[1;33mFound in-progress review\e[0m from <relative-time> ago (\e[1m<done>\e[0m of \e[1m<total>\e[0m chunks complete).
  \e[2m[\e[0mr\e[2m]\e[0m resume   \e[2m[\e[0mn\e[2m]\e[0m restart   \e[2m[\e[0mc\e[2m]\e[0m cancel
```

## `bat` install prompt

```
\e[1;33mbat is not installed\e[0m, so diffs will render without syntax highlighting.
  \e[2m[\e[0my\e[2m]\e[0m install now   \e[2m[\e[0mn\e[2m]\e[0m skip this time   \e[2m[\e[0ms\e[2m]\e[0m skip and don't ask again
```

## Preamble (printed once)

```
\e[1;36mPR \e[1;37m<owner>/<repo>#<num>\e[0m\e[1;36m — "<title>"\e[0m
\e[1mAuthor:\e[0m @<author>  ·  \e[1mBase:\e[0m <base> ← \e[1mHead:\e[0m <head>  ·  \e[1mHEAD:\e[0m <short-sha>
\e[1mDraft:\e[0m <yes|no>  ·  \e[1mMergeable:\e[0m <mergeable-styled>
\e[1mCI:\e[0m \e[32m<pass-count> passing\e[0m, \e[31m<fail-count> failing\e[0m, \e[2m<skip-count> skipped/pending\e[0m<, list failing names if any in \e[31m…\e[0m>
\e[1mURL:\e[0m \e[36m<pr-url>\e[0m

<AI summary>

\e[1m<total-hunks> hunks total\e[0m
  · \e[2m<N> auto-skipped as generated/lockfiles\e[0m (type `\e[1mS\e[0m` to list)
  · \e[2m<M> auto-skipped as no-risk:\e[0m <breakdown e.g. "8 formatting, 3 import reorders">
    (type `\e[1ms\e[0m` to inspect; any can be promoted into the queue)
  · \e[1;37m<Q> chunks queued for review\e[0m

\e[2m<E> existing review threads from <authors> (<open> open, <resolved> resolved) will be shown
  on their respective chunks.\e[0m

Press \e[1mEnter\e[0m to begin (or `\e[1ms\e[0m` / `\e[1mS\e[0m` to inspect skips first).
```

## Per-chunk card

Header rule total width ≈ 60 chars (cyan dashes pad either side of the centered label).

```
\e[1;36m─── Chunk <i> of <N> · \e[0m\e[1;<rating-color>m<emoji> <rating>\e[0m\e[1;36m<· <K> hunks if members.length > 1> ──────────────────────────────\e[0m
\e[1;37m<file>\e[0m  \e[2;35m<hunk_header><, +<K-1> more if grouped></e[0m

<diff body — bat-colored or plain>

\e[1mAI notes\e[0m
  <2-5 sentence commentary in plain prose. Call out the change directly,
   flag concrete concerns, no hedging filler. Append later investigation
   notes below the initial note with a leading "\e[2m↳ asked:\e[0m <prompt>".>

<if existing open threads on this chunk>
\e[1mExisting threads\e[0m
  @<author>\e[33m[bot]\e[0m (open): "<body, single-line, truncate to ~80 chars>"
  <... more open threads ...>
  \e[2m(<count> resolved — type `R` to view)\e[0m

\e[1mActions\e[0m
  \e[2m[\e[0m1\e[2m]\e[0m more context   \e[2m[\e[0m2\e[2m]\e[0m mark viewed   \e[2m[\e[0m3\e[2m]\e[0m comment
  \e[2m[\e[0m4\e[2m]\e[0m ask AI         \e[2m[\e[0m5\e[2m]\e[0m flag          \e[2m[\e[0mb\e[2m]\e[0m back
  \e[2m[\e[0mD\e[2m]\e[0m dump drafts    \e[2m[\e[0mT\e[2m]\e[0m show threads   \e[2m[\e[0mq\e[2m]\e[0m quit & save
\e[1m>\e[0m
```

In the flagged-queue pass, drop `[5] flag`; the action menu collapses to: `[1] more context  [2] mark viewed  [3] comment  [4] ask AI  [b] back  [D] dump drafts  [T] show threads  [q] quit & save`.

When this is the **only chunk left in the current queue**, also drop `[4] ask AI` — defer-to-bottom would be a no-op.

## Comment action — open-threads prompt

Shown when action `3` is invoked on a chunk that has open threads:

```
This chunk has \e[1m<K>\e[0m open thread(s):
  \e[2m[\e[0m1\e[2m]\e[0m @bob: "<body>"
  \e[2m[\e[0m2\e[2m]\e[0m @alice \e[33m[bot]\e[0m: "<body>"
Reply to one (type number), or \e[2m[\e[0mn\e[2m]\e[0m new top-level comment?
\e[1m>\e[0m
```

## Comment action — body prompt

```
\e[1mComment body\e[0m \e[2m(end with a blank line — or fence with `:::done` if the body itself contains a blank line)\e[0m:
\e[1m>\e[0m
```

## Action `3` — inline body syntax

Single-turn shortcut: append `:: <body>` to the action to skip the body prompt. Examples:
- `3 :: nit: rename to fooBar`
- `3 L45 :: this can be `null` here, see L40`
- `3 L20-22 :: extract this into a helper`

The body runs from the first non-space char after `::` to end-of-message. If the body itself contains blank lines, use the regular prompt flow instead (don't include `::`).

## Line-anchor validation error

```
\e[1;31mline <n> not in hunk range, retry\e[0m
```

## Flagged-pass banner

```
\e[1;36mMain pass complete.\e[0m \e[1m<K>\e[0m chunk(s) flagged for second look.
\e[1;36mBeginning flagged review.\e[0m
```

## Stale-PR prompt

```
\e[1;33mHEAD changed\e[0m since you started this review:
  \e[1mStarted at:\e[0m \e[2m<old>\e[0m
  \e[1mNow:\e[0m        \e[1;37m<new>\e[0m

  \e[2m[\e[0ma\e[2m]\e[0m abort \e[2m(discard draft)\e[0m
  \e[2m[\e[0ms\e[2m]\e[0m submit what you have against \e[2m<old>\e[0m
  \e[2m[\e[0mc\e[2m]\e[0m continue with stale diff, submit against \e[2m<old>\e[0m
  \e[2m[\e[0mr\e[2m]\e[0m restart against new HEAD \e[2m(discard draft)\e[0m
\e[1m>\e[0m
```

## Stale-inline fallback prompt

Shown when `submit-review.sh` exits 4 (`STALE_INLINE`). The reviewed SHA is no longer in the PR's commits list, so inline comments would be rejected by GitHub. Replies (if any) have already posted.

```
\e[1;33mInline comments can't anchor\e[0m: the SHA you reviewed (\e[2m<old>\e[0m) is no
longer in the PR's commits list (likely force-pushed). New HEAD is \e[1;37m<new>\e[0m.

How should I handle the \e[1m<N>\e[0m drafted inline comment(s)?
  \e[2m[\e[0m1\e[2m]\e[0m embed in overall body \e[2m— prefix each with `<file>:<lines>` and append to body\e[0m
  \e[2m[\e[0m2\e[2m]\e[0m re-anchor to new HEAD \e[2m— I'll try to find each line in the new diff; ask per-comment for unresolved\e[0m
  \e[2m[\e[0m3\e[2m]\e[0m drop inline comments  \e[2m— post body only, discard inline\e[0m
\e[1m>\e[0m
```

## Per-comment re-anchor prompt (option 2 fallbacks)

Shown for each inline comment the re-anchor pass cannot locate in the new diff.

```
\e[1;33mCan't re-anchor\e[0m \e[1;37m<file>:<old-lines>\e[0m:
  \e[2m<comment body preview>\e[0m
  \e[2mOriginal anchor content:\e[0m
    \e[2m<2-3 lines of original context>\e[0m

  \e[2m[\e[0mt\e[2m]\e[0m anchor to top of \e[1;37m<file>\e[0m \e[2m(line 1, RIGHT)\e[0m
  \e[2m[\e[0mb\e[2m]\e[0m move into overall body
  \e[2m[\e[0md\e[2m]\e[0m drop this comment
\e[1m>\e[0m
```

## Drafts dump (action `D`)

Print the running draft list inline (same shape as the end-of-review draft list), then re-prompt with the current chunk's action menu. Read-only.

If no drafts yet:
```
\e[2m(no comments drafted yet)\e[0m
```

## Thread expand (action `T`)

Reprint each existing thread on the current chunk with full bodies (no 80-char truncation), each comment in chronological order:

```
\e[1mExisting threads (expanded)\e[0m
  \e[1m@<author>\e[0m\e[33m[bot]\e[0m \e[2m<relative-time>\e[0m
    <full body, indented 4 spaces, wrapped at terminal width>
  \e[2m↳\e[0m \e[1m@<replier>\e[0m \e[2m<relative-time>\e[0m
    <reply body>
```

Then re-prompt with the same chunk's action menu.

## Quit confirmation

```
\e[1;32mSaved.\e[0m Resume with \e[1massisted-review <ref>\e[0m.
```

## End-of-review — summary

```
\e[1;36mReview complete.\e[0m
  · \e[1m<N>\e[0m chunks reviewed
  · \e[1m<C>\e[0m comments drafted across \e[1m<F>\e[0m chunks
  · \e[1m<R>\e[0m replies to existing threads
  · \e[1m<K>\e[0m flagged chunks resolved on second pass
```

## End-of-review — draft list entry (PR file order)

```
\e[1;37m<file>:<line(s)>\e[0m
  <if reply> \e[2m> <thread body excerpt>\e[0m
  <if reply> \e[1m[reply to @<author>]:\e[0m <body>
  <if new>   \e[1m[new comment]:\e[0m <body>
```

## End-of-review — verdict prompt

Hide `approve` if `state.preamble.self_authored`.

```
\e[1mVerdict:\e[0m  \e[2m[\e[0ma\e[2m]\e[0m \e[1;32mapprove\e[0m   \e[2m[\e[0mc\e[2m]\e[0m \e[1;36mcomment\e[0m   \e[2m[\e[0mr\e[2m]\e[0m \e[1;31mrequest changes\e[0m
\e[1m>\e[0m
```

Map to API event values: `APPROVE`, `COMMENT`, `REQUEST_CHANGES`.

## End-of-review — body prompt

```
\e[1mOverall review body:\e[0m  \e[2m[type it / g to AI-generate / s to skip]\e[0m
\e[1m>\e[0m
```

On `g`, frame the proposed body and re-prompt:

```
\e[1;36m─── proposed body ───\e[0m
<generated body>
\e[1;36m──────────────────────\e[0m

\e[2m[\e[0me\e[2m]\e[0m edit   \e[2m[\e[0ma\e[2m]\e[0m accept   \e[2m[\e[0mr\e[2m]\e[0m regenerate
\e[1m>\e[0m
```

## Edit drafted comment (verdict step)

At the verdict prompt the user may type `e <chunk-id>` to re-open a drafted comment for editing. Flow:

1. Print the existing draft:
   ```
   \e[1mEditing\e[0m \e[1;37m<file>:<lines>\e[0m
   \e[2mcurrent:\e[0m <body>
   ```
2. Show the body prompt from this file (same template as action `3`).
3. Replace `state.chunks[<id>].comments[<idx>].body`. Persist state.
4. Re-show the end-of-review summary and verdict prompt.

If the chunk-id has multiple drafted comments, list them numbered and ask which to edit.

## End-of-review — final confirm

Style the verdict word with its rating color (`APPROVE` green, `COMMENT` cyan, `REQUEST_CHANGES` red).

```
\e[1;36mAbout to submit\e[0m to \e[36m<pr-url>\e[0m:
  \e[1mEvent:\e[0m    <verdict-styled>
  \e[1mBody:\e[0m     <first 200 chars + ellipsis if longer, or \e[2m(empty)\e[0m>
  \e[1mComments:\e[0m <count>  \e[2m(<inline-count> inline, <reply-count> replies)\e[0m

  \e[2m[\e[0my\e[2m]\e[0m submit   \e[2m[\e[0mn\e[2m]\e[0m cancel \e[2m(keep draft)\e[0m
\e[1m>\e[0m
```

## End-of-review — submitted

```
\e[1;32mSubmitted:\e[0m <verdict-styled>
  \e[36m<review-html-url>\e[0m

\e[2mState archived to <archive-path>\e[0m
```
