# Spec Delta

## ADDED Requirements

### Requirement: The server runs the datahub-local OpenCode image

The `opencode-server` workload SHALL run
`ghcr.io/datahub-local/datahub-local-ai-opencode-adapter` by digest, pinned in
`values/_version.yaml`. The image SHALL be built in `datahub-local-ai/agents/adapters/opencode/`
from a Debian bookworm base with the pinned upstream OpenCode Linux release binary copied in. The
release SHALL NOT deploy `ghcr.io/anomalyco/opencode` or any other upstream OpenCode image. LiteLLM
SHALL be a provider declared in `opencode.json`, not a plugin: there is no package to install, no
cache to warm and no init container.

#### Scenario: The image is ours and pinned

- **WHEN** the rendered Pod spec is inspected
- **THEN** the server image is `ghcr.io/datahub-local/datahub-local-ai-opencode-adapter` by digest
- **AND** no upstream OpenCode image is referenced anywhere in the release

#### Scenario: The Pod has no init container

- **WHEN** the rendered Pod spec is inspected
- **THEN** the server Pod has no init container and no plugin cache to fill

### Requirement: The image carries the platform toolchain

The image SHALL provide, on `PATH` and as a non-root user under a read-only root filesystem:
`git`, `bash`, `curl`, `openssh-client`, `ca-certificates`, `jq`, `yq`, `kubectl`, `helm`,
`helmfile`, `kustomize`, `gh`, `node`/`npm`, `python3` with `venv` and `pip`, and `uv` with a
managed Python 3.13. Every tool SHALL be installed at build time from a pinned version; nothing
SHALL be installed at container start, and no container SHALL run `apk`, `apt` or an installer.

`ansible`, `dbt`, `dlt` and other project dependencies SHALL NOT be baked into the image; they
SHALL be resolved by `uv sync` from the checkout's lockfile. The image SHALL be published for
`linux/amd64` and `linux/arm64`, and tool versions SHALL be tracked by Renovate in
`datahub-local-ai/renovate.json`.

#### Scenario: The agent can run the repositories' own checks

- **WHEN** the agent runs `helmfile template` in a `datahub-local-core` checkout and `uv sync` in a
  `datahub-local-ai` checkout
- **THEN** both commands run with the tools already in the image
- **AND** no package is installed by a root process

#### Scenario: The image is the only toolchain

- **WHEN** the rendered Pod spec is inspected
- **THEN** there is no `apk --root` init container and no init container at all
- **AND** every long-running container starts as uid 1000 with a read-only root filesystem

#### Scenario: A version bump reaches the cluster by digest

- **WHEN** Renovate raises the OpenCode `ARG` in `datahub-local-ai` and that PR merges
- **THEN** `publish-images.yaml` builds and publishes a new multi-arch digest
- **AND** Renovate in this repository changes `values/_version.yaml` to that digest
- **AND** the release never deploys a moving tag

### Requirement: The image carries the agent's config, instructions and git files

The adapter image SHALL carry `opencode.json` at `/etc/opencode/opencode.json` (the OpenCode v2
system configuration directory), `AGENTS.md` at `/opt/opencode/AGENTS.md` and referenced from the
config's `instructions`, `gitconfig` at `/etc/gitconfig`, the credential helper at
`/usr/local/bin/git-credential-opencode` (mode `0755`), the token minter at
`/usr/local/bin/opencode-minter.mjs`. The release SHALL NOT ship those files in a ConfigMap and
SHALL NOT mount them under `/opt/data`, because the state volume is mounted there and hides what the
image carries.

The config SHALL use the v2 shapes: `permissions` as ordered `{action, resource, effect}` rules,
`mcp.servers`, `providers.litellm` with the `@opencode/ai/providers/openai-compatible` package,
`enabled_providers: ["litellm"]`, `update: "disable"`, the default model, and the Firecrawl
server. The Firecrawl URL SHALL be `{env:OPENCODE_FIRECRAWL_MCP_URL}`, the one
cluster-specific value.

#### Scenario: The files survive the state volume

