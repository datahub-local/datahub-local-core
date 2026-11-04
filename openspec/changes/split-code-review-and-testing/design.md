# Design

## Two states, two questions

Each status answers one question the owner asks while looking at the board:

- `Code Review`: is a pull request open and waiting for me?
- `Testing`: is the change live and waiting for me to check it?

The pull request's own state drives the first transition, and it is the only signal
the tick needs. The merge drives the second, because the merge is what deploys:
ArgoCD reconciles `main`, so a merged pull request is a change on its way to the
cluster.

```
Ready -> In Progress -> Code Review -> Testing -> Done
             ^                |           |
             +---- owner comment on Testing
```

## Who writes what

- `Code Review` is written by the tick when `pr` reports `open` for the session's
  current branch.
- `Testing` is written by the tick when `pr` reports `merged`.
- `In Progress` is written by the tick when it forwards an owner comment from
  `Testing` (or `Blocked`), the same path that already exists.
- `Done` stays with `finish`, which refuses while the issue is open. The owner
  closes the issue once the change works, and the next tick moves the card.

## A second pull request for the same issue

The old rule said never open a second pull request for an issue. That rule existed
to stop a tick from duplicating work it had already opened. It now has to yield to
the fix loop: when the owner comments on a card in `Testing`, the merged branch is
the wrong place to commit, so the agent cuts a new branch from `main`, comments
`Branch `...` in <repo>` so `last_branch` picks it up, and opens a new pull
request. The tick then treats that pull request like any other: comment the URL,
move to `Code Review`, and move to `Testing` on merge.

To keep the original intent, the rule becomes "never open a second pull request
while one is open". A fix after a merge is a new cycle, not duplication.

## Migration

Cards already in `Testing` whose pull request is still open describe the old
meaning. #99 and #109 were moved to `Code Review` by hand when the column was
introduced. No code migration is needed: once the tick runs, an open pull request
whose card is still in `Testing` is indistinguishable from a post-merge fix, so the
tick leaves it alone and the owner moves it once.
