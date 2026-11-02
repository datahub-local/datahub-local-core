# Design

## Reporting belongs to the write, not the model

The tick previously told the model "post one Slack line" in prose. On #127 the
model moved the card and returned a report to local delivery, and no Slack line
was sent. Prose is not a guarantee.

`status`, `finish` and `sync` now post the line themselves, after the GitHub call
succeeds. The line is built from facts the helper already has: the previous and
new status, the issue title and URL, and the session recorded on the issue. The
model cannot forget it, and a retried command cannot post twice because an
unchanged status posts nothing.

Slack failure does not fail the write. The card is already moved; returning an
error would tell the tick the move failed and invite a retry. The helper prints a
warning to stderr and reports `notified: false` in its JSON.

## The session link is a UI route, not an API URL

The OpenCode v2 web app routes a session at
`/server/<serverKey>/session/<sessionID>`. `serverKey` is not the origin string:
it is an FNV-1a hash of `location.origin`, rendered in base36. A link built from
the session id alone lands on the app root and loses the question.

`taskboard.py session_url` computes that key from `TASKBOARD_OPENCODE_URL`. The
value is the public origin (`https://automation-opencode.<gateway_hostname>`) and
must match what the browser reports as `location.origin`, including the scheme
and no trailing slash.

## A question is two notifications, not one

The issue comment is the durable record: the question, its options, and links to
the issue and the session. `notify <n>` posts the same text to Slack with the
links appended. The card move to `Blocked` then posts its own line, because the
board changed.

Two lines for one question is deliberate: one says what changed, the other says
what the owner has to decide. The alternative, folding the question into the
move line, loses the options that make the decision answerable.

## Wait long enough to catch the first question

`run_task` used a 10-second wait, so the tick ended before the agent asked
anything and the question waited for the next tick. On #127 that was seven
minutes of silence. A 120-second wait catches the common case (the agent reads
the issue and asks before it starts editing) without holding the tick for a long
turn. `run_task` still returns `running` when the turn outlives the wait, so the
one-turn-at-a-time rule and the ten-minute schedule are unchanged.

When the dispatch itself returns `needs_input`, the tick records the session and
goes straight to the question path, moving the card from `Ready` to `Blocked`.
It does not pass through `In Progress`: the board should say what is true now.

## Pull request links are for the issue, not Slack

GitHub already notifies on a pull request and a merge. The loop's job is to let
the owner open the pull request from the issue with one click, so the comment
carries `https://github.com/<org>/<repo>/pull/<n>`, not `#<n>` or a number the
owner has to turn into a URL. Slack gets the `Testing` and `Done` board moves,
which is the state change the owner asked to see.