- **WHEN** the server Pod mounts `/opt/data` and starts
- **THEN** the config, the instructions, `gitconfig`, an executable helper and the minter are read
  from the image
- **AND** no ConfigMap in the release carries any of them

### Requirement: LiteLLM is the only model path

`LITELLM_BASE_URL` SHALL name the `data` release's LiteLLM `/v1` endpoint and `LITELLM_API_KEY`
SHALL come from `litellm-auth-credentials` by reference. The default model SHALL be
`litellm/opencode-go/deepseek-v4.1-flash`.

#### Scenario: Only litellm models are selectable

- **WHEN** the agent lists its models
- **THEN** every entry is prefixed `litellm/`
- **AND** no other provider is enabled, including `github-copilot` (which a `GITHUB_TOKEN` in the environment would otherwise activate)

#### Scenario: A turn is served by LiteLLM

- **WHEN** a task reaches the server
- **THEN** the request is served by the in-cluster LiteLLM Service

### Requirement: The server is internal-only and requires Basic auth

`opencode serve` SHALL bind `0.0.0.0:4096` and SHALL require `OPENCODE_SERVER_PASSWORD`. Its Service
SHALL accept connections only from the web-proxy Pod and the MCP-shim Pod. No IngressRoute SHALL
target the server; the web proxy is the only published surface.

#### Scenario: Nothing else reaches the server

- **WHEN** a Pod outside the proxy and shim connects to port 4096
- **THEN** the NetworkPolicy denies it

#### Scenario: The API requires the password

- **WHEN** a request reaches `/api/*` without the Basic credential
- **THEN** the server answers 401

### Requirement: OpenCode gets its own GitHub Secret

The `opencode-server` container SHALL receive `GITHUB_TOKEN` from a Secret named `opencode-github`.
For now that Secret SHALL be derived from `github-root` by an ExternalSecret — there is no
OpenCode-specific root yet — so the deployment reads one purpose-named Secret and changing the
credential's source later is a single entry in `datahub-local-secrets`. No container SHALL reference
`github-root` directly.

The git credential helper SHALL answer from `GITHUB_TOKEN` and SHALL otherwise fall back to the
minter endpoint, so no credential file is written under `/opt/data`. Pull requests SHALL be opened by
the caller through the GitHub MCP server rather than `gh` in the Pod. SSH deploy keys SHALL NOT be
used: GitHub cannot attach one key to several repositories, which the three-repository workspace
needs.

A GitHub App with on-demand installation tokens remains the intended long-term design, but the
release SHALL NOT require one.

#### Scenario: A task pushes with the OpenCode Secret

- **WHEN** a task runs `git push` on a branch
- **THEN** the helper answers from `GITHUB_TOKEN`
- **AND** that value comes from the `opencode-github` Secret

#### Scenario: The shared root is not in the Pod

- **WHEN** the rendered Pod spec is inspected
- **THEN** no container references `github-root` or an App key
- **AND** no credential file exists under `/opt/data`

#### Scenario: The Pod starts without the App

- **WHEN** the release is rendered with no `github-app` Secret in the cluster
- **THEN** the Pod starts and serves its API
- **AND** no minter container is present

### Requirement: The MCP shim is a separate stateless Pod

The `opencode-mcp` Deployment SHALL expose exactly `run_task`, `get_session`, `get_diff`,
`list_sessions`, `get_transcript`, `respond`, and `abort_session` over MCP at `/mcp`, and SHALL hold
no state. It SHALL talk to the server's HTTP API with the Basic credential and SHALL run one replica.

`run_task` SHALL take a prompt, an optional workspace-relative directory, an optional session id,
and an optional `wait_seconds` (default 120, maximum 300); it SHALL create or resume a session, wait
at most that long, and return the session id, one of `running`, `idle`, `needs_input`, or `error`,
the latest assistant text, and changed files when idle. `get_session` SHALL return the same state
without waiting. `respond` SHALL submit an answer to the pending question or permission.
`get_diff` SHALL return the patch text a session produced, optionally narrowed to a message's turn.
`list_sessions` SHALL return the newest sessions with their state, searchable by title. `get_transcript`
SHALL return the newest messages, oldest first. `abort_session` SHALL interrupt a running session.

