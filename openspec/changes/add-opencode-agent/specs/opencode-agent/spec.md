# Spec Delta

## ADDED Requirements

### Requirement: The server runs the upstream image with a pinned plugin

The `opencode-server` workload SHALL run `ghcr.io/anomalyco/opencode` at the tag pinned in
`values/_version.yaml`, by digest. It SHALL NOT build or patch the image. The litellm plugin SHALL be
`opencode-plugin-litellm` at the version pinned beside the image, installed by an init container into
the writable plugin cache on the state volume, and listed in `opencode.json`.

#### Scenario: The image is upstream

- **WHEN** the rendered Pod spec is inspected
- **THEN** the server image is the official OpenCode image by digest
- **AND** no derived OpenCode image is involved

#### Scenario: The plugin install is idempotent

- **WHEN** the init container runs with a warm cache for the pinned version
- **THEN** it exits without a registry request

### Requirement: Configuration, instructions, and the git helper are ConfigMaps

One ConfigMap SHALL carry `opencode.json`, `AGENTS.md`, and `git-credential-opencode`, mounted at
`/opt/data/.config/opencode/opencode.json`, `/opt/data/.config/opencode/AGENTS.md`, and
`/opt/data/bin/git-credential-opencode` (mode `0755`). The config SHALL name the default model, the
pinned plugin, the Firecrawl MCP server, the git credential helper, and the permission ruleset.

#### Scenario: All three files are present before the server starts

- **WHEN** the Pod starts
- **THEN** the config, the instructions, and an executable helper exist at those paths
- **AND** none is written by the container at runtime

### Requirement: LiteLLM is the only model path, through the plugin

`LITELLM_BASE_URL` SHALL name the `data` release's LiteLLM `/v1` endpoint and `LITELLM_API_KEY`
SHALL come from `litellm-auth-credentials` by reference. The default model SHALL be
`litellm/opencode-go/deepseek-v4.1-flash`.

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

### Requirement: Git is installed into the state volume

An init container SHALL install Alpine's `git` into `/opt/data/git` with
`apk --root` and the image's key and repository files, and the server container SHALL expose it via
`PATH`, `LD_LIBRARY_PATH`, and `GIT_EXEC_PATH`. The install SHALL be idempotent. The server
container SHALL keep a read-only root filesystem; the init container is the only root process and
drops every capability.

#### Scenario: Git runs as the agent user

- **WHEN** the agent runs `git --version` and `git clone` over HTTPS
- **THEN** both succeed as uid 1000

### Requirement: GitHub credentials live in a minter sidecar, not the server

The `opencode-server` Pod SHALL include a minter sidecar holding `GITHUB_APP_ID`,
`GITHUB_APP_INSTALLATION_ID`, and `GITHUB_APP_PRIVATE_KEY` by secret reference. The minter SHALL
expose a loopback token endpoint that returns a cached installation token while it has more than ten
minutes left and otherwise mints a fresh one. The git helper SHALL call that endpoint when git runs,
so a session may live for days without a credential file or a refresh loop. The server container
SHALL NOT receive the App key or any long-lived GitHub credential.

#### Scenario: Git works days into a session

- **WHEN** a session started days ago runs `git fetch`
- **THEN** the helper receives a freshly minted token
- **AND** no credential file exists under `/opt/data`

#### Scenario: The key is not in the server container

- **WHEN** the server container's environment and filesystem are inspected
- **THEN** the App key is absent
- **AND** only the minter holds it

### Requirement: The MCP shim is a separate stateless Pod

The `opencode-mcp` Deployment SHALL expose exactly `run_task`, `get_session`, `respond`, and
`abort_session` over MCP at `/mcp`, and SHALL hold no state. It SHALL talk to the server's HTTP API
with the Basic credential and SHALL run one replica.

