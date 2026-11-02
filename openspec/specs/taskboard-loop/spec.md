# taskboard-loop Specification

## Purpose

The scheduled loop that turns a `Ready` issue into a pull request: it reads the
GitHub project board, dispatches one coding-agent session, forwards the owner's
comments, and moves the card, with its instructions and helper shipped from this
repository rather than living on the Hermes volume.

## Requirements

### Requirement: The loop's instructions and helper ship from the repository

The tick's instructions, the script that reads and writes the board, and the
schedule that runs them SHALL be declared in `datahub-local-core` and applied by
the `hermes` and umbrella releases, so a fresh or restored `HERMES_HOME` comes up
with the loop in place and the owner's other scheduled jobs untouched.

#### Scenario: Hermes starts with a fresh volume

- **WHEN** the gateway starts with no `cron/jobs.json`, or with one that lacks the job
- **THEN** the `gateway:startup` hook creates the `taskboard-tick` job
- **AND** the skill directory is present from the mounted ConfigMap

#### Scenario: Hermes restarts with the job already scheduled

- **WHEN** the job exists in `jobs.json`
- **THEN** the hook leaves the file unchanged
- **AND** no duplicate job is created

#### Scenario: The hook cannot create the job

- **WHEN** `hermes cron create` fails or `jobs.json` cannot be parsed
- **THEN** the hook logs the outcome and the gateway starts anyway
- **AND** it never writes into a file it could not read

### Requirement: Only marked comments are machine comments

The helper SHALL treat a comment as machine-written when it contains a
`<!-- taskboard:` marker, and SHALL treat any comment without one, posted after the
help marker, as the owner's answer. Author identity SHALL NOT be used for this
decision, because every machine comment is posted with the owner's token.

#### Scenario: Hermes comments after asking a question

- **WHEN** the newest comments after the help marker carry a taskboard marker
- **THEN** the question is reported as unanswered

#### Scenario: The owner answers on the issue

- **WHEN** a comment without a marker exists after the help marker
- **THEN** that comment is reported as the answer
- **AND** the first such comment wins

### Requirement: A failed dispatch is not a blocked task

When the shim is unreachable or a turn fails, the tick SHALL report the failure on
the issue and SHALL NOT set `Blocked`, which is reserved for a task waiting on the
owner's answer.

#### Scenario: The opencode shim is down

- **WHEN** the dispatch call returns a transport error
- **THEN** the issue keeps its status
- **AND** the error is posted on the issue and reported once

### Requirement: An issue labelled agent reaches the board

The tick SHALL add every open issue carrying the `agent` label that is not on the
project to the project before reading its status, because the project's own
automation only adds sub-issues and a new taskboard issue would otherwise stay
invisible.

#### Scenario: A new issue is created with the agent label

- **WHEN** an open issue with `agent` is not among the project's items
- **THEN** the tick adds it, at `Backlog`
- **AND** the same tick does not also dispatch it

### Requirement: Dispatch stops at the shim's limit, not at a count of its own

The tick SHALL dispatch ready issues in order and SHALL stop at the first `busy`,
treating the shim's configured concurrency as the only cap. It SHALL pass the
repository name as the session directory when the issue names exactly one
repository.

#### Scenario: The agent is full

- **WHEN** `run_task` answers `status: busy`
- **THEN** the tick dispatches no further issues this run
- **AND** it neither comments nor changes a status because of the refusal

### Requirement: A blocked report is not a missing pull request

A turn that ends `BLOCKED` without asking a question SHALL be reported as blocked:
the issue gets the reason and what would unblock it, the status becomes `Blocked`,
and the owner is told once. The tick SHALL NOT report it as a branch without a pull
request, which is the shape of a different failure.

#### Scenario: The agent cannot continue

- **WHEN** an idle session's report begins with `BLOCKED`
- **THEN** the issue is `Blocked` with the reason on it
- **AND** no pull-request lookup decides the outcome

### Requirement: An answer relayed from Slack is the owner's answer

The owner MAY answer in Slack. Hermes SHALL relay that text on the issue verbatim
and without a taskboard marker, so the tick reads it as the answer and resumes the
session, exactly as if the owner had typed it on the issue.

#### Scenario: The owner answers in Slack

- **WHEN** the owner gives the answer in a chat and Hermes posts it on the issue
- **THEN** the comment carries no marker
- **AND** the next tick forwards it with `respond` and sets `In Progress`

### Requirement: Owner comments reach the session exactly once

The tick SHALL forward issue comments and pull-request review comments through one
ordered queue, SHALL send no comment already covered by the newest
`<!-- taskboard:forwarded … -->` marker, and SHALL write that marker only after
the send succeeded.

#### Scenario: The owner reviews the pull request

- **WHEN** a review comment is written after the newest forwarded marker
- **THEN** it is sent to the session with its path and line
- **AND** the marker advances to its timestamp

#### Scenario: The session is still running

- **WHEN** the owner writes while the session answers `running`
- **THEN** the tick leaves the marker alone
- **AND** the next tick sends the comment

### Requirement: The tick's work list comes from the board

Every run SHALL read the set of issues it acts on from the project board, because a
scheduled session has no memory of the previous one. The list SHALL contain every
open, agent-labelled issue that is not `Done`, with its status and issue state, so
that the comment, question, blocked and pull-request steps have something to
iterate.

#### Scenario: A tick starts

- **WHEN** the job runs
- **THEN** it reads the board before acting
- **AND** every issue it touches came from that list or from the dispatch step

#### Scenario: An issue is closed but its status is not Done

- **WHEN** a board item's issue is closed and its status is still `Testing`
- **THEN** the tick sets `Done` before anything else looks at the item

