# hermes-gateway Specification

## Purpose

Run Hermes Agent as this cluster's chat-driven agent gateway: one Deployment in the `automation`
namespace, sandboxed by gVisor and the restricted Pod Security profile, reachable only through an
OIDC-gated dashboard, wired to one Slack channel and to the namespace's Sympozium MCP servers, with
in-cluster LiteLLM as the only model path and all state on a single Longhorn volume.

## Requirements

### Requirement: The gateway runs the upstream image through a pinned chart

The release SHALL use `oci://ghcr.io/jyje/hermes-agent-helm/hermes-agent` at chart version `1.22.0`
and image tag `v0.22.5`. It SHALL NOT build, patch, or vendor the agent source, and SHALL NOT
require a custom session driver.

#### Scenario: No build step is involved

- **WHEN** the release is rendered
- **THEN** the workload uses `nousresearch/hermes-agent:v0.22.5`
- **AND** no image build, patch layer, or in-repo agent source is involved

#### Scenario: An upgrade is deliberate

- **WHEN** the chart or image pin changes
- **THEN** the chart version and image tag change together in `values/_version.yaml`

### Requirement: The gateway runs under gVisor

The Pod SHALL set `runtimeClassName: gvisor`. The browser toolset SHALL stay disabled until a
browser launch and a page read are proven under that runtime.

#### Scenario: The Pod is admitted with the sandbox runtime

- **WHEN** the Pod spec is inspected
- **THEN** `runtimeClassName` is `gvisor`
- **AND** the gateway answers a model turn while running under it

#### Scenario: The Pod lands on a node with a monotonic clock

- **WHEN** the Pod is scheduled
- **THEN** `nodeSelector` names `datahublocal-amd-1`, whose clocksource is `tsc`
- **AND** it is not placed on `datahublocal-amd-2`, where the kernel blacklists the TSC
  (`available_clocksource` is `hpet acpi_pm` only) and gVisor's sandbox clock jumps backwards by up
  to 1.6 s — enough to abort the dashboard's Node TUI in `GetNowUint64`'s monotonicity check, which
  measured 53 of 800 `node` starts on that node

### Requirement: The Pod runs the restricted security profile

The release SHALL layer the chart's hardened profile: `runAsNonRoot: true` with the image's `hermes`
uid/gid `10000`, `readOnlyRootFilesystem: true`, size-bounded memory `emptyDir`s at `/run` and
`/tmp`, `allowPrivilegeEscalation: false`, all capabilities dropped, and `RuntimeDefault` seccomp.
The service-account token SHALL NOT be mounted. `/run` SHALL remain writable and executable, because
s6-overlay's init runs from it. One init container SHALL run as uid 0 solely to take ownership of the
`/opt/data` mountpoint, with every capability dropped but `CHOWN` and the root filesystem read-only.

#### Scenario: The gateway is not root

- **WHEN** the running gateway is inspected
- **THEN** its process runs as uid 10000
- **AND** the container has no added capabilities and no service-account token

#### Scenario: The root filesystem is read-only

- **WHEN** the rendered Pod spec is inspected
- **THEN** the main container sets `readOnlyRootFilesystem: true`
- **AND** `/run` and `/tmp` are the only writable memory-backed mounts besides `/opt/data`

### Requirement: The only inbound surface is the OIDC-gated dashboard

The release SHALL expose the chart's management dashboard through one Traefik `IngressRoute` at
`automation-hermes.<gateway_hostname>`, backed by the release's Service on port 9119. It SHALL be the
only listener bound off loopback: the chart's API server binds `127.0.0.1` only and the webhook
receiver SHALL stay disabled. The dashboard SHALL authenticate
against dex (`dashboard.auth.provider: oidc`, client `hermes`), because upstream fails closed without
a provider, and SHALL set `public_url` and `trusted_proxies` so the callback origin matches the
registered redirect URI and the session cookies are marked `Secure`.

#### Scenario: The dashboard is the only route

- **WHEN** cluster resources for the release are listed
- **THEN** there is exactly one IngressRoute, pointing at the dashboard Service port
- **AND** no listener other than the dashboard binds a non-loopback address

