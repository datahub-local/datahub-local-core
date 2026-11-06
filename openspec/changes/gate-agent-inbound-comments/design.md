# Design

## Context

The loop has three ways a person's text reaches a coding session:

| path | function | today |
| --- | --- | --- |
| issue or pull-request comment | `pending_comments`, `merge_pending` | author ignored |
| answer to a question | `help_state` | first non-machine comment wins |
| relay from Slack | `comment --owner` | posted as the owner's login |

The `--owner` relay stays because its author is the owner's login, so the same
gate covers it without a second rule.

## Goals / Non-Goals

**Goals**

- A login that is not configured cannot put a word in front of the session.
- The omission is visible: the tick learns what it dropped instead of guessing.
- One check, used by every path, so a later surface does not reopen the hole.

**Non-Goals**

- Blocking new issues. Only a collaborator can label an issue `agent`, and only
  labelled issues are dispatched.
- Hiding the comments. They stay on GitHub; they just do not reach the model.
- Changing the machine-comment rule. A marker still means "not the owner".

## Decisions

### D1 — Trust lives in one list, rendered from the global values

`TRUSTED_USERS` is `GITHUB_TRUSTED_USERS` plus `TASKBOARD_OWNER`, lowercased.
`GITHUB_TRUSTED_USERS` is rendered from `github_trusted_users` in
`values/global.yaml.gotmpl`, so a component that reads a comment can use the same
logins without a second copy. The environment is only the transport: the list is
reviewable in the repository and shared by every release.

### D2 — The gate is at the queue, not at the read

`pending_comments`, `merge_pending` and `help_state` filter, because those are
the three functions that decide what the session is told. Filtering in
`GitHub.comments` would also hide the dropped comments from the report.

### D3 — `inbox` reports what it dropped, `issue` withholds it

The tick gets `ignored` as a list of `{id, author, url, created_at}` so it can
post one fixed line naming the author and the comment URL. The body is never
forwarded and the line carries a marker, so the tick does not read it back as an
answer.

`issue <n>` is context rather than a queue, and it would otherwise print every
comment body. It returns the metadata with `body: ""` and `withheld: true` for an
untrusted author. The claim regexes read only readable comments, so a stranger
cannot move the pull request lookup to another repository.
