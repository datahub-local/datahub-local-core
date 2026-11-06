# Spec Delta

## MODIFIED Requirements

### Requirement: Only marked comments are machine comments

The helper SHALL treat a comment as machine-written when it contains a
`<!-- taskboard:` marker, and SHALL treat any comment without one, posted after the
help marker and authored by a trusted login, as the owner's answer. Author
identity SHALL NOT be used to decide whether a comment is machine-written, and
SHALL be used to decide whether it may reach the session at all.

The trusted set SHALL be `GITHUB_TRUSTED_USERS`, rendered from
`github_trusted_users` in `values/global.yaml.gotmpl`, plus `TASKBOARD_OWNER`, so
a login that is not configured can write on the issue without writing to the
agent.

#### Scenario: Hermes comments after asking a question

- **WHEN** the newest comments after the help marker carry a taskboard marker
- **THEN** the question is reported as unanswered

#### Scenario: The owner answers on the issue

- **WHEN** a comment without a marker from a trusted login exists after the help marker
- **THEN** that comment is reported as the answer
- **AND** the first such comment wins

#### Scenario: A stranger comments on a public issue

- **WHEN** a comment without a marker is authored by a login outside the trusted set
- **THEN** it is not forwarded and does not answer a question
- **AND** `inbox` lists it under `ignored` with its author and URL

#### Scenario: A stranger answers a blocked card

- **WHEN** a card is `Blocked` and only an untrusted login writes after the help marker
- **THEN** the card stays `Blocked`
- **AND** no `respond` is sent to the session

## ADDED Requirements

### Requirement: An untrusted comment is never shown to the model

`inbox` SHALL return every untrusted human comment in the forwarding window under
`ignored`, with its id, author, URL and timestamp, and SHALL NOT include its body
in `items`. `issue` SHALL return every comment's metadata but an empty body for an
untrusted author, marked `withheld: true`. Repository and branch lookup SHALL read
claims only from a machine comment or a trusted login. Marker parsing for the
forwarding cursor, the session id and the help question SHALL read machine
comments only.

#### Scenario: A stranger types a taskboard marker

- **WHEN** an untrusted comment contains `<!-- taskboard:forwarded … -->`,
  `<!-- taskboard:session … -->` or `<!-- taskboard:help -->`
- **THEN** the cursor, the session id and the question state are unchanged
- **AND** the owner's next comment is still forwarded

#### Scenario: The tick reads an inbox with a dropped comment

- **WHEN** `inbox` returns one item and one ignored comment
- **THEN** only the item is sent to the session
- **AND** the tick posts one line naming the ignored author and its URL
- **AND** the marker keeps the next tick from reading that line as an answer

#### Scenario: The tick reads the issue for context

- **WHEN** `issue <n>` is read and an untrusted login commented
- **THEN** that comment's body is empty and `withheld` is true
- **AND** every trusted and machine comment keeps its body

#### Scenario: An untrusted comment names a branch

- **WHEN** an untrusted login writes `Branch \`x\` in other/repo`
- **THEN** `repo_of` and `last_branch` ignore it
- **AND** the pull request lookup uses the trusted claim only
