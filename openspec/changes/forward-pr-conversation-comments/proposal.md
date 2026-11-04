# Proposal

## Why

An owner comment on `datahub-local-ai#53` never reached the session that wrote the
pull request. `inbox` reads the issue's comments and the pull request's inline
review comments, but not the pull request's conversation comments
(`/repos/<repo>/issues/<n>/comments`), which is where the owner wrote.

A second gap hid the first: issue `datahub-local#99` has no `## Repo` section, so
`inbox` returned `"repo": null` and skipped the pull request lookup entirely. The
tick's own `pr <repo> <branch>` calls passed the bare name (`datahub-local-ai`),
which the API reads as an owner, so every poll since 2026-11-03 answered
`404` from `/repos/datahub-local-ai/pulls`.

## What Changes

- `taskboard.py inbox` reads the pull request's conversation comments as well as
  its inline review comments, in the same ordered queue, deduplicated by comment id.
- Repository resolution falls back to the newest claim comment
  (`Branch \`x\` in <repo>`) when the issue has no `## Repo` section, and always
  carries the organisation.
- `pr` and `review` accept a bare repository name as well as a full slug.
- The `taskboard-loop` skill and the spec name the conversation surface.

Not changed: delivery is still the ten-minute tick, not a webhook; a review
submitted with only a body (`/pulls/<n>/reviews`) is still not read.

## Impact

- `releases/automation/files/agent/taskboard-loop/taskboard.py`
- `releases/automation/files/agent/taskboard-loop/SKILL.md`
- `tests/test_taskboard.py`
- `openspec/specs/taskboard-loop/spec.md`
