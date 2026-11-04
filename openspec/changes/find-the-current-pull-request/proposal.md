# Proposal

## Why

Issue #99 showed the loop losing a second cycle. The first pull request (#53)
merged, the owner asked for a fix, and the agent opened a new pull request (#55)
on a new branch. From then on the tick read the wrong pull request:

- `last_branch` only matched the claim format `Branch \`x\``, and the second
  branch was only ever printed by the tick itself as `(branch \`x\`)`, so the
  branch stayed `feat/99-agent-authored-articles`.
- `inbox 99` therefore attached the comments of merged pull request #53 and
  never read #55.
- `pr <repo> <feat/99-…>` answered `merged`, so the card could move to `Testing`
  while #55 was open, and no comment announced the new pull request.
- A comment on the issue still reached the queue, but the agent's work on #55
  could not be seen by the tick at all.

The branch is not a durable key once an issue has more than one cycle. The
`Refs datahub-local/datahub-local#<n>` line in the pull request body is, and
every pull request carries it.

## What Changes

- `taskboard.py` resolves the current pull request from the `Refs` line, open
  first, newest number first, and falls back to the branch only when nothing
  references the issue.
- `inbox` reads comments from every pull request that references the issue, so a
  reply on the merged one is not dropped.
- A new `pull <n>` command reports `current` and every referencing pull request,
  and the tick's step 5 uses it instead of `pr <repo> <branch>`.
- `BRANCH_RE` and `CLAIM_REPO_RE` match `branch` in any case, so a pull request
  comment does not hide the newest branch.

Not changed: one open pull request at a time, `Done` on a closed issue, and the
merge still moves the card to `Testing`.

## Impact

- `releases/automation/files/agent/taskboard-loop/taskboard.py`
- `releases/automation/files/agent/taskboard-loop/SKILL.md`
- `tests/test_taskboard.py`
- `openspec/specs/taskboard-loop/spec.md`