While a session is active, `run_task` SHALL return busy with that session's id and SHALL NOT create
a second one. Sessions SHALL NOT be bounded by the tool wait: a session MAY stay active for days.

#### Scenario: A long turn is started and polled

- **WHEN** `run_task` starts a turn that takes hours
- **THEN** it returns `running` with the session id after `wait_seconds`
- **AND** a later `get_session` returns the final text

#### Scenario: The agent asks for feedback

- **WHEN** the session asks a question
- **THEN** `get_session` returns `needs_input` with the question
- **AND** `respond` submits the answer and the session continues

#### Scenario: The agent fails

- **WHEN** the session ends in an error
- **THEN** `get_session` returns `error` with the message

#### Scenario: A second task is refused

- **WHEN** `run_task` is called while another session is active
- **THEN** it returns busy with the active session's id

### Requirement: The web proxy is a separate Pod and the only published surface

The `opencode-web` Deployment SHALL run a reverse proxy that forwards to the server's Service on
4096, preserving SSE and WebSocket upgrades and disabling response buffering. It SHALL be the only
workload exposed by an `IngressRoute`, at `automation-opencode.<gateway_hostname>`, behind the
shared `security/oauth2-proxy-auth` middleware and the `/oauth2/` route. A Traefik `headers`
middleware SHALL inject `Authorization: Basic …` so a signed-in user gets one login.

#### Scenario: Anonymous access is redirected

- **WHEN** the UI origin is opened without a session
- **THEN** oauth2-proxy redirects to dex
- **AND** no request reaches the proxy unauthenticated

#### Scenario: The signed-in user gets the UI

- **WHEN** the dex login completes
- **THEN** the proxy forwards the request with the Basic credential
- **AND** the UI loads without a browser credential prompt

### Requirement: Firecrawl is the self-hosted MCP bridge

The release SHALL NOT deploy a Firecrawl server or hold a Firecrawl account key. The server's
`opencode.json` SHALL register the `add-firecrawl-mcp` bridge at
`http://…-automation-mcp-firecrawl-http.automation.svc.cluster.local:8080/mcp` (the HTTP transport
Service). The server
SHALL NOT enable the native `websearch` or `webfetch` tools.

#### Scenario: Search works through the bridge

- **WHEN** the agent searches
- **THEN** results arrive from the self-hosted Firecrawl API in `data`
- **AND** the server makes no direct web request

#### Scenario: No Firecrawl key exists

- **WHEN** the release is rendered and the cluster is searched
- **THEN** there is no Firecrawl Deployment and no `firecrawl-token` Secret
- **AND** `FIRECRAWL_API_KEY` is absent from every container

### Requirement: Permissions name every needed directory and tool

The OpenCode config SHALL resolve every permission check without a silent `ask`, using the v2
ordered `permissions` ruleset:

- deny `webfetch` and `websearch`;
- deny reads of `*.env` and `*.env.*`;
- deny `external_directory` for `*`, then allow `/workspace/*`, `/tmp/*`, and
  `/opt/data/.config/opencode/*`;
- allow `question`, so the agent can ask and the shim reports `needs_input`;
- allow `fc_firecrawl_scrape`, `fc_firecrawl_search`, and `fc_firecrawl_map`; the bridge registers
  nothing else, so crawl, agent, monitor, interact, parse, and feedback never reach the permission
  layer.

The Firecrawl server SHALL set `codemode: false`, so its tools appear as native
`<server>_<tool>` actions rather than only through Code Mode. `read`, `edit`, `shell`, `glob` and
`grep` SHALL otherwise remain allowed inside the workspace.

#### Scenario: The directories the agent needs are reachable

- **WHEN** the agent writes under `/tmp`, reads its `AGENTS.md`, or runs `git`
- **THEN** the permission check allows it

#### Scenario: Only the registered bridge tools exist

- **WHEN** the agent lists its Firecrawl tools
- **THEN** only `fc_firecrawl_scrape`, `fc_firecrawl_search`, and `fc_firecrawl_map` are present

