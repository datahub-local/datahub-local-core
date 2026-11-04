# Proposal

## Why

The tick comments a pull request's full URL whenever a card returns to `Code
Review`. After a fix round that is the same pull request, already announced, so the
issue gains the same link again while the change is described nowhere. The agent
now comments what it fixed (see `datahub-local-ai`: `report-fixes-on-the-issue`),
and that comment is the record.

## What Changes

- Step 5 of `taskboard-loop/SKILL.md` comments the pull request URL only when the
  issue does not already carry it, and leaves a fix round to the agent's comment.

Not changed: a new pull request is still announced in full, and the card still
moves to `Code Review` after review.

## Impact

- `releases/automation/files/agent/taskboard-loop/SKILL.md`
- `openspec/specs/taskboard-loop/spec.md`
