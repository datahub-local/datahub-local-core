# Spec Delta

## MODIFIED Requirements

### Requirement: The tick's work list comes from the board

Every run SHALL read the set of issues it acts on from the project board, because a
scheduled session has no memory of the previous one. The list SHALL contain every
open, agent-labelled issue that is not `Done`, with its status and issue state, so
that the comment, question, blocked and pull-request steps have something to
iterate. The list SHALL order `Code Review` before `Testing`, because an open pull
request is closer to the owner than a change already deployed.

#### Scenario: A tick starts

- **WHEN** the job runs
- **THEN** it reads the board before acting
- **AND** every issue it touches came from that list or from the dispatch step

#### Scenario: An issue is closed but its status is not Done

- **WHEN** a board item's issue is closed and its status is still `Code Review` or `Testing`
- **THEN** the tick sets `Done` before anything else looks at the item

### Requirement: Done needs a closed issue

The helper SHALL refuse to set `Done` while the issue is open, however many merged
pull requests reference it, and the tick SHALL reach `Done` only through `finish`,
which reads the issue state first. The owner MAY still move a card to `Done` by hand.
A merged pull request SHALL NOT close the issue or move the card to `Done`: the merge
is the deploy, and the owner closes the issue once the change works.

#### Scenario: An open umbrella issue with merged pull requests

- **WHEN** an open issue is referenced by merged pull requests and its status is `Code Review` or `Testing`
- **THEN** `finish` refuses and reports the issue state
- **AND** the card keeps its status

#### Scenario: The issue is closed

- **WHEN** the issue state is `CLOSED`
- **THEN** `finish` sets `Done` and reports the status it moved from

### Requirement: A pull request link is complete in the issue comment

The issue comment that announces a pull request or a merge SHALL carry the full
`https://github.com/<org>/<repo>/pull/<number>` URL, not only the number or a
branch name. Pull request and merge events SHALL NOT add a separate Slack line;
GitHub already notifies on them, and Slack only carries board writes and
questions.

#### Scenario: The pull request opens

- **WHEN** the tick finds an open pull request for the session's branch
- **THEN** the issue comment contains the full pull request URL and what changed
- **AND** the card moves to `Code Review`, which posts the Slack line

#### Scenario: The pull request merges

- **WHEN** the pull request is merged and the issue is still open
- **THEN** the issue comment contains the full pull request URL
- **AND** `status` moves the card from `Code Review` to `Testing` and posts the Slack line

#### Scenario: A fix merges while the owner is testing

- **WHEN** a merged pull request is seen on a card already in `Testing`
- **THEN** only the merge comment is written
- **AND** the card stays in `Testing`

## ADDED Requirements

### Requirement: Code Review holds the open pull request, Testing holds the deployed change

The board SHALL carry `Code Review` while a pull request is open and `Testing`
after it merges, so the owner can tell review from verification. A comment on a
card in `Testing` SHALL move it to `In Progress`, and the agent SHALL cut a new
branch from `main` and open a new pull request for the fix, which returns the card
to `Code Review` and to `Testing` on merge.

#### Scenario: The owner reviews a pull request

- **WHEN** a pull request opens and its card is `In Progress`
- **THEN** the card moves to `Code Review`
- **AND** the owner merges from there

#### Scenario: The change is live and the owner tests it

- **WHEN** the pull request merges
- **THEN** the card moves to `Testing`
- **AND** it stays there while the owner runs the change on the cluster

#### Scenario: Testing finds a problem

- **WHEN** the owner comments on an issue whose card is `Testing`
- **THEN** the comment is forwarded and the card moves to `In Progress`
- **AND** the agent opens a new pull request from a new branch, which moves the card to `Code Review`

#### Scenario: A second pull request while one is open

- **WHEN** the agent is asked to change code and its previous pull request is still open
- **THEN** it pushes to that branch instead of opening another
- **AND** only a merged pull request gives the issue a second branch
