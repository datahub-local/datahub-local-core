# Spec Delta

## ADDED Requirements

### Requirement: The gateway runs the upstream image through a pinned chart

The release SHALL use `oci://ghcr.io/jyje/hermes-agent-helm/hermes-agent` at chart version `1.21.0`
and image tag `v0.22.2`. It SHALL NOT build, patch, or vendor the agent source, and SHALL NOT
require a custom session driver.

#### Scenario: No build step is involved

- **WHEN** the release is rendered
- **THEN** the workload uses `nousresearch/hermes-agent:v0.22.2`
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

### Requirement: The Pod runs the restricted security profile

The release SHALL layer the chart's hardened profile: `runAsNonRoot: true` with the image's `hermes`
uid/gid `10000`, `readOnlyRootFilesystem: true`, size-bounded memory `emptyDir`s at `/run` and
`/tmp`, `allowPrivilegeEscalation: false`, all capabilities dropped, and `RuntimeDefault` seccomp.
The service-account token SHALL NOT be mounted. `/run` SHALL remain writable and executable, because
s6-overlay's init runs from it.

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
`automation-hermes.<gateway_hostname>`, backed by the release's Service on port 9119. The API server,
the webhook receiver and every other listener SHALL stay disabled. The dashboard SHALL authenticate
against dex (`dashboard.auth.provider: oidc`, client `hermes`), because upstream fails closed without
a provider, and SHALL set `public_url` and `trusted_proxies` so the callback origin matches the
registered redirect URI and the session cookies are marked `Secure`.

#### Scenario: The dashboard is the only route

- **WHEN** cluster resources for the release are listed
- **THEN** there is exactly one IngressRoute, pointing at the dashboard Service port
- **AND** no API server or webhook listener is enabled

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

`config.mcp_servers` SHALL register the seven `…-sympozium-mcp-*` Services of this namespace as HTTP
MCP endpoints (`http://<release>-automation-sympozium-mcp-<name>.automation.svc.cluster.local:8080/mcp`),
and the NetworkPolicy SHALL allow egress to the `app.kubernetes.io/name: mcpserver` pods on port 8080.
These are the servers the Sympozium agents already use; their stdio adapter speaks MCP over HTTP and
needs no credential the Deployments do not already mount. The `slack` entry is a tool surface on top
of the built-in channel, which keeps its own Socket Mode connection.

#### Scenario: The agent discovers the namespace's tools

- **WHEN** the gateway enumerates MCP tools
- **THEN** every registered server completes the MCP handshake and reports its tools

#### Scenario: MCP is the only in-namespace egress besides LiteLLM

- **WHEN** the agent connects to any other Service in this namespace
- **THEN** the NetworkPolicy denies it

### Requirement: Credentials come from existing secrets by reference

The Pod SHALL consume `OPENAI_API_KEY` from `litellm-auth-credentials` and the Slack tokens from
`mcp-slack-token` through `extraEnvFrom`. The chart's own `env` map SHALL stay empty. The LiteLLM key
SHALL NOT appear in a values file, a ConfigMap, or a rendered manifest. The dex client secret is the
one exception: it is the shared value already used by the other dex clients, it comes from
`/helm-values/security.yaml` rather than this repository, and it reaches the Pod as
`HERMES_DASHBOARD_OIDC_CLIENT_SECRET`, because the dashboard reads that key from the environment and
`config.yaml` renders into a ConfigMap.

#### Scenario: No credential is rendered

- **WHEN** the Helm output is searched for key material
- **THEN** the LiteLLM key appears only as a secret reference
- **AND** the only literal secret is the dex client secret, which is not this repository's to hold

### Requirement: The model path is the cluster LiteLLM endpoint

The agent SHALL use a custom provider with `base_url` pointing at LiteLLM's `/v1` endpoint, the key
from `OPENAI_API_KEY`, and model alias `opencode-go/deepseek-v4.1-flash`. It SHALL NOT call a public
model API directly.

#### Scenario: A turn is served by LiteLLM

- **WHEN** a message reaches the agent
- **THEN** the request is served by in-cluster LiteLLM
- **AND** the reply is delivered back to Slack

### Requirement: Slack is restricted to the owner

The gateway SHALL enable Slack through `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`, with
`GATEWAY_ALLOW_ALL_USERS=false` and `SLACK_ALLOWED_USERS` containing only `U08RV08387L`.

#### Scenario: An unlisted user is ignored

- **WHEN** a Slack user outside the allowlist messages the bot
- **THEN** no agent turn runs

### Requirement: State is single-writer and survives restarts

The release SHALL use one replica, the chart's `Recreate` strategy, and a persistent volume mounted
at `/opt/data`. Values requesting more than one replica with persistence SHALL be rejected or
refused at review.

#### Scenario: A rollout does not share the state directory

- **WHEN** the release is upgraded
- **THEN** the old Pod terminates before the new one mounts `/opt/data`

### Requirement: Health is the supervised gateway service

Liveness, readiness and startup SHALL probe the s6-supervised gateway service
(`/command/s6-svstat /run/service/main-hermes`), and readiness SHALL additionally require the dashboard
listener to answer on port 9119. `hermes gateway status` SHALL NOT be the probe: it is accurate but
takes about 35 seconds inside this Pod, and it reports the process rather than channel connectivity,
so nothing is lost by asking s6 directly.

#### Scenario: A dead gateway is not ready

- **WHEN** the supervised gateway service is down
- **THEN** readiness fails
