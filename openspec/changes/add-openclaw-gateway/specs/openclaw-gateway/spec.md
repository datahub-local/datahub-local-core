# Spec Delta

## ADDED Requirements

### Requirement: The gateway survives its own shutdown drain

The deployment SHALL give the gateway a termination grace period longer than its own drain budget,
because a SIGKILL mid-drain leaves an owner lease in the state directory and the next start refuses
to run against it. The grace period SHALL be set where the rest of the pod is configured, so the
relationship is visible rather than buried in a default.

#### Scenario: A restart does not poison the state directory

- **WHEN** the pod is replaced while the gateway is draining
- **THEN** the gateway has time to release its owner lease
- **AND** the replacement starts without `Another Gateway owner lease is still active`

### Requirement: Liveness is asserted where the gateway is reachable

Probes SHALL be `exec` probes that assert the JSON readiness body, not HTTP or TCP probes against the
pod IP. The Control UI answers unknown paths with a catch-all 200, so a status-code check alone would
report a broken gateway as healthy. The release binds `custom:0.0.0.0` for Traefik, so an HTTP probe
would connect — and still prove nothing. Each probe SHALL be explicitly enabled, because the chart
drops an unenabled probe without failing the render.

#### Scenario: A gateway that cannot answer is not called ready

- **WHEN** the gateway is running but its HTTP surface does not answer
- **THEN** the readiness probe fails
- **AND** the pod is kept out of the Service endpoints

#### Scenario: A dropped probe is not mistaken for a passing one

- **WHEN** the rendered pod spec is inspected
- **THEN** startup, readiness and liveness probes are all present

### Requirement: The Control UI is reachable only through the authenticated ingress

The gateway SHALL bind a non-loopback address so Traefik can reach it, and SHALL list the proxy origin
in `gateway.controlUi.allowedOrigins` — a non-loopback bind refuses to start without explicit
origins, and startup seeds only localhost/127.0.0.1. The IngressRoute SHALL use the `websecure`
entrypoint with the `oauth2-proxy-auth` middleware on every path except `/oauth2/`, and gateway token
auth SHALL stay enabled behind the proxy.

#### Scenario: An unauthenticated request is stopped at the ingress

- **WHEN** a request reaches the UI hostname without an oauth2-proxy session
- **THEN** it is redirected through the oauth2-proxy login, not served by the gateway

#### Scenario: The UI still requires the gateway token

- **WHEN** a browser authenticated by the proxy opens the Control UI
- **THEN** the gateway still demands its own token

### Requirement: The agent runs the hardened tool profile

The release SHALL set `tools.profile: "messaging"` and deny `group:automation`, `group:runtime`,
`group:fs`, `sessions_spawn` and `sessions_send`, with `fs.workspaceOnly: true`, `exec` denied,
`elevated` and `agentToAgent` off, and `session.dmScope: "per-channel-peer"`. `group:web` and
`browser` SHALL be re-allowed explicitly — the messaging profile omits both — while `bundle-mcp` is
implicit in the profile, so search, the browser and the facts MCP server keep working.

#### Scenario: The agent cannot run shell commands or touch the filesystem

- **WHEN** an agent turn is asked to run a shell command or open a workspace file
- **THEN** the `exec`/`process` and `fs` tools are not offered to the model

#### Scenario: Search and the browser survive the profile

- **WHEN** an agent turn searches the web or opens a page
- **THEN** `web_search` and `browser` are available

#### Scenario: MCP tools survive the profile

- **WHEN** an agent turn calls a `homelab_facts` tool
- **THEN** the `bundle-mcp` tools are offered under the messaging profile

### Requirement: The browser works inside the pod or is disabled

When the browser is enabled the deployment SHALL supply the two things the bundled Chromium needs in
a container: `noSandbox: true`, because the namespace sandbox cannot initialize under the pod's
seccomp profile, and a `/dev/shm` larger than the 64 Mi pod default. The image SHALL be a `-browser`
variant and the pod SHALL be scheduled on amd64, where the bundled Chromium is auto-detected.

