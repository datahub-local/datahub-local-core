# Proposal

## Why

Every pull request, issue comment and review the fleet produces is authored by
`alvsanand`, because both agents authenticate with the owner's personal access
token. The impersonation is not cosmetic: the loop had to invent a
`<!-- taskboard: -->` marker to tell a machine comment from the owner's answer, and a
reviewed pull request reads as if the owner reviewed it.

Two GitHub Apps fix the attribution and shrink the blast radius: a manager for
Hermes, a coder for OpenCode. A coder token cannot move the board, and the pull
request timeline says which agent acted.

## What Changes

- `github-app-manager` and `github-app-coder` roots and derived secrets in
  `datahub-local-secrets`: `GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`,
  `GITHUB_APP_PRIVATE_KEY`. Empty until the Apps exist.
- `opencode-server` runs the existing minter as a sidecar, reads
  `github-app-coder`, and loses `GITHUB_TOKEN`. The git credential helper falls
  back to the minter; `gh` gains a wrapper that asks the same helper, so a pull
  request is opened as the bot.
- The git identity becomes `datahub-local-coder[bot]` with the App's noreply email,
  which is how GitHub links a commit to the App.
- The Hermes GitHub MCP deployment gets a proxy sidecar that holds the manager key
  and injects an installation token into every request, because that server
  authenticates per request and ignores the env token. The MCP server moves to
  loopback and the Service points at the proxy. Hermes' `headers` block and its
  `mcp-github-token` reference go away.

## Capabilities

### New Capabilities

- `agent-github-identity`: which identity writes to GitHub, where its key lives, how
  a token is minted and never stored, and what each identity is allowed to do.

### Modified Capabilities

None. The board, the loop and the shim keep their contracts; only the credential
behind them changes.

## Impact

- `datahub-local-secrets`: two roots and two derived secrets.
- `datahub-local-core`: a sidecar and a proxy, one Service target, one config
  block removed from Hermes, one Secret reference removed.
- `datahub-local-ai`: `gh` wrapper, git identity, and the proxy script in the
  adapter image, therefore a rebuild and a digest bump before this can deploy.
- The `opencode-github` and `mcp-github-token` secrets become unused. They stay in
  place until the new path has produced a real pull request, then go.
