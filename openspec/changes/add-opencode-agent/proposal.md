# Proposal

## Why

The owner wants a coding agent that is always on, usable from a browser and from Hermes, with GitHub
access and web search. Hermes cannot use it directly: Hermes speaks MCP, and `opencode serve` speaks
its own HTTP API. OpenCode has no MCP server and no HTTP ACP, so the gap is a shim, not a
configuration flag.

The shape also has to survive days: a long-running server, a browser UI, a credential that does not
expire mid-session, and a search tool that is a reviewed surface rather than `webfetch` to any URL.

The upstream image cannot do the job. `ghcr.io/anomalyco/opencode` is Alpine 3.23 with `libgcc`,
`libstdc++` and one musl Bun binary: no `git`, `curl`, `ssh`, `helm`, `helmfile`, `uv` or `python`.
The agent's work lives in the DataHub.local repositories — a helmfile release, a uv project, a test
suite — so an image that cannot run those tools is a chat box. The first design installed `git` at
startup and left everything else missing. This change makes the image the toolchain.

## What Changes

- Build `ghcr.io/datahub-local/datahub-local-ai-opencode-adapter` in
  `datahub-local-ai/agents/adapters/opencode/`: Debian bookworm, the pinned upstream OpenCode Linux
  release binary, and every tool the repositories use — `git`, `bash`, `curl`, `openssh-client`,
  `ca-certificates`, `jq`, `yq`, `kubectl`, `helm`, `helmfile`, `kustomize`, `gh`, `node`/`npm`,
  `python3` + `venv`/`pip`, and `uv` with a managed Python 3.13. `ansible`, `dbt` and `dlt` are
  project dependencies and arrive through `uv sync` in the repository that needs them.
- Add an `opencode-server` Deployment: `opencode serve` on 4096, state on `/opt/data`, workspace on
  `/workspace`, LiteLLM declared as the only provider, and the coder App's minter as a sidecar.
- Add an `opencode-web` Deployment: an nginx reverse proxy to the server, preserving SSE and
  WebSocket; the only workload published through Traefik and dex.
- Add an `opencode-mcp` Deployment: a stateless MCP shim (`run_task`, `get_session`, `get_diff`,
  `list_sessions`, `get_transcript`, `respond`, `abort_session`) that Hermes and Sympozium personas
  call.
- Remove the `apk --root` git install. The image ships `git`, the Pod has no init container, and no
  root process at all.
- Consume the self-hosted Firecrawl MCP bridge from `add-firecrawl-mcp`; no Firecrawl workload, no
  account key, and no `api.firecrawl.dev` egress in this release.
- Bake `opencode.json`, `AGENTS.md`, the skills directory, `gitconfig`, the git credential helper,
  the `gh` wrapper and the token minter into the adapter image (`/etc/opencode`, `/etc/gitconfig`,
  `/usr/local/bin`); the config names the two models, the reviewer subagent, the LiteLLM provider,
  the Firecrawl and Kubernetes bridges, the skills path, and the permission ruleset.
- Extend the `egress-proxy` allowlist with the helm chart repositories and OCI registries a
  `helmfile template` in these repositories needs, including the hosts their redirects land on.
- Run the coder GitHub App's minter as a sidecar: the server reads `github-app-coder`, the git
  helper and `gh` wrapper ask it for installation tokens, and no container reads `github-root`.
  The App itself, its roots and the Hermes proxy belong to `agent-github-identity`.
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

- `opencode-agent`: the three-workload topology — server, web proxy, MCP shim — plus the image and
  its toolchain, configuration delivery, the LiteLLM model path, GitHub token minting, permissions,
  isolation, state, egress, and registration.

### Modified Capabilities

- `egress-proxy`: the domain allowlist gains a `helm` group for the chart repositories and OCI
  registries the agent's `helmfile` runs resolve against.

## Impact

- One new release in `releases/automation/` with three workloads, three Services, one IngressRoute,
  one headers Middleware, and one catalog `MCPServer`.
- The agent's config, instructions, skills, git files, wrappers and minter in the adapter image;
  nothing of theirs in a ConfigMap, because `/opt/data` is a volume and would hide them.
- One new image in `datahub-local-ai/agents/adapters/opencode/`, built multi-arch and published by
  that repository's `publish-images.yaml`; the cluster pins it by digest. nginx and the shim stay
  digest-pinned too. No upstream OpenCode image is deployed.
- Two Longhorn RWO PVCs for the server.
- A Secret created outside this repository: `github-app-coder` (`GITHUB_APP_ID`,
  `GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY`), owned by `agent-github-identity`. The
  LiteLLM key comes from `automation/litellm-auth-credentials`; the server password is derived.
  Firecrawl needs no key.
- No credential root or key in a container: installation tokens are minted on demand and never
  written to disk. SSH deploy keys stay unused because GitHub cannot attach one key to the
  three-repository workspace.
- Public egress is not direct: the server sends 443 through the `security` egress proxy deployed by
  `add-egress-proxy`, whose allowlist is PyPI, GitHub, npm, helm chart repositories and their OCI
  registries; everything else is denied.
