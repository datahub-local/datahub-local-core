# Spec Delta

## MODIFIED Requirements

### Requirement: Owner comments reach the session exactly once

The tick SHALL forward issue comments, pull-request conversation comments and
pull-request inline review comments through one ordered queue, SHALL send no
comment already covered by the newest `<!-- taskboard:forwarded … -->` marker,
and SHALL write that marker only after the send succeeded. A comment that appears
in more than one collection SHALL be forwarded once.

#### Scenario: The owner reviews the pull request

- **WHEN** a review comment is written after the newest forwarded marker
- **THEN** it is sent to the session with its path and line
- **AND** the marker advances to its timestamp

#### Scenario: The owner writes on the pull request

- **WHEN** a conversation comment is written on the pull request after the newest forwarded marker
- **THEN** it is sent to the session without a path and line
- **AND** the marker advances to its timestamp

#### Scenario: The session is still running

- **WHEN** the owner writes while the session answers `running`
- **THEN** the tick leaves the marker alone
- **AND** the next tick sends the comment

#### Scenario: The agent is busy with another issue

- **WHEN** `run_task` answers `busy` because another issue's turn holds the shim
- **THEN** the tick leaves the marker alone
- **AND** it adds no reaction, because the comment is queued rather than delivered
- **AND** the next tick retries it

## ADDED Requirements

### Requirement: The pull request is found without a Repo section

The helper SHALL resolve the repository from the `## Repo` section when it names
exactly one repository, and otherwise from the newest claim comment naming the
branch's repository. A bare repository name SHALL be prefixed with
`TASKBOARD_ORG`, in `inbox`, `pr` and `review`, because the API path needs a
`<owner>/<repo>` slug.

#### Scenario: The issue has no Repo section

- **WHEN** an issue names no repository but its claim says `Branch \`feat/99-x\` in datahub-local-ai`
- **THEN** `inbox` looks up `datahub-local/datahub-local-ai` and its pull requests
- **AND** it does not report `"repo": null`

#### Scenario: The tick asks for a pull request by bare name

- **WHEN** `pr datahub-local-ai <branch>` is called
- **THEN** the request path is `/repos/datahub-local/datahub-local-ai/pulls`
- **AND** it does not 404 on an owner named after the repository

#### Scenario: Nothing names a repository

- **WHEN** neither the issue nor a claim names one
- **THEN** `inbox` reports no repository and no items
- **AND** it does not guess from another issue

### Requirement: A forwarded comment is acknowledged

After the tick records a successful forward, the helper SHALL react 👀 to every
comment that forward covered. When the send failed with an error, the helper SHALL
instead react 😕 to those comments and SHALL NOT advance the forwarded marker, so
the next tick retries. A `busy` answer from the agent SHALL NOT be treated as a
send failure: it SHALL leave the marker and the reactions untouched. A reaction
failure SHALL be reported and SHALL NOT fail the marker write.

#### Scenario: The session received the comment

- **WHEN** the send succeeded and `forwarded <n> <since>` runs
- **THEN** the marker is written
- **AND** each comment in that window carries an 👀 reaction

#### Scenario: The send failed

- **WHEN** `forwarded <n> <since> --failed` runs
- **THEN** no marker is written
- **AND** each comment in that window carries a 😕 reaction

### Requirement: A queued comment says it is waiting

When the agent answers `busy`, the helper SHALL post one ⏳ note on the pull
request, or on the issue when there is no pull request, SHALL NOT post a second
note while one already exists, and SHALL delete it once the send succeeds or a
real send error is recorded. The note SHALL carry a machine marker so it is never
forwarded as the owner's words.

#### Scenario: The agent is busy

- **WHEN** the tick finds a pending comment and `run_task` answers `busy`
- **THEN** one ⏳ note says the comment is queued
- **AND** the forwarded marker is unchanged

#### Scenario: The comment is finally delivered

- **WHEN** a later tick sends it and runs `forwarded`
- **THEN** the ⏳ note is deleted
- **AND** the owner comment carries the 👀 receipt
