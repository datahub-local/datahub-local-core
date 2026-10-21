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

### Requirement: Nothing on the network can reach the gateway

The release SHALL NOT create an IngressRoute, a public Service, a dashboard, an API server, or a
homepage entry. Slack SHALL use Socket Mode, which is an outbound connection.

#### Scenario: No inbound route exists

- **WHEN** cluster resources for the release are listed
- **THEN** there is no IngressRoute and no externally reachable Service
- **AND** Slack messages still arrive over the outbound socket

### Requirement: Egress is limited to DNS, LiteLLM, and HTTPS

The chart's NetworkPolicy SHALL be enabled with `allowDns: true` and `blockPrivateEgress: true`, plus
one explicit egress rule for LiteLLM on port 4000. Public HTTPS SHALL remain allowed for Slack. The
residual breadth of HTTPS SHALL be documented, because the CNI enforces L3/L4 and cannot restrict by
hostname.

#### Scenario: The Kubernetes API is unreachable from the agent

- **WHEN** the gateway tries to reach the API server or another private address outside the allowed
  set
- **THEN** the connection is denied

#### Scenario: LiteLLM is reachable

- **WHEN** the gateway calls the in-cluster LiteLLM Service on port 4000
- **THEN** the connection is allowed by the policy

### Requirement: Credentials come from existing secrets by reference

The Pod SHALL consume `OPENAI_API_KEY` from `litellm-auth-credentials` and the Slack tokens from
`mcp-slack-token` through `extraEnvFrom`. The chart's own `env` map SHALL stay empty. No key SHALL
appear in a values file, a ConfigMap, or a rendered manifest.

#### Scenario: No credential is rendered

- **WHEN** the Helm output is searched for key material
- **THEN** only secret references are present

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

### Requirement: Health is the gateway's own status

Liveness and readiness SHALL run `hermes gateway status` as an `exec` probe, so a process that is
listening but has lost its channel connection is not reported healthy.

#### Scenario: A dead channel connection is not ready

- **WHEN** the gateway process is up but its channel socket is not connected
- **THEN** readiness fails
