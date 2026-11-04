# Spec Delta

## MODIFIED Requirements

### Requirement: A pull request link is complete in the issue comment

The issue comment that announces a pull request or a merge SHALL carry the full
`https://github.com/<org>/<repo>/pull/<number>` URL, not only the number or a
branch name. A pull request the issue already carries SHALL NOT be announced a
second time: a fix round on an open pull request is reported by the agent's own
comment, which names what changed and the gate result. Pull request and merge
events SHALL NOT add a separate Slack line; GitHub already notifies on them, and
Slack only carries board writes and questions.

#### Scenario: The pull request opens

- **WHEN** the tick finds an open pull request the issue does not mention
- **THEN** the issue comment contains the full pull request URL and what changed
- **AND** the card moves to `Code Review`, which posts the Slack line

#### Scenario: A fix is pushed to an open pull request

- **WHEN** the tick finds an open pull request whose URL the issue already carries
- **THEN** it does not repeat the URL
- **AND** the card still moves to `Code Review`, because the agent's comment is the record

#### Scenario: The pull request merges

- **WHEN** the pull request is merged and the issue is still open
- **THEN** the issue comment contains the full pull request URL
- **AND** `status` moves the card from `Code Review` to `Testing` and posts the Slack line