### Requirement: The Pod runs under gVisor on an amd-1 node

The server Pod SHALL set `runtimeClassName: gvisor`, `nodeSelector` `kubernetes.io/hostname:
datahublocal-amd-1`, and `kubernetes.io/arch: amd64`.

#### Scenario: The sandbox is admitted on the monotonic-clock node

- **WHEN** the Pod spec is inspected
- **THEN** `runtimeClassName` is `gvisor`
- **AND** the Pod is not schedulable on `datahublocal-amd-2`

### Requirement: Every container runs the restricted profile

All containers SHALL run as a non-root uid: 1000 for the OpenCode and shim containers (and the
minter, when it is wired), and the proxy image's own non-root uid. All SHALL set `readOnlyRootFilesystem: true`,
`allowPrivilegeEscalation: false`, all capabilities dropped, and `RuntimeDefault` seccomp. The
service-account token SHALL NOT be mounted. No container SHALL run as uid 0. Writable paths SHALL be
limited to `/opt/data`, `/workspace`, and a size-bounded memory `/tmp`.

#### Scenario: No process is root

- **WHEN** the running containers are inspected
- **THEN** every process runs as a non-root uid
- **AND** no service-account token is mounted
- **AND** no container has an init path that installs packages

### Requirement: Server state is single-writer on two volumes

The server SHALL use one replica, `Recreate`, a Longhorn RWO volume at `/opt/data` (home and
OpenCode state), and a second at `/workspace` (repositories). `HOME` SHALL be `/opt/data`.

#### Scenario: A rollout does not share a volume

- **WHEN** the server is upgraded
- **THEN** the old Pod terminates before the new one mounts either volume

### Requirement: Egress is explicit per workload

- Server Pod: DNS, `data/litellm` on 4000, the automation Firecrawl bridge on 8080, and the
  `security` egress proxy on 3128. No Kubernetes API, no other `automation` Service, and no direct
  public HTTPS.
- Web proxy Pod: DNS and the server on 4096 only.
- Shim Pod: DNS and the server on 4096 only.

The server SHALL set `HTTP_PROXY` and `HTTPS_PROXY` to the proxy Service and `NO_PROXY` to the
cluster domains, so installs, GitHub calls and `helmfile` chart resolution work; a client that
ignores them is denied rather than leaking. The proxy's own allowlist is the `egress-proxy`
capability, and SHALL include the helm chart repositories and OCI registries these releases use.

#### Scenario: The API server is unreachable

- **WHEN** the agent shells out to the Kubernetes API or another private address
- **THEN** the connection is denied by the policy and by the proxy's private ACL

#### Scenario: Public access is allowlisted

- **WHEN** the server resolves a public host and opens a socket
- **THEN** the policy permits only the proxy Pod on 3128
- **AND** the proxy allows only its `pypi`, `github`, `npm`, `helm`, `alpine` and `slack` domains

### Requirement: The shim is registered for Hermes and personas

The shim Service SHALL carry `app.kubernetes.io/name: mcpserver` and port 8080. The release SHALL
create one `sympozium.ai/v1alpha1 MCPServer` named for the shim, labelled
`sympozium.ai/catalog: "true"`, with `spec.url` at `/mcp` and `spec.transportType: http`. Hermes'
`config.mcp_servers.opencode` SHALL point at the same URL with `timeout: 900`.

#### Scenario: Hermes reaches the shim

- **WHEN** Hermes calls the `opencode` MCP server
- **THEN** the existing `mcpserver` egress rule admits the call
- **AND** a 120-second bounded wait is not cut off by the MCP client timeout

### Requirement: Health reflects the server, the provider, and the proxy

Server liveness SHALL probe port 4096. Server readiness SHALL require a resolvable `litellm/*`
model, proving the declared provider loaded. Startup SHALL allow at least 120 seconds. The proxy and
shim SHALL expose readiness against the server.

#### Scenario: A slow first start is not killed

- **WHEN** the first start is still loading MCP and the provider
- **THEN** the startup probe keeps the container alive
- **AND** readiness stays false until a model is listed