#### Scenario: The bundled browser starts

- **WHEN** the browser is enabled and the gateway is asked to open a page
- **THEN** a managed Chromium starts and returns a snapshot
- **AND** no explicit executable path is required

#### Scenario: A page is actually read

- **WHEN** an agent turn asks for something only the rendered page carries
- **THEN** the browser tool navigates and the agent answers from the page content

### Requirement: The model plane is the cluster gateway

The deployment SHALL reach its models through the in-cluster LiteLLM proxy as an OpenAI-compatible
provider, and SHALL read the provider key from a secret rather than carry it in configuration.

#### Scenario: A turn is answered through the proxy

- **WHEN** an agent turn runs
- **THEN** the model call goes to the in-cluster proxy and returns a completion
- **AND** no key value appears in the release's rendered configuration

### Requirement: Slack is connected without duplicating a credential

The deployment SHALL connect Slack over Socket Mode, reading both the bot token and the app-level
token from the existing `slack-root`-derived secret rather than minting a second copy. Access SHALL
default to an allowlist, so the bot does not answer in an unlisted channel until one is added on
purpose.

#### Scenario: The bot answers a paired DM

- **WHEN** a user who has paired with the bot sends a direct message
- **THEN** the gateway receives it over Socket Mode and the agent replies
- **AND** no Slack credential is committed to this repository

#### Scenario: An unlisted channel gets no answer

- **WHEN** the bot is mentioned in a channel that is not on the allowlist
- **THEN** the gateway does not answer there

### Requirement: Plugins are pinned to a build that can load them

The image SHALL be pinned by digest, and the plugin installs SHALL be pinned to exact versions the
pinned image can load — at or above the plugin API floor, because a plugin install refuses silently:
the CLI exits 0 while reporting `requires plugin API >=<version>`. A failed install SHALL be logged
rather than silently tolerated. The declared plugin set SHALL NOT be expressed as a `plugins.allow`
list, because that list is authoritative and would disable bundled plugins the deployment depends on.

#### Scenario: A declared plugin actually installs

- **WHEN** the plugin set is installed on the pinned tag
- **THEN** each non-bundled plugin reports `Installed plugin: …`
- **AND** no plugin reports a plugin-API refusal

#### Scenario: Enabling one plugin does not disable another

- **WHEN** the plugin entries are added to configuration
- **THEN** the bundled browser plugin stays loaded
- **AND** the existing browser capability is unaffected

### Requirement: Sympozium's facts MCP server is reachable from the gateway

The gateway SHALL connect to Sympozium's `fact_server` — the homelab-facts MCP server — as a
streamable-HTTP MCP server, so its tools are available to agents through the same tool policy as
every other tool.

#### Scenario: The facts server answers

- **WHEN** the MCP server definition is probed
- **THEN** the in-cluster endpoint answers an MCP initialization
- **AND** its tools appear in the effective tool inventory

### Requirement: A plugin that needs a credential says so rather than borrowing one

A plugin SHALL read its credential from a secret dedicated to this deployment, and SHALL NOT reuse a
shared administrative credential. A plugin whose credential does not exist SHALL be left configured
but unauthenticated, and the missing key recorded as a task rather than substituted.

#### Scenario: No administrative credential is reused

- **WHEN** the rendered deployment is inspected
- **THEN** no GitHub administrative token is referenced
- **AND** the only Slack credentials are the ones already delivered for the MCP server's app

#### Scenario: A missing key is visible, not papered over

- **WHEN** a plugin's credential is absent
- **THEN** the deployment still starts
- **AND** the missing key is listed as outstanding work

### Requirement: The state directory outlives the pod

The gateway SHALL persist its state on a claim, because image tags advance and a persisted state
database carries the schema its writer created.

#### Scenario: Configuration survives a restart

- **WHEN** the pod is replaced
- **THEN** the agent workspace and gateway state are still present
- **AND** config seeded on first boot is not overwritten by the ConfigMap
