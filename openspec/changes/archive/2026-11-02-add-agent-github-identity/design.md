# Design

## Context

`github-mcp-server` in http mode authenticates per request from the `Authorization`
header and ignores `GITHUB_PERSONAL_ACCESS_TOKEN`; Hermes injects that header from a
Secret. OpenCode's shell authenticates git through a credential helper and `gh`
through `GITHUB_TOKEN`, both fed from its own Secret. Neither path can carry an App,
because an installation token expires in an hour and neither consumer reloads a
value.

The adapter image already ships `opencode-minter.mjs`: a sidecar that holds the App
key, mints on demand and serves `/token` on loopback. That is the shape both
consumers need.

## Decisions

### 1 — Two identities, one grant

| | manager (Hermes) | coder (OpenCode) |
| --- | --- | --- |
| Organization projects | read/write | none |
| Contents | read | read/write |
| Workflows | none | read/write |
| Issues, Pull requests | read/write | read/write |

The split is by purpose, not by grant: both Apps were created with the same
permissions, because the owner wants Hermes able to make an ad-hoc change without a
second install. The table above is what narrowing would look like, not what runs.

### 2 — The coder mints through the helper it already has

`git-credential-opencode` prefers `GITHUB_TOKEN` and falls back to the minter on
loopback. With the App wired, the variable is removed, so the helper always mints.
`gh` has no credential helper, so a wrapper in the image asks the same helper
(`git credential fill`) and execs the real binary with `GH_TOKEN`. One token source,
two consumers, nothing on disk.

Commits link to the bot only with the App's noreply address, so `gitconfig` carries
`<app-id>+datahub-local-coder[bot]@users.noreply.github.com`.

### 3 — Hermes talks to a proxy, because the header is computed per request

The MCP server cannot read an env token in http mode, and Hermes must not hold the
key. A sidecar in the same pod listens on the Service port, mints the manager's
installation token, and forwards to the MCP server on loopback with the header set.
The server moves to `127.0.0.1:8081`; the Service still publishes 8080.

The proxy answers `/healthz` without minting, so a wrong key does not crash-loop the
pod; the failure appears on the first real call, which is where it is diagnosable.
It mints with `curl` for the same reason the minter does: `fetch` ignores
`HTTPS_PROXY`, and this pod reaches GitHub only through the egress proxy.

### 4 — The old secrets stay until the new path is proven

`opencode-github` and `mcp-github-token` are removed from both pods in this change,
but the Secrets themselves stay in `datahub-local-secrets` until a pull request
authored by the coder is merged. Deleting them first would leave no way back without
a second edit.

## Residuals

- The `<!-- taskboard: -->` marker stays. Attribution no longer needs it, but it
  still distinguishes machine text from an owner comment when someone quotes a
  marker.
- The manager App needs the `Organization projects` permission. A `project` scope on
  a PAT has no App equivalent, so this is a different grant, not a mapping.