#### Scenario: Sign-in goes through dex

- **WHEN** the dashboard origin is opened without a session
- **THEN** it redirects to the sign-in page and the callback returns through dex
- **AND** `/api/env` and `/api/config` answer 401 unauthenticated

#### Scenario: Nothing else reaches the pod

- **WHEN** a connection to port 9119 arrives from an address outside Traefik's node network and the
  pod CIDR
- **THEN** the NetworkPolicy denies it

#### Scenario: Every Traefik replica can reach the dashboard

- **WHEN** Traefik on a node other than the one hosting the Pod forwards a request to port 9119
- **THEN** the request is admitted, because a gVisor sandbox sees such a peer SNATed to the pod
  network's gateway address rather than the node address

### Requirement: The dex client names the dashboard callback

The dex staticClient `hermes` SHALL list exactly the dashboard callback
`https://automation-hermes.<gateway_hostname>/auth/callback` and SHALL reuse the shared client
secret already used by the other dex clients. The dashboard SHALL read that secret from
`HERMES_DASHBOARD_OIDC_CLIENT_SECRET`, never from `config.yaml`, which renders into a ConfigMap.

#### Scenario: The callback is registered

- **WHEN** dex is asked to complete a login started from the dashboard origin
- **THEN** the callback URI matches the registered entry and the login completes
- **AND** the client secret reaches the Pod only as an environment variable

### Requirement: Egress is limited to DNS, LiteLLM, and HTTPS

The chart's NetworkPolicy SHALL be enabled with `allowDns: true` and `blockPrivateEgress: true`, plus
one explicit egress rule for LiteLLM on port 4000 and one for the Traefik node network on port 443.
The second is needed because dex — the dashboard's OIDC issuer — is published through Traefik, which
runs hostNetwork, so the issuer hostname resolves to an RFC1918 node address that
`blockPrivateEgress` would otherwise deny, leaving the dashboard answering 503 on `/auth/login`.
Public HTTPS SHALL remain allowed for Slack. The residual breadth of HTTPS SHALL be documented,
because the CNI enforces L3/L4 and cannot restrict by hostname.

#### Scenario: The Kubernetes API is unreachable from the agent

- **WHEN** the gateway tries to reach the API server or another private address outside the allowed
  set
- **THEN** the connection is denied

#### Scenario: LiteLLM is reachable

- **WHEN** the gateway calls the in-cluster LiteLLM Service on port 4000
- **THEN** the connection is allowed by the policy

#### Scenario: The OIDC issuer is reachable

- **WHEN** the dashboard starts a login and fetches dex's discovery document
- **THEN** the request to the issuer hostname is allowed by the policy

### Requirement: MCP tools are the namespace's own Sympozium servers

`config.mcp_servers` SHALL register the namespace's Sympozium MCP servers as HTTP MCP endpoints on
port 8080, and the NetworkPolicy SHALL allow egress to the `app.kubernetes.io/name: mcpserver` pods
on that port. Seven of them are the shared `…-mcp-*` Services the Sympozium agents already
use; their stdio bridge speaks MCP over HTTP and needs no credential the Deployments do not already
mount. The `slack` entry is a tool surface on top of the built-in channel, which keeps its own Socket
Mode connection.

The seventh, `sympozium-firecrawl`, SHALL point at a dedicated
`…-mcp-firecrawl-http` Service running `ghcr.io/firecrawl/firecrawl-mcp-server` in its own
stateless HTTP mode, which proxies the self-hosted Firecrawl API in `data`. It SHALL expose only the
scrape, search and map tools through the server's `tools.include` filter, and SHALL need no Firecrawl
account key. Like `sympozium-github`, it SHALL bypass the stdio bridge, because the bridge forwards
each client's `initialize` to one long-lived child and misroutes this server's replies. The gateway
SHALL disable the native `web` and `browser` toolsets on every platform through
`config.agent.disabled_toolsets`, so those tools are not offered on Slack, CLI, dashboard or cron
surfaces. Public egress SHALL remain allowed for Slack; this is not a network boundary.

