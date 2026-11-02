# agent-github-identity Specification

## Purpose
Give each agent its own GitHub identity, so what it writes is attributed to it, the
key it holds is scoped to what it does, and no long-lived personal token sits in a
pod.

## Requirements

### Requirement: Each agent writes as its own App

The fleet SHALL have two GitHub Apps: a manager for Hermes and a coder for OpenCode.
Every commit, pull request, issue comment and review SHALL be authored by the App of
the agent that produced it, and no agent SHALL authenticate with the owner's
personal access token.

#### Scenario: The coder opens a pull request

- **WHEN** OpenCode creates a pull request
- **THEN** the author is the coder App's bot
- **AND** the commits carry the coder's noreply address

#### Scenario: The manager comments on an issue

- **WHEN** Hermes posts a question or a status
- **THEN** the author is the manager App's bot
- **AND** the owner's name appears only where the owner wrote

### Requirement: A key is held only by the process that mints from it

The App private keys SHALL live only in the secrets repository and in the pods that
mint tokens. Hermes SHALL NOT hold a GitHub credential: its MCP server SHALL receive
a token per request from a proxy that holds the manager key.

#### Scenario: Hermes calls a GitHub tool

- **WHEN** Hermes sends a request to the GitHub MCP server
- **THEN** the proxy adds a freshly minted installation token
- **AND** the Hermes pod contains no key and no token in its config

#### Scenario: The coder pushes

- **WHEN** git asks for a credential
- **THEN** the helper mints an installation token on loopback
- **AND** nothing is written to disk

### Requirement: A token is minted for the operation, never stored

Installation tokens SHALL be minted on demand, cached in memory only, and refreshed
before they expire, so a session that runs for days still has a live credential.

#### Scenario: A session outlives a token

- **WHEN** the cached token has less than ten minutes left
- **THEN** the next request mints a new one
- **AND** the caller sees no interruption

### Requirement: The grants are recorded and can be narrowed

The fleet SHALL run two Apps, so a write is attributed to the agent that made it.
Their grants SHALL be stated here rather than assumed, and SHALL NOT include
administration, members or secrets.

Both Apps currently carry the same set: contents, workflows, issues, pull requests
and organization projects, all read/write. That is deliberate. The owner wants
Hermes to make a change on request without a third install or a permission round
trip, and none of the code paths require the difference.

Narrowing is available without code changes: nothing in the coder path calls the
Projects API, and nothing in the manager path writes a file.

#### Scenario: A coder token is used against the board

- **WHEN** a coder installation token calls the Projects API
- **THEN** the call succeeds today, because the grant is shared
- **AND** the coder can be restricted to no organization-projects permission at any
  time, with no change outside the App settings

#### Scenario: A grant is changed

- **WHEN** either App's permissions are narrowed or widened
- **THEN** this requirement is updated in the same week
- **AND** the installation is re-approved, or the change does not take effect
