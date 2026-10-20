# Spec Delta

## ADDED Requirements

### Requirement: The gateway runs the upstream image, not a fork

The release SHALL run `nousresearch/hermes-agent` pinned by both tag and index digest. It SHALL NOT
build, patch, or vendor the agent source, and SHALL NOT require a custom session driver.

#### Scenario: No build step is involved

- **WHEN** the release is rendered
- **THEN** the image reference is an upstream tag plus digest
- **AND** no image build, patch layer, or in-repo agent source is involved

### Requirement: The gateway runs under gVisor

Every container in the gateway Pod SHALL carry `runtimeClassName: gvisor`. The browser toolset SHALL
stay disabled until a browser launch and a page read are proven under that runtime.

#### Scenario: The Pod is admitted with the sandbox runtime

- **WHEN** the Pod spec is inspected
- **THEN** `runtimeClassName` is `gvisor`
- **AND** the gateway accepts a model turn while running under it

### Requirement: Privilege drop follows the image's supported contract

The Pod SHALL start the image's own entrypoint as root because the s6 bootstrap requires it, and
SHALL set `HERMES_UID` and `HERMES_GID` so the gateway process drops to the unprivileged `hermes`
user. The release SHALL NOT pin an arbitrary `runAsUser` that the image rejects. All capabilities
SHALL be dropped, privilege escalation SHALL be disabled, `RuntimeDefault` seccomp SHALL be set, and
the service-account token SHALL NOT be mounted. Any writable root filesystem SHALL be recorded as a
deviation next to the values.

#### Scenario: The gateway process is not root

- **WHEN** the running gateway is inspected
- **THEN** its main process runs as the configured unprivileged uid
- **AND** the container has no added capabilities and no service-account token

#### Scenario: An unsupported uid pin is not used

- **WHEN** the rendered Pod spec is inspected
- **THEN** it does not set `runAsUser` to an arbitrary non-hermes uid

### Requirement: Nothing on the network can reach the gateway

The release SHALL NOT create an IngressRoute, a public Service, or a homepage entry. Slack SHALL use
Socket Mode, an outbound connection. The dashboard SHALL remain unexposed.

#### Scenario: No inbound route exists

- **WHEN** cluster resources for the release are listed
- **THEN** there is no IngressRoute and no externally reachable Service
- **AND** Slack messages still arrive over the outbound socket

### Requirement: Egress is limited to DNS, LiteLLM, and HTTPS

A NetworkPolicy SHALL allow DNS, in-cluster LiteLLM on port 4000, and outbound TCP 443, and SHALL
deny everything else. The residual breadth of 443 SHALL be documented, because the CNI enforces
L3/L4 and cannot restrict by Slack hostname.

#### Scenario: The Kubernetes API is unreachable from the agent

- **WHEN** the gateway tries to reach the API server or another in-cluster service outside the
  allowed set
- **THEN** the connection is denied

### Requirement: Credentials come from existing secrets by reference

The Pod SHALL consume `OPENAI_API_KEY` from `litellm-auth-credentials` and Slack tokens from
`mcp-slack-token` through `envFrom` or `secretKeyRef`. No key SHALL appear in a values file, a
ConfigMap, or a rendered manifest.

#### Scenario: No credential is rendered

- **WHEN** the Helm output is searched for key material
- **THEN** only secret references are present

### Requirement: The model path is the cluster LiteLLM endpoint

The agent SHALL use the `custom` provider with `base_url` pointing at LiteLLM's `/v1` endpoint and
model alias `opencode-go/deepseek-v4.1-flash`. It SHALL NOT call a public model API directly.

#### Scenario: A turn is served by LiteLLM

- **WHEN** a message reaches the agent
- **THEN** the request is served by in-cluster LiteLLM
- **AND** the reply is delivered back to the channel

### Requirement: Slack is restricted to the owner

The gateway SHALL enable Slack through `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`, with
`GATEWAY_ALLOW_ALL_USERS=false` and `SLACK_ALLOWED_USERS` containing only the owner's member ID.

#### Scenario: An unlisted user is ignored

- **WHEN** a Slack user outside the allowlist messages the bot
- **THEN** no agent turn runs

### Requirement: State is single-writer and survives restarts

The release SHALL use one replica, `strategy: Recreate`, and a persistent volume mounted at
`/opt/data`. Scaling above one replica with that volume SHALL be rejected by the chart or the
values.

#### Scenario: A rollout does not share the state directory

- **WHEN** the release is upgraded
- **THEN** the old Pod terminates before the new one mounts `/opt/data`

### Requirement: Health is the gateway's own status

Liveness and readiness SHALL run the gateway's status command (`hermes gateway status`) rather than
a TCP or bare HTTP check, so a process that is listening but has lost its channel connection is not
reported healthy.

#### Scenario: A dead channel connection is not ready

- **WHEN** the gateway process is up but its channel socket is not connected
- **THEN** readiness fails