`sympozium-github` SHALL instead point at a dedicated `…-mcp-github-hermes` Service running
the upstream server in its `http` mode, because the bridge re-sends `initialize` to a long-lived
child and `github-mcp-server` v2 rejects the duplicate. That
instance SHALL authenticate with `Authorization: Bearer` resolved from `GITHUB_PERSONAL_ACCESS_TOKEN`
at gateway start, never from a literal in `config.yaml`, SHALL exclude the tools the catalog server
denies (`create_repository`, `fork_repository`, `delete_repository`, `delete_file`,
`merge_pull_request`), and SHALL stay out of Sympozium's MCPServer catalog so its agents keep their
own stdio instance.

#### Scenario: The agent discovers the namespace's tools

- **WHEN** the gateway enumerates MCP tools
- **THEN** every registered server completes the MCP handshake and reports its tools

#### Scenario: github uses its own transport

- **WHEN** the gateway connects to `sympozium-github`
- **THEN** it reaches the dedicated HTTP instance rather than the shared stdio bridge
- **AND** the request carries the token from the Pod environment

#### Scenario: Firecrawl is reachable through the bridge

- **WHEN** the gateway connects to `sympozium-firecrawl`
- **THEN** it reaches the bridge in its own namespace on 8080
- **AND** a scrape returns page markdown from the self-hosted API in `data`

#### Scenario: Firecrawl replaces the native web tools

- **WHEN** the gateway's tool list is read for any platform
- **THEN** `web` and `browser` are absent
- **AND** only the three included Firecrawl tools are registered from `sympozium-firecrawl`
- **AND** public egress remains allowed for Slack

#### Scenario: MCP is the only in-namespace egress besides LiteLLM

- **WHEN** the agent connects to any other Service in this namespace
- **THEN** the NetworkPolicy denies it

### Requirement: Credentials come from existing secrets by reference

The Pod SHALL consume `OPENAI_API_KEY` from `litellm-auth-credentials`, the Slack tokens from
`hermes-slack-token`, and `GITHUB_PERSONAL_ACCESS_TOKEN` from `mcp-github-token` through
`extraEnvFrom`. The chart's own `env` map SHALL carry no credential: its only entry is
`OPENAI_API_KEY: null`, which deletes the chart's `sk-REPLACE_ME` default so the `extraEnvFrom` source
wins the duplicate name. The LiteLLM key SHALL NOT appear in a values file, a ConfigMap, or a
rendered manifest. The dex client secret is the one exception: it is the shared value already used by
the other dex clients, it comes from `/helm-values/security.yaml` rather than this repository, and it
reaches the Pod as `HERMES_DASHBOARD_OIDC_CLIENT_SECRET`, because the dashboard reads that key from
the environment and `config.yaml` renders into a ConfigMap. The GitHub token SHALL reach the
`sympozium-github` header only through that environment expansion.

#### Scenario: No credential is rendered

- **WHEN** the Helm output is searched for key material
- **THEN** the LiteLLM key appears only as a secret reference
- **AND** the GitHub token appears only as `${env:GITHUB_PERSONAL_ACCESS_TOKEN}`
- **AND** the only literal secret is the dex client secret, which is not this repository's to hold

### Requirement: The model path is the cluster LiteLLM endpoint

The agent SHALL use a custom provider with `base_url` pointing at LiteLLM's `/v1` endpoint, the key
from `OPENAI_API_KEY`, and model alias `opencode-go/deepseek-v4.1-flash`. It SHALL NOT call a public
model API directly.

#### Scenario: A turn is served by LiteLLM

- **WHEN** a message reaches the agent
- **THEN** the request is served by in-cluster LiteLLM
- **AND** the reply is delivered back to Slack

### Requirement: Slack is restricted to the owner and to one channel

The gateway SHALL enable Slack through `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`, with
`GATEWAY_ALLOW_ALL_USERS=false`, `SLACK_ALLOWED_USERS` containing only `U08RV08387L`, and
`SLACK_ALLOWED_CHANNELS` plus `SLACK_FREE_RESPONSE_CHANNELS` containing only `#agent-hermes`
(`C0CBX92B6PQ`), so plain messages there are answered without an @mention.

