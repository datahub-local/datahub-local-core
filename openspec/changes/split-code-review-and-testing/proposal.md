# Proposal

## Why

The board has one state, `Testing`, for two different jobs. The tick sets it as
soon as a pull request exists, so it means "review and merge this pull request".
The owner also needs a state for the days after that: the pull request merged, the
change deployed, and the owner trying it on the cluster. A merge today only leaves
a comment, so the card stays in `Testing` and the board cannot tell review from
verification.

The gap bites when verification fails. The owner comments on the issue, the agent
fixes it, and a second pull request is needed, but the loop's rule is "never open a
second pull request for an issue", and the card has no state to return to.

## What Changes

- `Code Review` becomes the state while a pull request is open: the tick moves the
  card there after it comments the pull request URL, instead of `Testing`.
- `Testing` becomes the post-merge state: the tick moves the card there when it
  sees the pull request merged.
- `Done` still needs a closed issue. The merge is not the end; the owner closes the
  issue after the change works.
- A comment on a card in `Testing` moves it to `In Progress`, and the agent may open
  a new pull request for the fix on a new branch. That pull request goes through
  `Code Review` and back to `Testing` on merge.
- All seven statuses are named in the `taskboard-loop` and `board` skills, and the
  active-item order in `taskboard.py` puts `Code Review` before `Testing`.

Not changed: the tick schedule, the Slack reporting shape, `finish`'s refusal to
set `Done` on an open issue, and the rule that one tick starts one session.

## Impact

- `releases/automation/files/agent/taskboard-loop/taskboard.py`
- `releases/automation/files/agent/taskboard-loop/SKILL.md`
- `releases/automation/files/agent/board/SKILL.md`
- `tests/test_taskboard.py`
- `openspec/specs/taskboard-loop/spec.md`
- `datahub-local/datahub-local`: `docs/projects/agentic-code-automation.md`
