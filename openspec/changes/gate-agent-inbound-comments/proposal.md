# Proposal

## Why

`datahub-local` and its sibling repositories are public, so anyone with a GitHub
account can comment on an agent-labelled issue or on a pull request. The tick
forwards every comment that lacks a `<!-- taskboard:` marker to an OpenCode
session that holds `contents: write`, and treats the first one after a help
marker as the owner's answer. Nothing checks who wrote it.

That is not hypothetical: `alvarosantossyngenta` authored 14 issues on the board
repository while the loop was live, and their comments would have been forwarded
as instructions.

GitHub cannot stop this at the repository edge today. The `allow_forking` field
is rejected on public repositories, so the remaining lever is
`pull_request_creation_policy: collaborators_only` (which blocks pull requests
from non-collaborators) plus gating the comments the agent actually reads.

## What Changes

- `taskboard.py` filters forwarded comments and answers by author. The trusted
  set is `GITHUB_TRUSTED_USERS`, rendered from `github_trusted_users` in
  `values/global.yaml.gotmpl` so other components can read the same list, plus
  `TASKBOARD_OWNER`; anything else is dropped and named in `inbox` under
  `ignored`.
- `issue` withholds the body of an untrusted comment, and the branch and
  repository claims are read only from a trusted or machine comment, so the
  context path cannot hand the model the text the queue path drops.
- A `taskboard:` marker counts only on a machine comment, so a stranger cannot
  move the forwarding cursor, fake a session id or fake a question.
- `merge_pending`, `pending_comments` and `help_state` share one `trusted()`
  check, so the issue path, the pull-request path and the `Blocked` answer path
  cannot drift.
- The Hermes deployment states the trusted logins next to the other loop knobs.
- `SKILL.md` says what `ignored` means and forbids forwarding it.

## Impact

- `releases/automation/files/agent/taskboard-loop/taskboard.py`
- `releases/automation/files/agent/taskboard-loop/SKILL.md`
- `releases/automation/values/hermes.yaml.gotmpl`
- `tests/test_taskboard.py`
- `openspec/specs/taskboard-loop/spec.md`