That channel is private, so the Slack app SHALL subscribe to `message.groups` and grant
`groups:history`; without both, a plain message produces no event. The app SHALL be a dedicated one
with its own bot and app-level tokens in `hermes-slack-token`, because Slack delivers each event to
one of an app's Socket Mode connections: the `@homelab` app is held by Sympozium's channel responder,
which received and dropped the gateway's messages. Reinstalling an app to add a scope rotates its bot
token, so the Secret SHALL be updated and the Pod restarted.

#### Scenario: An unlisted user is ignored

- **WHEN** a Slack user outside the allowlist messages the bot
- **THEN** no agent turn runs

#### Scenario: A message in the scoped channel is answered

- **WHEN** the owner posts a plain message in `#agent-hermes`
- **THEN** the gateway logs `inbound message: platform=slack`, opens a `source=slack` session, and
  replies in the channel

#### Scenario: Another channel is ignored

- **WHEN** the bot is mentioned in a channel other than `#agent-hermes`
- **THEN** no agent turn runs, because `SLACK_ALLOWED_CHANNELS` is set

### Requirement: Inbound Slack messages are acknowledged with a reaction

Every inbound Slack message SHALL get an `:eyes:` reaction before channel, mention and authorisation
gating, so a message that produces no turn is still visibly acknowledged. Hermes's built-in lifecycle
reaction covers only DMs and @mentions — it swaps `:eyes:` for `:white_check_mark:` or `:x:` when a
tracked turn ends — so the broader ack comes from the `slack-eyes-ack` plugin.

The plugin's two files SHALL ship as a ConfigMap mounted over `/opt/data/plugins/slack-eyes-ack`,
because values cannot carry files and the gateway scans that directory only at startup, and
`config.plugins` SHALL select it with `plugins.entries.slack-eyes-ack.settings.emoji: eyes`. The app
needs `reactions:write`.

#### Scenario: A plain channel message is acknowledged

- **WHEN** the owner posts a plain message in `#agent-hermes`
- **THEN** the message carries `:eyes:` while the turn runs
- **AND** the plugin log line `every inbound Slack message now gets :eyes: before gating` appears once
  per gateway start

#### Scenario: A dropped message is still acknowledged

- **WHEN** a message arrives that the channel or user gate will drop
- **THEN** it still receives `:eyes:`, because the reaction is added before gating

### Requirement: State is single-writer and survives restarts

The release SHALL use one replica, the chart's `Recreate` strategy, and a persistent volume mounted
at `/opt/data`. Values requesting more than one replica with persistence SHALL be rejected or
refused at review.

#### Scenario: A rollout does not share the state directory

- **WHEN** the release is upgraded
- **THEN** the old Pod terminates before the new one mounts `/opt/data`

### Requirement: The state volume is backed up through Hermes' own archive

The `data` volume SHALL be included in the daily Velero filesystem backup, and that backup SHALL run
a pre-hook writing `hermes backup -o /opt/data/backups/hermes-backup-<timestamp>.zip -k 3` first,
because a raw copy of a live `HERMES_HOME` can tear a WAL-mode SQLite database. The hook SHALL be
bounded by a 15-minute timeout. Hermes' archive snapshots `*.db` through `sqlite3.backup()` and skips
its own `backups/` directory, so the hook does not nest archives.

#### Scenario: A daily backup holds a consistent archive

- **WHEN** the daily filesystem backup runs
- **THEN** the pre-hook exits only after writing a database-consistent zip under `/opt/data/backups`
- **AND** earlier `hermes-backup-*.zip` files beyond the newest three are pruned by `-k 3`

### Requirement: Health is the supervised gateway service

Liveness, readiness and startup SHALL probe the s6-supervised gateway service
(`/command/s6-svstat /run/service/main-hermes`), and readiness SHALL additionally require the dashboard
listener to answer on port 9119. `hermes gateway status` SHALL NOT be the probe: it is accurate but
takes about 35 seconds inside this Pod, and it reports the process rather than channel connectivity,
so nothing is lost by asking s6 directly.

#### Scenario: A dead gateway is not ready

- **WHEN** the supervised gateway service is down
- **THEN** readiness fails
