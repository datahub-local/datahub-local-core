# Proposal

## Why

The loop moved #127 from `Ready` to `In Progress` and told nobody. The tick's
reply went to local delivery, so the only Slack line was the one the model chose
to write, and the dispatch step never asked for one. The same gap hid the first
question: the coding agent asked 70 seconds after dispatch, no tick ran for ten
minutes, and the owner found the question by opening the OpenCode UI by hand.

Reporting is part of the state change, not a courtesy after it. A card write the
owner cannot see is the same as no write, and a question delivered only inside a
session is a question the owner has to go looking for.

## What Changes

- `taskboard.py` posts the Slack line for every board write it performs: a card
  added at `Backlog`, every status transition (`In Progress`, `Blocked`,
  `Testing`, `Done`), with the issue link and the session link when one exists.
- `taskboard.py session_url` builds the OpenCode web link:
  `<origin>/server/<fnv1a-base36(origin)>/session/<id>`. The origin comes from
  `TASKBOARD_OPENCODE_URL` in the Hermes values.
- `taskboard.py notify <n>` posts a question or report to Slack and appends the
  issue URL and the session URL, so the owner can answer on the issue or pick the
  options in the UI.
- The tick waits up to 120 seconds after dispatch. An early `needs_input` is
  published and the card moves to `Blocked` in the same tick; a longer turn still
  returns `running`.
- The issue comment for a question carries the session link. The comment for a
  pull request carries the full URL, never only the number.
- PR and merge events stay on GitHub notifications; no extra Slack line is added
  for them.

## Impact

- `releases/automation/files/agent/taskboard-loop/taskboard.py`
- `releases/automation/files/agent/taskboard-loop/SKILL.md`
- `releases/automation/values/hermes.yaml.gotmpl`: `TASKBOARD_OPENCODE_URL`
- `tests/test_taskboard.py`
- `openspec/specs/taskboard-loop/spec.md` through this change's delta
- One Hermes rollout; the volume and existing jobs are untouched.
