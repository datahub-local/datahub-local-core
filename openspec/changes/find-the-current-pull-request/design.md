# Design

## The link that survives a cycle

A branch belongs to one pull request. `Refs <org>/<repo>#<n>` belongs to the
issue, and the repository's own pull request convention already puts it in the
body. So `pull <n>` lists the pull requests for the issue rather than for a
branch:

- read `/repos/<repo>/pulls?state=all&per_page=100`,
- keep the bodies matching `Refs <REPO>#<n>`,
- sort open first, then by number descending.

`current` is the first of that list. An open pull request outranks a merged one
because a merged pull request from an earlier cycle is history, not work in
progress.

## Fallbacks

Two shapes predate the convention and still have to work:

- A pull request whose body has no `Refs` line: the branch in the claim comment
  is the only key, so `pull_of` falls back to the branch lookup.
- An issue with no `## Repo` section: `repo_of` already reads the claim comment,
  and that is enough for the `pulls` list as long as a repository is named.

## Comments across cycles

`inbox` reads the conversation and review comments of every referencing pull
request. The forwarded marker is a timestamp, and `merge_pending` deduplicates by
comment id, so reading an older pull request costs nothing and catches a reply
left on it after the merge.

## Cost

One `pulls?state=all&per_page=100` call per active issue per tick, plus two
comment calls per referencing pull request. Both surfaces are cheap next to the
ten-minute schedule, and there are rarely more than two pull requests per issue.

## What the tick sees

`pull <n>` returns `current` and `pulls`. Step 5 branches on `current.state` and
`current.merged`, so the tick never has to compare a branch name to the board.
`current.head` is also the branch the agent used, which is what the issue
comment should name when the tick announces the new pull request.
