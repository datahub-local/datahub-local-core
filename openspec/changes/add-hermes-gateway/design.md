# Design

## Context

Hermes is a single gateway process that owns channels, the agent loop, tools, memory and cron. It
does not start a container per session, so the *Pod's* isolation is the security boundary. The
gateway shape matches the OpenClaw release: one workload, one state volume, channel credentials in
secrets, and no inbound surface when Socket Mode is used.

## Decisions

### 1 — Use the jyje chart, published and current

Three options were considered:

- **Fork the agent** (NanoClaw): live-tested, rejected — fork maintenance, bespoke images, and a
  single-node shared volume for session SQLite.
- **`ultraworkers/hermes-agent-helm-chart`**: not published anywhere Helm can consume, pins
  `appVersion: 0.8.0` while the image is `0.22.2`, and its Pod defaults do not match the image it
  targets.
- **`jyje/hermes-agent-helm`**: published as `oci://ghcr.io/jyje/hermes-agent-helm/hermes-agent` and
  on GitHub Pages, chart `1.21.0` targets Hermes `v0.22.2`, and it ships overlays for exactly this
  deployment. CI installs each release on a fresh kind cluster before and after it ships.

The third is chosen. It is a community chart, not an official release; the pin and the upgrade task
make that explicit. It gives us the upstream image with no build step, and its `runtimeClassName`
value supports gVisor.

### 2 — The restricted profile is the security baseline

`values-hardened.yaml` is layered into the release:

- `runAsNonRoot: true`, uid/gid `10000` (the image's `hermes` user), `fsGroup: 10000`;
- `readOnlyRootFilesystem: true`;
- `/run` and `/tmp` as size-bounded memory `emptyDir`s — s6-overlay's init lives under `/run` and
  must be writable and executable, and the agent's tools need `/tmp`;
- `allowPrivilegeEscalation: false`, all capabilities dropped;
- `SeccompProfile: RuntimeDefault`.

The `/run` mount is the part that is easy to get wrong. Verified against `v0.22.2`: pinning an
arbitrary `--user` without a writable `/run` fails at s6 stage0, and a root-owned tmpfs over `/run`
fails the same way. The chart's memory `emptyDir` with `fsGroup` ownership is the supported shape;
its overlay documents that CI boots it. We still verify it on this cluster.

The chart also turns off service-account token mounting by default, which the release keeps.

### 3 — gVisor

The cluster exposes `runtimeClassName: gvisor` (`runsc`). The chart sets it on the Pod, so the
gateway, its tools and its init containers share the sandbox. This is the main reason Hermes wins
over the NanoClaw path: the agent's shell runs in a user-space kernel, not on the node, and it costs
one values key.

`[UNVERIFIED]` until the live run: the hardened profile and gVisor together, and any Chromium use
inside the sandbox. The first release keeps browser tools off.

### 4 — No inbound surface

`hermes gateway run` is outbound-only. Slack uses Socket Mode, so no public URL, Service or Ingress
is needed. Dashboard, API server and webhook stay disabled; the chart's NetworkPolicy denies ingress
by default, which matches.

This removes the ingress, oauth2-proxy and gateway-token surface that OpenClaw required for its
Control UI.

### 5 — Network boundary

The chart's NetworkPolicy:

- `enabled: true`, `allowDns: true`;
- `blockPrivateEgress: true`, so RFC1918 and the cloud metadata endpoint are denied by default;
- one `extraEgress` rule for LiteLLM, scoped to the `data` namespace and the LiteLLM Pod label, port
  4000;
- public internet stays allowed, which is what Slack's WSS endpoint needs.

Verified on this cluster from an earlier agent Pod: the network-policy controller denies a direct
LiteLLM call unless the policy allows it, and allows the named destination. The 443-to-internet leg
is necessarily broad because the CNI enforces L3/L4, not FQDN; narrowing it needs an egress proxy or
a Cilium FQDN policy, neither of which is installed.

### 6 — Credentials by reference

`extraEnvFrom` the existing secrets:

- `litellm-auth-credentials` → `OPENAI_API_KEY` (the LiteLLM key);
- `mcp-slack-token` → `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`.

The chart's `env` map is set to `OPENAI_API_KEY: null`, not `{}`: Helm keeps the default
`sk-REPLACE_ME` when the override is an empty map, and a null deletes the key so the chart's Secret
renders empty. The real key arrives from the later `envFrom` source, which wins the duplicate key.
No key enters values or a ConfigMap. Hermes keeps the model key in-process; mitigations are a read-only LiteLLM key,
`security.redact_secrets`, and gVisor. A credential gateway would be stronger, but Hermes has no
equivalent seam and this is a single-tenant homelab gateway.

### 7 — Model path

The chart's custom-provider shape maps directly onto LiteLLM:

```yaml
config:
  providers:
    litellm:
      base_url: http://<release>-data-litellm.data.svc.cluster.local:4000/v1
      key_env: OPENAI_API_KEY
      discover_models: true
  model:
    provider: litellm
    default: opencode-go/deepseek-v4.1-flash
```

The endpoint was probed from inside the cluster: `POST /v1/chat/completions` for that alias returned
HTTP 200. Auxiliary tasks default to the main model; per-task overrides can come later if cost
matters.

### 8 — Slack reuses the existing app

Live checks against `mcp-slack-token`:

- `auth.test` → ok, bot `homelab` (`U08SHC076NL`) in `DataHub.local`;
- `apps.connections.open` → ok, so Socket Mode is enabled;
- the only human member is `alvsanand` (`U08RV08387L`), the sole `SLACK_ALLOWED_USERS` entry;
- `GATEWAY_ALLOW_ALL_USERS=false`.

The Slack MCP server uses the app over stdio, not Socket Mode, so there is no competing socket
connection. Event subscriptions and bot scopes cannot be read with a bot token. Hermes needs
`message.im`, `message.channels`, `app_mention` and `files:read`; if the app lacks them it will
connect but stay silent. A live DM is the test, and a dedicated app is the fallback.

### 9 — State and lifecycle

- One replica; the chart forces `Recreate` when persistence is enabled, so the new Pod cannot race
  the RWO volume.
- 5 Gi Longhorn PVC at `/opt/data`; RWO is enough because only one Pod mounts it. No node pin, so
  the gateway can reschedule.
- `terminationGracePeriodSeconds` stays at the default unless the gateway drain is raised; the
  image's current default interrupts in-flight work and exits fast. If `restart_drain_timeout` is
  ever set, the grace period must exceed it.
- Probes use `hermes gateway status` as an `exec` check. A TCP check would call a listening process
  healthy even after it lost its channel socket.

### 10 — Explicitly out of scope

Dashboard and its ingress, API server/webhook, multi-tenant or team mode, channels other than Slack,
browser tools under gVisor, and a dedicated credential gateway.

## Risks

- **Community chart.** Pinned version and Renovate tracking; upgrades are reviewed against the
  chart changelog, not auto-merged blindly.
- **Hardened profile + gVisor is a new combination.** The chart verifies the profile on kind, not
  under gVisor. A failed start is a release blocker, not something to paper over with a writable
  rootfs.
- **Broad HTTPS egress.** Required by Slack with an L3/L4 CNI.
- **Slack event scopes.** Socket Mode works; delivery is unproven until a DM is answered.
- **Rootless image contract.** The chart's uid 10000 is the image's own user; a future image that
  changes that uid requires a values change.
