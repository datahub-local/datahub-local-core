# Spec Delta

## MODIFIED Requirements

### Requirement: Owner comments reach the session exactly once

The tick SHALL forward issue comments and the comments of every pull request that
references the issue through one ordered queue, SHALL send no comment already
covered by the newest `<!-- taskboard:forwarded … -->` marker, and SHALL write
that marker only after the send succeeded.

#### Scenario: The owner reviews the pull request

- **WHEN** a review comment is written after the newest forwarded marker
- **THEN** it is sent to the session with its path and line
- **AND** the marker advances to its timestamp

#### Scenario: The owner replies on a pull request from an earlier cycle

- **WHEN** the issue has a merged pull request and an open one, and the owner writes on the merged one
- **THEN** the comment is sent to the session
- **AND** the marker advances to its timestamp

#### Scenario: The session is still running

- **WHEN** the owner writes while the session answers `running`
- **THEN** the tick leaves the marker alone
- **AND** the next tick sends the comment

## ADDED Requirements

### Requirement: The current pull request is the one that references the issue

The tick SHALL resolve the pull request an issue is working on from the
`Refs <org>/<repo>#<n>` line in pull request bodies, because a branch names one
cycle and an issue can have several. An open pull request SHALL outrank a merged
one, and the branch in the claim comment SHALL be the fallback only when no pull
request references the issue.

#### Scenario: A fix follows a merge

- **WHEN** an issue has a merged pull request and a newer open one, both carrying the `Refs` line
- **THEN** `pull <n>` reports the open one as `current`
- **AND** the tick comments that pull request's URL and sets `Code Review`

#### Scenario: The pull request has no Refs line

- **WHEN** no pull request body references the issue
- **THEN** the branch in the newest claim comment is used to find it

#### Scenario: A pull request comment names a branch

- **WHEN** a pull request comment writes `(branch \`x\`)` in lowercase
- **THEN** the branch is read as the newest one

#### Scenario: The merge of an earlier cycle is seen first

- **WHEN** the merged pull request and the open one both reference the issue
- **THEN** the tick does not set `Testing` while the open pull request exists
