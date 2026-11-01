# Spec Delta

## ADDED Requirements

### Requirement: The loop's instructions and helper ship from the repository

The tick's instructions, the script that reads and writes the board, and the
schedule that runs them SHALL be declared in `datahub-local-core` and applied by
the `hermes` and umbrella releases, so a fresh or restored `HERMES_HOME` comes up
with the loop in place and the owner's other scheduled jobs untouched.

#### Scenario: Hermes starts with a fresh volume

- **WHEN** the Pod starts with no `cron/jobs.json`
- **THEN** the init container creates the `taskboard-tick` job
- **AND** the skill directory is present from the mounted ConfigMap

#### Scenario: Hermes restarts with the job already scheduled

- **WHEN** the job exists in `jobs.json`
- **THEN** the init container leaves the file unchanged
- **AND** no duplicate job is created

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

### Requirement: The tick is quiet when nothing moves

The scheduled job SHALL deliver locally rather than to a chat, and SHALL post to
Slack only for events it acts on.

#### Scenario: Nothing is ready

- **WHEN** no issue is `Ready` and no session changed state
- **THEN** the tick posts nothing to Slack
- **AND** it changes no status

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
