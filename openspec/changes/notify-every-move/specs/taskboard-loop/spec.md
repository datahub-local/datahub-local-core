# Spec Delta

## REMOVED Requirements

### Requirement: The tick is quiet when nothing moves

**Reason**: The tick already said nothing when nothing moved. The failure was the
opposite: a board write happened and no line was posted, because reporting was
left to the model. The replacement makes the helper post every write and keeps it
silent only when the board did not change.

**Migration**: Use `taskboard.py status`, `finish` and `sync` for every write; they
post the Slack line. Remove prose that asks the model to post move lines.

## ADDED Requirements

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
`<origin>` is `TASKBOARD_OPENCODE_URL` and `<serverKey>` is the FNV-1a hash of that
origin in base36. The link SHALL be built by the helper, not by the model.

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

## MODIFIED Requirements

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