`run_task` SHALL take a prompt, an optional workspace-relative directory, an optional session id,
and an optional `wait_seconds` (default 120, maximum 300); it SHALL create or resume a session, wait
at most that long, and return the session id, one of `running`, `idle`, `needs_input`, or `error`,
the latest assistant text, and changed files when idle. `get_session` SHALL return the same state
without waiting. `respond` SHALL submit an answer to the pending question or permission.
`abort_session` SHALL interrupt a running session.

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
`http://…-automation-mcp-firecrawl.automation.svc.cluster.local:8080/mcp`. The server
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

The OpenCode config SHALL resolve every permission check without a silent `ask`:

- deny `webfetch`, `websearch`;
- allow `question`, so the agent can ask and the shim reports `needs_input`;
- deny reads of `*.env` and `*.env.*`;
- deny `external_directory` for `*`, then allow `/workspace/*`, `/tmp/*`,
  `/opt/data/.config/opencode/*`, and `/opt/data/git/*`;
- allow `fc_firecrawl_scrape`, `fc_firecrawl_search`, and `fc_firecrawl_map`; the bridge registers
  nothing else, so crawl, agent, monitor, interact, parse, and feedback never reach the permission
  layer.

`read`, `edit`, `shell`, `glob` and `grep` SHALL otherwise remain allowed inside the workspace.

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

All containers SHALL run as a non-root uid: 1000 for the OpenCode, minter, and shim containers, and
the proxy image's own non-root uid. All SHALL set `readOnlyRootFilesystem: true`,
`allowPrivilegeEscalation: false`, all capabilities dropped, and `RuntimeDefault` seccomp. The
service-account token SHALL NOT be mounted. The git-install init container SHALL be the only root
process, with all capabilities dropped, writing only to `/opt/data`. Writable paths SHALL be limited
to `/opt/data`, `/workspace`, and a size-bounded memory `/tmp`.

#### Scenario: No long-running process is root

- **WHEN** the running containers are inspected
- **THEN** no long-running process runs as uid 0
- **AND** no service-account token is mounted

### Requirement: Server state is single-writer on two volumes

The server SHALL use one replica, `Recreate`, a Longhorn RWO volume at `/opt/data` (home, git,
plugin cache), and a second at `/workspace` (repositories). `HOME` SHALL be `/opt/data`.

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
cluster domains, so installs and GitHub calls work; a client that ignores them is denied rather than
leaking. The proxy's own allowlist is the `egress-proxy` capability.

#### Scenario: The API server is unreachable

- **WHEN** the agent shells out to the Kubernetes API or another private address
- **THEN** the connection is denied by the policy and by the proxy's private ACL

#### Scenario: Public access is allowlisted

- **WHEN** the server resolves a public host and opens a socket
- **THEN** the policy permits only the proxy Pod on 3128
- **AND** the proxy allows only its `pypi`, `github`, `npm` and `alpine` domains

### Requirement: The shim is registered for Hermes and personas

The shim Service SHALL carry `app.kubernetes.io/name: mcpserver` and port 8080. The release SHALL
create one `sympozium.ai/v1alpha1 MCPServer` named for the shim, labelled
`sympozium.ai/catalog: "true"`, with `spec.url` at `/mcp` and `spec.transportType: http`. Hermes'
`config.mcp_servers.opencode` SHALL point at the same URL with `timeout: 900`.

#### Scenario: Hermes reaches the shim

- **WHEN** Hermes calls the `opencode` MCP server
- **THEN** the existing `mcpserver` egress rule admits the call
- **AND** a 120-second bounded wait is not cut off by the MCP client timeout

### Requirement: Health reflects the server, the plugin, and the proxy

Server liveness SHALL probe port 4096. Server readiness SHALL require a resolvable `litellm/*`
model, because a cold cache installs the plugin and git. Startup SHALL allow at least 120 seconds.
The proxy and shim SHALL expose readiness against the server.

#### Scenario: A cold install is not killed

- **WHEN** the first start is still installing the plugin or git
- **THEN** the startup probe keeps the container alive
- **AND** readiness stays false until a model is listed
