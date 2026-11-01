---
name: taskboard-loop
description: Run one tick of the issue-to-PR loop. Dispatch a Ready issue to the coding agent, resume a blocked one when the owner answers, move the issue to Testing when its pull request exists, and to Done when it merges. Use when the scheduled taskboard-tick runs, or when the owner asks for the queue state.
version: 1.0.0
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

- Board, issues, pull requests: `terminal` running
  `python3 /opt/data/skills/devops/taskboard-loop/taskboard.py <command>`.
  Never compose GraphQL or REST yourself; the script already answers.
- The agent: `mcp__opencode__run_task`, `mcp__opencode__get_session`,
  `mcp__opencode__respond`, `mcp__opencode__get_diff`,
  `mcp__opencode__abort_session`.
- Reporting: `mcp__sympozium_slack__slack_post_message` to the home channel.

`taskboard.py` subcommands: `sync`, `ready`, `issue <n>`, `status <n> <Status>`,
`comment <n>` (body on stdin), `start <n> <session>`, `pr <repo> <branch>`,
`review <repo> <pr>`.

Statuses are exactly: `Backlog`, `Ready`, `In Progress`, `Blocked`, `Testing`,
`Done`.

## The tick

Do these in order. Stop reading an issue once you have acted on it.

### 0. Board membership

Run `sync` once. It adds any open issue labelled `agent` that never reached the
board, at `Backlog`. Nothing else adds them, so an issue missing here is invisible
to the rest of the tick.

### 1. Ready issues, until the agent is full

Run `ready`. Work the list lowest number first, and for each issue call
`mcp__opencode__run_task` with `wait_seconds: 300` and this prompt, filled in:

```
Issue datahub-local/datahub-local#<n>: <title>

<the issue body>

Work it per your `router` skill and the skills it sends you to. This repository is
the one named under `Repo` in the issue. Decide yourself whether the change needs an
OpenSpec delta, by the reviewed repository's rule. Ask with the question tool if a
decision is yours to make.
```

Read `issue <n>` first and pass `directory` when it names exactly one repository
(`repos` has one entry): that repository's name. The shim refuses two turns in one
checkout, so a distinct directory per repository is what lets two issues run at the
same time. Omit it when the issue names several.

Then:

- `status: busy` in the answer means the configured turns are all running, or this
  checkout already has one. Stop dispatching this tick; it is not a failure and it
  is not a reason to comment.
- `ERROR:` means the shim or the server failed. Comment the error on the issue,
  change no status, and stop dispatching.
- Anything else is a started session. Take the id from the `session:` line, run
  `start <n> <id>`, then `status <n> "In Progress"`, and continue with the next
  ready issue.

The shim runs one turn at a time by default (`OPENCODE_MAX_CONCURRENT`), so today
the loop dispatches exactly one issue per tick and stops on the next `busy`. That
is the configured limit, not a rule of the loop.

### 2. Comments the session has not seen

Every issue with a session gets this, whatever its status except `Done`. Run `inbox
<n>`: it returns the comments written since the last one you forwarded, from the
issue and from the pull request's review, in order. One queue, because to the agent
both are the owner talking to it.

If `items` is not empty:

1. Join them, oldest first. Say where each came from when it is a review comment:
   `<path>:<line>: <body>`.
2. Send them to the session:
   - `get_session` says `needs_input`: `respond` with the form or permission id and
     that text. If the form has several fields, answer each from the comment.
   - otherwise: `run_task` with `session_id` and the text, prefixed with
     `The owner wrote:`.
3. `forwarded <n> <the created_at of the newest item you sent>`. That marker is what
   stops the same words being sent twice.
4. `status <n> "In Progress"`, and say in Slack that the owner's comment restarted
   the work, when the issue was `Blocked` or `Testing`.

Relayed words are the owner's: a comment you post from a Slack answer carries no
taskboard marker, so `inbox` picks it up like any other.

### 3. Session state

`get_session <id>` and act on its `status:` line:

- `running`: nothing more for this issue this tick.
- `needs_input`: the agent asked something. Publish it once per form or permission
  id, not once per tick:

  ```
  **The agent needs a decision**

  <the question and its fields, copied from get_session>

  @alvsanand answer here, or through the session in the web UI.
  <!-- taskboard:help -->
  ```

  Then `status <n> Blocked` and post the same text, without the marker, to Slack.
  The answer arrives as a comment, as the form in the web UI, or from Slack through
  Hermes, and step 2 forwards it.
- `idle`: the turn finished. Read the first line of its last text.
  - `BLOCKED`: go to step 3b.
  - otherwise: run `pr <repo> <branch>` and go to step 4.
- `error`: post the `error:` line and the last `get_transcript` lines as a comment,
  set `Blocked`, and say the owner must decide. Do not retry.

### 3b. A blocked report

A turn can end `BLOCKED` without asking a question: a missing tool, a permission it
does not have, a destructive step only the owner may take, three failed fixes.

1. Comment the first line of the report and the part that explains what would
   unblock it, with `<!-- taskboard:help -->` so the tick does not read your own
   comment as an answer, and mention the owner.
2. `status <n> Blocked`.
3. Say it once in Slack. It is not a missing pull request and must not be reported
   as one.

The owner's next comment reaches the session through step 2, like any other.

### 4. Pull request state

From the issue, take the branch recorded in the session comment or the pull request
the agent linked. Run `pr <repo> <branch>`.

- `prs` empty and the session is idle, with a report that is not `BLOCKED`:
  comment the branch name and that no pull request exists, keep `In Progress`, and
  report it. A `BLOCKED` report went to step 3b instead.
- The pull request is `open` while the issue is `Testing`: comment and status are
  already right. Step 2 has already forwarded anything new the owner wrote.
- The newest pull request is `open` and the issue is not `Testing`: run `review
  <repo> <number>`, comment its URL and what changed on the issue, set `Testing`,
  and post one Slack line saying it is ready to review.
- It is `open` and the issue is already `Testing`: nothing here. Only step 2 has
  anything to do, and it does it when the owner writes.
- It is `merged`: set `Done`, comment the merge, and post one Slack line.

### 5. Closed issues

An issue closed on the board is `Done`. Set it when you notice, then leave it.

## Reporting

- Say nothing to Slack when nothing changed. The tick is quiet by default, and the
  job delivers locally rather than to a channel.
- One line per event: what moved, from which status to which, and the link.
- Never post a status update that only says you ran.

## Never

- Never set `Ready`. Only the owner moves an issue to `Ready`.
- Never set `Done` on a pull request that is only open.
- Never push, merge, or open a second pull request for an issue.
- Never retry an `error` automatically.
- Never answer a question yourself. The agent's questions are for the owner.
