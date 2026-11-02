# taskboard-slack Specification

## Purpose

Read and move the GitHub Project board from Slack, where the work is discussed. The owner lists a column, moves a card or comments on an issue through `/hermes board ...` or a plain message, and Hermes answers by running the same `taskboard.py` the scheduled tick uses. One helper, one token path, and a chat request that never starts a tick.

## Requirements

### Requirement: The owner lists and moves the board from Slack

Hermes SHALL answer a board request written in Slack by running one `taskboard.py`
subcommand: list a column, show one issue, move an issue's Status, or comment on it.

#### Scenario: Listing a column

- **WHEN** the owner asks what is in `In Progress`
- **THEN** the reply names the open agent issues in that column, with links
- **AND** no other column is listed

#### Scenario: Moving a card

- **WHEN** the owner asks to move issue 116 to `Ready`
- **THEN** the Status field of that item is set through `taskboard.py`
- **AND** the reply names the status it moved from

#### Scenario: Moving a card that is already there

- **WHEN** the target status equals the current one
- **THEN** no write is sent to GitHub
- **AND** the reply says the card is already in that column

#### Scenario: A dictated comment

- **WHEN** the owner dictates a comment for issue 116
- **THEN** it is posted with `--owner`
- **AND** it carries no `<!-- taskboard:` marker, so the tick reads it as the
  owner's words

#### Scenario: A status that does not exist

- **WHEN** the requested status is not one of the six options
- **THEN** Hermes asks once instead of writing
- **AND** nothing on the board changes

#### Scenario: An unclear request

- **WHEN** the message names no issue, or two, or no status
- **THEN** Hermes asks one question and stops
- **AND** it does not pick the only card in a column

### Requirement: Slack exposes one command, and `board` names this surface

The Slack app manifest SHALL declare `/hermes` as its only slash command, and board
requests SHALL carry `board` as the first word after it, so the surface is named
without competing with the Hermes subcommands.

#### Scenario: The command menu

- **WHEN** a person opens Slack's slash command list in the workspace
- **THEN** Hermes contributes one entry, `/hermes`
- **AND** the fifty native commands are reachable as `/hermes <subcommand>`

#### Scenario: A prefixed board request

- **WHEN** the owner sends `/hermes board move 116 ready`
- **THEN** the first word after `/hermes` is `board`, which is not a Hermes
  subcommand, so the text reaches the board skill as a regular message

#### Scenario: A Hermes subcommand is not a board request

- **WHEN** the owner sends `/hermes status`
- **THEN** Hermes answers its own status command
- **AND** the board skill does not run, even though "status" is also a board word

### Requirement: A board request is not a tick

The instructions that answer a chat request SHALL NOT run `sync`, start a session,
forward comments, or move any issue the message did not name, and they SHALL be a
separate skill from the scheduled tick so the tick's dispatch steps never load for a
chat message.

#### Scenario: A request in the middle of the loop

- **WHEN** the owner asks for a column while other issues are `Ready`
- **THEN** no session starts and no card moves
- **AND** the reply is the listing only

#### Scenario: The tick skill is chosen for a chat message

- **WHEN** the board skill is missing or not selected
- **THEN** the reply must not dispatch work, because the tick's steps exist only in
  the tick's own skill

### Requirement: The board helper authenticates without a token in the Pod

`taskboard.py` SHALL use an exported `GITHUB_PERSONAL_ACCESS_TOKEN` when present and
otherwise mint an installation token from the sidecar at `MINTER_URL`, and SHALL
fail with one clear error when neither is available.

#### Scenario: The sidecar is the only credential

- **WHEN** no token is exported and `MINTER_URL` answers
- **THEN** the helper uses the minted token for the call
- **AND** no token is written to disk

#### Scenario: The mint fails

- **WHEN** the sidecar is down or returns no token
- **THEN** the helper exits with an error naming the failure
- **AND** it does not fall back to an unauthenticated call

#### Scenario: A local run exports a token

- **WHEN** `GITHUB_PERSONAL_ACCESS_TOKEN` is set
- **THEN** the helper uses it and never contacts the sidecar
