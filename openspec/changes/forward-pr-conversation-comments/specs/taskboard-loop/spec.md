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
