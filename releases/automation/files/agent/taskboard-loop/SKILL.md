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

Work it per your taskboard skill. This repository is the one named under `Repo`
in the issue. Ask with the question tool if a decision is yours to make.
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

### 2. In Progress issues

For each issue whose status is `In Progress`:

1. `issue <n>` for the body, the comments and the recorded session.
2. No session recorded: comment that the session was lost, leave the status, and
   report it.
3. `get_session <id>` and act on its `status:` line:
   - `running`: nothing. Do not poll it again this tick.
   - `idle`: the turn finished. Run `pr <repo> <branch>` for the branch recorded
     in the issue, and go to step 4.
   - `needs_input`: go to step 3.
   - `error`: post the `error:` line and the last `get_transcript` lines as a
     comment, set `Blocked`, and say the owner must decide. Do not retry.

### 3. A question

A session that reports `needs_input` has asked something. Do this once per form or
permission id, not once per tick:

1. Comment on the issue, with `taskboard.py comment <n>` on stdin:

   ```
   **The agent needs a decision**

   <the question and its fields, copied from get_session>

   @alvsanand answer here, or through the session in the web UI.
   <!-- taskboard:help -->
   ```

2. `status <n> Blocked`.
3. Post the same text, without the marker, to Slack.

Then, for an issue already `Blocked`, resume when the owner answered:

- `issue <n>` and read `help.answered`. If true, call `respond` with the session
  id, the form or permission id from `get_session`, and the answer text from
  `help.answer.body`. Then `status <n> "In Progress"`.
- If `help.answered` is false but `get_session` no longer says `needs_input`, the
  owner answered in the web UI. Set `In Progress` and forward nothing.
- When both are present, forward the issue answer and ignore the form answer.

### 4. Pull requests

From the issue, take the branch recorded in the session comment or the pull request
the agent linked. Run `pr <repo> <branch>`.

- `prs` empty and the session is idle: comment the branch name and that no pull
  request exists, keep `In Progress`, and report it.
- The newest pull request is `open`: run `review <repo> <number>`, comment its URL
  and what changed on the issue, set `Testing`, and post one Slack line saying it
  is ready to review.
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
