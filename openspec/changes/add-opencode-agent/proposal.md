# Proposal

## Why

The owner wants a coding agent that is always on, usable from a browser and from Hermes, with GitHub
access and web search. Hermes cannot use it directly: Hermes speaks MCP, and `opencode serve` speaks
its own HTTP API. OpenCode has no MCP server and no HTTP ACP, so the gap is a shim, not a
configuration flag.

The shape also has to survive days: a long-running server, a browser UI, a credential that does not
expire mid-session, and a search tool that is a reviewed surface rather than `webfetch` to any URL.

## What Changes

- Add an `opencode-server` Deployment: `opencode serve` on 4096, state on `/opt/data`, workspace on
  `/workspace`, git installed into the volume, the LiteLLM plugin installed at startup, and a
  **minter sidecar** holding the GitHub App key.
- Add an `opencode-web` Deployment: an nginx reverse proxy to the server, preserving SSE and
  WebSocket; the only workload published through Traefik and dex.
- Add an `opencode-mcp` Deployment: a stateless MCP shim (`run_task`, `get_session`, `respond`,
  `abort_session`) that Hermes and Sympozium personas call.
- Consume the self-hosted Firecrawl MCP bridge from `add-firecrawl-mcp`; no Firecrawl workload, no
  account key, and no `api.firecrawl.dev` egress in this release.
- Add one ConfigMap with `opencode.json`, `AGENTS.md`, and the git credential helper; the config
  names the model, the plugin, Firecrawl, the helper, and the permission ruleset.
- Install `git` into `/opt/data/git` with an init container (`apk --root`) because the image has no
  git and the server keeps a read-only root filesystem.
- Mint GitHub installation tokens on demand in the minter sidecar; git asks it through the helper
  whenever it runs. No credential file, no rotation loop, no PAT in the server.
- Expose the UI at `automation-opencode.<gateway_hostname>` through the existing
  `security/oauth2-proxy-auth` middleware, with a Traefik header injecting the Basic credential.
- Keep `websearch` and `webfetch` disabled; search is the Firecrawl MCP tools only.
- Run the server under `gvisor` on `datahublocal-amd-1` with the restricted profile.
- Register the shim once as a catalog `MCPServer` and add `opencode` to Hermes' `config.mcp_servers`
  with `timeout: 900`.

Not changed: LiteLLM, the existing MCP servers, Hermes' chart, Sympozium's control plane, and every
other release.

## Capabilities

### New Capabilities

- `opencode-agent`: the three-workload topology — server, web proxy, MCP shim — plus
  configuration delivery, the LiteLLM model path, GitHub token minting, git installation,
  permissions, isolation, state, egress, and registration.

### Modified Capabilities

<!-- None. -->

## Impact

- One new release in `releases/automation/` with three workloads, three Services, one IngressRoute,
  one headers Middleware, and one catalog `MCPServer`.
- One ConfigMap rendered from `releases/automation/files/opencode/` (config, instructions, helper).
- Images pinned by digest: the upstream OpenCode image, nginx, and the shim (built in
  `datahub-local-ai-mcp`). No OpenCode-derived image.
- Two Longhorn RWO PVCs for the server.
- Secrets created outside this repository: `github-app` (`app-id`, `installation-id`, `private-key`).
  The LiteLLM key still comes from `automation/litellm-auth-credentials`; the server password is
  derived and rendered into a Secret. Firecrawl needs no key: the self-hosted MCP bridge from
  `add-firecrawl-mcp` is keyless.
- A GitHub App installed on the intended repositories with `contents: write`, `pull_requests:
  write`, `metadata: read`.
- Public egress is not direct: the server sends 443 through the `security` egress proxy deployed by
  `add-egress-proxy`, whose allowlist is PyPI, GitHub, npm and Alpine; everything else is denied.
