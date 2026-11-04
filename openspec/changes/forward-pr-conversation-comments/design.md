# Design

## Context

GitHub splits what a reader calls "a comment on the pull request" across three
REST collections:

| surface | collection | read today |
| --- | --- | --- |
| issue / pull request conversation | `/repos/<repo>/issues/<n>/comments` | issue only, never the pull request |
| inline review comment | `/repos/<repo>/pulls/<n>/comments` | yes |
| review summary | `/repos/<repo>/pulls/<n>/reviews` | no |

The owner wrote in the first collection on `datahub-local-ai#53`. The tick read
the second, which was empty, and the lookup itself was null because the issue
lacked `## Repo`.

## Goals / Non-Goals

**Goals**

- Every human comment on the issue or the pull request reaches the session once.
- The pull request is found from the branch and the repository the work already
  names, without requiring the intake shape to be perfect.

**Non-Goals**

- Immediate delivery (a webhook); the tick stays the only path.
- Reading review summaries, which carry no line and are rare in this loop.
- Widening which issues the loop works on.

## Decisions

### D1 — One queue over both pull-request collections

`GitHub.pull_comments` returns the conversation comments and the inline review
comments shaped alike, with `path`/`line` present only on the inline ones.
`merge_pending` deduplicates by comment id and sorts by `created_at`, so the
order the owner wrote in is the order the session reads. Rationale: the owner
does not distinguish the two boxes, and the tick should not keep two markers.

### D2 — A repository comes from `## Repo`, else from the claim

`repo_of(body, comments)` uses `repos_of(body)` when it names exactly one
repository; otherwise it reads the newest claim comment for
`Branch \`<branch>\` in <repo>`. The owner's intake shape asks for `## Repo`, but
#99 proves an existing issue can predate or miss it, and the claim is already the
record the tick uses for the branch.

### D3 — The organisation is added at the boundary

`full_repo` prefixes `TASKBOARD_ORG` to a bare name and leaves a slug alone.
Both `inbox` and the `pr`/`review` subcommands pass through it, because the model
is told the repository the way the issue prose names it and `/repos/<name>` is a
404, not a lookup.

### D4 — A missing repository stays a silent skip

If neither the section nor a claim names a repository, `inbox` still reports
`"repo": null` and no items. Guessing from another issue's branch is worse than
leaving the next tick to a corrected issue.

### D5 — The receipt is a reaction, written with the outcome

GitHub has no check-mark reaction; `eyes` is the available acknowledgement that
matches the Slacks plugin's 👀. `forwarded` reacts after writing the marker, so a
comment is acknowledged only once the session actually has it. `--failed` reacts
`confused` (😕) and skips the marker, which keeps the retry intact. Each comment
knows the repository and collection it came from, and the reaction goes to
`/issues/comments/<id>/reactions` or `/pulls/comments/<id>/reactions` accordingly.
A failed reaction warns, because losing the receipt is better than losing the
comment to a duplicate send. A `busy` answer is not a failure: the agent is
single-turn, so a comment that arrives while another issue's turn runs waits for
the next tick, and writing 😕 would claim a loss that did not happen.

### D6 — The queue is visible as one ⏳ note, not a reaction

GitHub has no hourglass reaction, so a queued comment gets a temporary comment in
the same thread, marked `<!-- taskboard:waiting -->`. `waiting` posts it only when
none exists, and `forwarded` deletes it after success or a real error. It goes on
the pull request when there is one and on the issue otherwise, because that is the
thread the owner is reading. The marker is a machine marker, so `inbox` can never
forward the note as the owner's words.
