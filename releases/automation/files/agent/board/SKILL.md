---
name: board
description: Answer the owner's board request in Slack. List a column, show one issue, move an issue's Status, or comment on it. Use when the owner writes board words in chat, not for the scheduled tick (that is taskboard-loop).
version: 1.0.0
metadata:
  hermes:
    tags: [taskboard, github, slack]
    category: devops
---

# Board requests

The owner asks in Slack and you do the one thing asked. This is not a tick: never
run `sync`, never dispatch an issue to the coding agent, never poll a session, and
never move a card the owner did not name.

## Tool

`terminal`, running the same helper the tick uses:

```
python3 /opt/data/skills/devops/taskboard-loop/taskboard.py <command>
```

It mints its own token from the sidecar, so there is nothing to export first.

| The owner writes | Run |
| --- | --- |
| "what's in Ready", "list in progress", "show me the board" | `board` (then keep the column asked for) |
| "what's ready", "anything to pick up" | `ready` |
| "116", "show 116", "what is 116" | `issue 116` |
| "move 116 to ready", "block 116", "116 is testing" | `status 116 <Status>` |
| "tell 116 ...", "comment on 116 ...", "answer 116 ..." | `comment 116 --owner`, body on stdin |

Statuses are exactly `Backlog`, `Ready`, `In Progress`, `Blocked`, `Testing`,
`Done`. Translate the owner's words to one of those and nothing else.

## Read before you write

Run `issue <n>` first, every time, even when the owner sounds sure. The reply names
the status it moved from, and a card already in the target column is answered
"already Ready" rather than written twice.

A move the owner asked for is allowed even when it is `Ready`, `Done` or back to
`Backlog`. The tick may not set `Ready`; you may, because the owner is the one
deciding.

## One write per request

Do not chain. If the owner asks for a move, move and answer. If they ask what is
next, read and answer. Do not also comment, relabel, or dispatch unless they said
so in that message.

## Comments are the owner's words

A dictated comment is posted with `--owner`, so it carries no
`<!-- taskboard:` marker and the tick treats it as the owner talking. Pass the body
through a quoted heredoc, never `echo`: it can contain backticks and `$(...)`.

```
cat <<'EOF' | python3 /opt/data/skills/devops/taskboard-loop/taskboard.py comment 116 --owner
> the words the owner dictated
EOF
```

## When the request is unclear

Ask once with the question tool and stop. A missing issue number, two numbers, or a
status that is not in the list is a question for the owner, not a guess and not a
default. Never pick an issue because it is the only one in a column.

## Answer

One line with what changed or what the column holds, and the link. Nothing about
how you ran it, nothing repeated back. When the helper fails, say the error it
printed and stop; do not retry and do not substitute a different command.
