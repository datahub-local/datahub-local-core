# Spec Delta

## ADDED Requirements

### Requirement: Each agent session runs as its own Pod

The runtime SHALL realize one `SessionSpec` as one Pod whose containers are exactly the spec's
containers, and SHALL NOT require a Docker daemon, a mounted container socket, or a privileged
container. The Pod SHALL carry the four canonical labels (`nanoclaw-install`, `nanoclaw-group`,
`nanoclaw-session`, `nanoclaw-role`) verbatim so a handle can be rebuilt after a host restart.

#### Scenario: A session is realized without Docker

- **WHEN** the host prepares a session
- **THEN** a Pod exists in the host's namespace with the session's image, command, env and mounts
- **AND** no privileged container and no host container socket are involved

#### Scenario: A surviving session is adopted

- **WHEN** the host restarts while a session Pod is still running
- **THEN** listing by the `nanoclaw-install` label returns that session
- **AND** the handle is reconstructed from the canonical labels, not from host memory

### Requirement: Session state is shared with the host through subPath mounts

The driver SHALL realize every `MountSpec` as a subPath of the session-state PVC at the same
container path, preserving read-only mode. It SHALL NOT mount the whole volume into an agent
container, so paths outside the spec's mounts (the central database, other groups) stay invisible.

#### Scenario: An agent sees only its declared mounts

- **WHEN** an agent container is inspected
- **THEN** its volume mounts are the spec's mounts, each with a `subPath`
- **AND** the volume root is not mounted

#### Scenario: A missing host path fails the session

- **WHEN** a composed mount's host path does not exist under the volume root
- **THEN** the driver refuses the session with a non-retryable spec error
- **AND** no Pod is created

### Requirement: Model credentials never enter an agent Pod

Agent containers SHALL receive a placeholder token and the URL of the in-cluster credential proxy.
The LiteLLM key SHALL live only in the proxy Deployment's environment, sourced from a Secret. The
agent's `ANTHROPIC_BASE_URL` SHALL point at the proxy, and the proxy SHALL add the real key on the
way to LiteLLM.

#### Scenario: An agent turn reaches the model

- **WHEN** an agent calls the model
- **THEN** the request is accepted by LiteLLM through the Anthropic-compatible `/v1/messages`
  endpoint
- **AND** the reply is written to `outbound.db`

#### Scenario: The key is not in the agent

- **WHEN** the agent Pod spec is inspected
- **THEN** no container has the LiteLLM key in its environment or mounts

### Requirement: Agent egress is limited to the proxy

A NetworkPolicy SHALL allow DNS resolution and egress to the credential proxy, and SHALL deny other
egress from agent Pods. The proxy SHALL be the only workload allowed to reach LiteLLM.

#### Scenario: The agent cannot reach the API server

- **WHEN** an agent Pod attempts to reach the Kubernetes API or the internet directly
- **THEN** the connection is blocked

### Requirement: The release runs on the pinned node with its images imported

The host and agent Pods SHALL be scheduled to the node that holds the session-state volume and the
imported images. The driver SHALL report `imageBuild: false` so self-modification refuses a rebuild
it cannot perform, and image pull policy SHALL be `IfNotPresent`.

#### Scenario: A rebuild is refused instead of silently skipped

- **WHEN** an agent requests an image rebuild
- **THEN** the request is denied because the driver has no build daemon

### Requirement: The model path uses the cluster LiteLLM endpoint

The agent model SHALL be the LiteLLM alias `opencode-go/deepseek-v4.1-flash`, reached through the
proxy's Anthropic-compatible path. No new provider implementation or OpenCode dependency SHALL be
required.

#### Scenario: The configured alias answers

- **WHEN** the proxy forwards a `/v1/messages` request for the alias
- **THEN** LiteLLM returns a message response
- **AND** the agent-runner parses it as a normal Claude Agent SDK response

### Requirement: Lifecycle maps to Pod phase

`status()` SHALL report `starting` for a pending Pod, `running` for a running one, `stopped` for a
succeeded one, and `failed` with the container exit code for a failed one. `stop()` SHALL delete the
Pod using the spec's grace period.

#### Scenario: A crashed agent is reported as failed

- **WHEN** the agent container exits non-zero
- **THEN** the session status is `failed` and carries the exit code
- **AND** the host does not treat it as a clean stop