### Requirement: A tick ends before the work does

The dispatch SHALL return as soon as the session exists, or after at most a
120-second wait, SHALL record the session and the status, and SHALL NOT hold the
tick open for the turn. The wait exists to catch a question the agent asks before
it starts editing; a turn that outlives it returns `running` and a later tick
polls it. A tick SHALL stop after a bounded number of tool calls, because the next
tick is ten minutes away and a wandering tick holds the only agent.

#### Scenario: A dispatched turn runs for minutes

- **WHEN** `run_task` answers `running` after its wait
- **THEN** the tick records the session, sets `In Progress` and ends
- **AND** a later tick polls it with `get_session`

#### Scenario: The turn asks before it runs long

- **WHEN** `run_task` answers `needs_input` after its wait
- **THEN** the tick records the session, publishes the question and sets `Blocked`
- **AND** the next tick does not treat the turn as still running

#### Scenario: The tick starts investigating the cluster

- **WHEN** the tick has made twenty tool calls without finishing
- **THEN** it posts what moved and ends
- **AND** it does not use `execute_code`, which cron mode blocks

### Requirement: Done needs a closed issue

The helper SHALL refuse to set `Done` while the issue is open, however many merged
pull requests reference it, and the tick SHALL reach `Done` only through `finish`,
which reads the issue state first. The owner MAY still move a card to `Done` by hand.

#### Scenario: An open umbrella issue with merged pull requests

- **WHEN** an open issue is referenced by merged pull requests and its status is `Testing`
- **THEN** `finish` refuses and reports the issue state
- **AND** the card stays in `Testing`

#### Scenario: The issue is closed

- **WHEN** the issue state is `CLOSED`
- **THEN** `finish` sets `Done` and reports the status it moved from

### Requirement: A report carries the agent's identity

The tick SHALL post its Slack lines with Hermes' own bot token, so the author of the
message is the agent that did the work, and SHALL NOT post reports through the
Sympozium Slack server, whose bot belongs to a different app. The token SHALL be
passed on stdin rather than argv, because `/proc` exposes process arguments.

#### Scenario: A card moves

- **WHEN** the tick posts a status line
- **THEN** the Slack message is authored by the Hermes app
- **AND** it lands in the channel Hermes reads for answers

### Requirement: Every board write is announced in Slack

`taskboard.py` SHALL post one Slack line for every write it performs: a card added
to the project at `Backlog`, and every status change to `In Progress`, `Blocked`,
`Testing` or `Done`. The line SHALL name the issue, the previous and new status,
the title and the issue URL, and SHALL append the OpenCode session link when the
issue records a session. A write that changes nothing SHALL post nothing.

The line SHALL be posted by the command that writes the board, after the GitHub
call succeeds, so a model that forgets to report cannot hide the change. A Slack
failure SHALL NOT fail the write; the command SHALL report `notified: false` and
print the reason, because the card has already moved and a retry would duplicate
it.

#### Scenario: A Ready issue is dispatched

- **WHEN** the tick records the session and sets `In Progress`
- **THEN** one Slack line says `Ready → In Progress` and links the issue and the session
- **AND** no second line is posted for the same move

#### Scenario: The status is already the target

- **WHEN** `status` is called with the status the card already has
- **THEN** no GitHub write and no Slack line are sent

#### Scenario: A new agent issue appears

- **WHEN** `sync` adds an issue to the board at `Backlog`
- **THEN** one Slack line names the issue and its link

### Requirement: A question carries the session link

When a session reports `needs_input`, the tick SHALL post the question and its
options as an issue comment and SHALL post the same text to Slack. Both SHALL carry
the issue URL and the full OpenCode session URL, so the owner can answer in
writing or open the session and select an option. The issue comment SHALL keep the
`<!-- taskboard:help -->` marker; the Slack copy SHALL NOT.

The session URL SHALL be `<origin>/server/<serverKey>/session/<sessionID>`, where
`<origin>` is `TASKBOARD_OPENCODE_URL` and `<serverKey>` is that origin encoded as
base64url without padding. The link SHALL be built by the helper, not by the
model.

#### Scenario: The agent asks a question

- **WHEN** the session state is `needs_input`
- **THEN** the issue comment and the Slack message both contain the question, the options and the session URL
- **AND** the card moves to `Blocked` and that move also posts its line

#### Scenario: The dispatch itself returns a question

- **WHEN** `run_task` answers `needs_input` within its wait
- **THEN** the session is recorded, the question is published, and the card moves from `Ready` to `Blocked`
- **AND** the tick does not also dispatch the next ready issue if the agent is busy

#### Scenario: No web origin is configured

- **WHEN** `TASKBOARD_OPENCODE_URL` is empty
- **THEN** the issue and Slack text carry the issue URL but no session URL
- **AND** the helper does not invent an origin

### Requirement: A pull request link is complete in the issue comment

The issue comment that announces a pull request or a merge SHALL carry the full
`https://github.com/<org>/<repo>/pull/<number>` URL, not only the number or a
branch name. Pull request and merge events SHALL NOT add a separate Slack line;
GitHub already notifies on them, and Slack only carries board writes and
questions.

#### Scenario: The pull request opens

- **WHEN** the tick finds an open pull request for the session's branch
- **THEN** the issue comment contains the full pull request URL and what changed
- **AND** the card moves to `Testing`, which posts the Slack line

#### Scenario: The pull request merges

- **WHEN** the pull request is merged and the issue is closed
- **THEN** the issue comment contains the full pull request URL
- **AND** `finish` moves the card to `Done` and posts the Slack line
