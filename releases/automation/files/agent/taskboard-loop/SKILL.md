---
name: taskboard-loop
description: Run one tick of the issue-to-PR loop. Dispatch a Ready issue to the coding agent, forward the owner's comments, move the issue to Testing when its pull request exists, and to Done when it merges. Use when the scheduled taskboard-tick runs, or when the owner asks for the queue state.
version: 1.1.0
metadata:
  hermes:
    tags: [taskboard, github, opencode, orchestration]
    category: devops
---

# Taskboard loop

One tick. The issue is the record and the Project board is the state; you are the
only writer of that state. The coding agent writes code and comments; it never
moves a card.

## Tools

- Board, issues and pull requests: `terminal` running
  `python3 /opt/data/skills/devops/taskboard-loop/taskboard.py <command>`.
  Never compose GraphQL or REST yourself; the script already answers.
- The agent: `mcp__opencode__run_task`, `mcp__opencode__get_session`,
  `mcp__opencode__respond`, `mcp__opencode__get_diff`,
  `mcp__opencode__get_transcript`, `mcp__opencode__abort_session`,
  `mcp__opencode__list_sessions`.
- Reporting: `mcp__sympozium_slack__slack_post_message` to the home channel.

`taskboard.py` subcommands: `sync`, `board`, `ready`, `issue <n>`, `inbox <n>`,
`status <n> <Status>`, `comment <n> [--owner]` (body on stdin), `start <n>
<session>`, `forwarded <n> <since>`, `pr <repo> <branch>`, `review <repo> <pr>`.

Statuses are exactly: `Backlog`, `Ready`, `In Progress`, `Blocked`, `Testing`,
`Done`.

When you post a body that came from somewhere else, pass it through a quoted
heredoc, never `echo`: the text can contain backticks and `$(...)`.

```
cat <<'EOF' | python3 /opt/data/skills/devops/taskboard-loop/taskboard.py comment 116
> the body, verbatim
EOF
```

## The tick

The tick has no memory between runs, so it starts by reading the board. Run `sync`,
then `board`, then work the list. Nothing below is reached by guessing an issue
number.

### 0. Board membership

`sync` adds any open issue labelled `agent` that never reached the board, at
`Backlog`. Nothing else adds them, so an issue missing here stays invisible.

### 1. Closed issues

For any board item whose `state` is `CLOSED` and whose status is not `Done`: set
`Done`, comment the merge or the close, and post one Slack line. Skip everything
else for that issue.

### 2. Ready issues, until the agent is full

Work the `Ready` items lowest number first. For each, read `issue <n>` first:

- It already records a session: a previous tick started work and died before the
  status moved. Set `In Progress`, comment that it resumed, and do not dispatch a
  second session.
- Otherwise dispatch: call `mcp__opencode__run_task` with `wait_seconds: 300`, the
  `directory` from `repos` when the issue names exactly one repository, and this
  prompt:

  ```
  Issue datahub-local/datahub-local#<n>: <title>

  <the issue body>

  Work it per your `router` skill and the skills it sends you to. This repository is
  the one named under `Repo` in the issue. Decide yourself whether the change needs
  an OpenSpec delta, by the reviewed repository's rule. Ask with the question tool
  if a decision is yours to make.
  ```

Then:

- `status: busy`: the configured turns are all running, or that checkout already
  has one. Stop dispatching this tick. Say nothing and change nothing.
- `ERROR:`: comment the error on the issue, change no status, stop dispatching.
- Anything else: take the `session:` id, run `start <n> <id>`, set `In Progress`,
  and continue with the next ready issue.

### 3. Comments the session has not seen

For every board item that is `In Progress`, `Blocked` or `Testing`, run `inbox <n>`.
It returns the comments written since the last one you forwarded, from the issue
and from the pull request's review, in order. One queue, because to the agent both
are the owner talking to it.

If `items` is not empty:

1. Check `get_session` first. If the session is `running`, stop here and leave the
   marker alone: forwarding into a live turn returns `busy`, and marking it would
   lose the comment. The next tick sends it.
2. Join the items, oldest first. Say where each came from when it is a review
   comment: `<path>:<line>: <body>`.
3. Send them:
   - `needs_input`: `respond` with the form or permission id and that text. If the
     form has several fields, answer each from the comment.
   - otherwise: `run_task` with `session_id` and the text, prefixed with
     `The owner wrote:`.
4. `forwarded <n> <the created_at of the newest item you sent>`.
5. `status <n> "In Progress"`, and say in Slack that the owner's comment restarted
   the work, when the issue was `Blocked` or `Testing`.

Relayed words are the owner's: post a Slack answer with `comment <n> --owner`, which
leaves it unmarked so `inbox` forwards it like any other.

### 4. Session state

`get_session <id>` and act on its `status:` line:

- `running`: nothing more for this issue this tick.
- `needs_input`: the agent asked something. Publish it once per form or permission
  id: read `issue <n>` and skip if the newest comment carrying
  `<!-- taskboard:help -->` already names this id. Otherwise post:

  ```
  **The agent needs a decision**

  <the question and its fields, copied from get_session>

  @alvsanand answer here, or through the session in the web UI.
  <!-- taskboard:help -->
  ```

  Then `status <n> Blocked` and post the same text, without the marker, to Slack.
- `idle`: the turn finished. Read the first line of its last text.
  - `BLOCKED`: go to step 4b.
  - otherwise: run `pr <repo> <branch>` and go to step 5.
- `ERROR: no session`: the recorded session is gone. Comment that it was lost and
  what the last known state was, leave the status, and report it. Do not start a
  new session on your own.
- `ERROR:` otherwise: comment the error, set `Blocked`, and say the owner must
  decide which way to go. Do not retry.

### 4b. A blocked report

A turn can end `BLOCKED` without asking a question: a missing tool, a permission it
does not have, a destructive step only the owner may take, three failed fixes.

1. Comment the first line of the report and the part that explains what would
   unblock it, with `<!-- taskboard:help -->` so the tick does not read your own
   comment as an answer, and mention the owner.
2. `status <n> Blocked`.
3. Say it once in Slack. It is not a missing pull request and must not be reported
   as one.

### 5. Pull request state

Take the branch from the agent's claim comment or the pull request it linked, and
run `pr <repo> <branch>`.

- `prs` empty and the session is idle, with a report that is not `BLOCKED`: comment
  the branch name and that no pull request exists, once. If a comment already says
  it, say nothing. Keep `In Progress`.
- `open` and the issue is `In Progress`: run `review <repo> <number>`, comment its
  URL and what changed on the issue, set `Testing`, and post one Slack line saying
  it is ready to review.
- `open` and the issue is already `Testing`: nothing. Only step 3 has anything to
  do, and it does it when the owner writes.
- `open` and the issue is `Blocked`: nothing. A question outranks an old pull
  request; only the owner's answer leaves `Blocked`.
- `merged`: set `Done`, comment the merge, and post one Slack line.

## Reporting

- Say nothing to Slack when nothing changed. The tick is quiet by default, and the
  job delivers locally rather than to a channel.
- One line per event: what moved, from which status to which, and the link.
- Never post a status update that only says you ran.

## Never

- Never set `Ready`. Only the owner moves an issue to `Ready`.
- Never set `Done` on a pull request that is only open.
- Never push, merge, or open a second pull request for an issue.
- Never retry an `error` automatically, and never start a session to replace a lost
  one.
- Never answer a question yourself. The agent's questions are for the owner.
- Never leave `Blocked` for any reason except forwarding the owner's answer.
