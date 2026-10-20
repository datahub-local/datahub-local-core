# Design

## Context

Hermes is a single gateway process that owns the channels, the agent loop, tools, memory and cron.
Unlike NanoClaw it does not start a container per session; tools execute in the gateway's own
environment. That makes the *pod's* isolation the security boundary, which is why this design is
mostly about the runtime class and the network, not about a driver.

The gateway shape matches the OpenClaw release: one Deployment, one PVC, channel credentials in
secrets, and a Service only if something needs to reach it. Nothing else in the cluster needs to
change.

## Decisions

### 1 — No fork, and no community chart

NanoClaw's live PoC proved the seam works, but it required a ~400-line Kubernetes driver in a fork,
two bespoke images, and a single-node volume so the host and agent could share SQLite files. Hermes
needs none of that: the upstream image runs the gateway, channels are configuration, and the image
is published.

The community Helm chart was still not used directly:

- it is not published (no Helm repository, no release artifact, no Pages index), so consuming it
  would mean vendoring the chart into this repository or forking the chart repository;
- its `appVersion` is 0.8.0 while the published image is 0.22.2, so it lags the agent it packages;
- its pod defaults do not match the image it targets. It sets `runAsUser: 1000` and
  `readOnlyRootFilesystem: true`, but the image rejects arbitrary UIDs and its s6 bootstrap expects
  a root start (verified below).

The house harness (`app-template`) already covers Deployment, PVC, Service, ConfigMap, probes and
raw resources, and every automation release uses it. The chart is used as a specification of intent,
not as a dependency.

### 2 — The image's entrypoint dictates the privilege model

This was verified against `nousresearch/hermes-agent:v0.22.2`, not inferred:

- the image ships an s6-overlay tree and a `hermes` user at uid/gid **10000**;
- `docker run --user 10000:10000` fails: s6 stage0 cannot enter `/run/s6` and the entrypoint
  explicitly rejects an arbitrary `--user` UID;
- starting as root with `HERMES_UID`/`HERMES_GID` works; the bootstrap remaps the `hermes` user and
  the long-running gateway drops to it;
- mounting an empty tmpfs over `/run` breaks s6, because the basedir is baked into the image's
  `/run`;
- `readOnlyRootFilesystem: true` therefore cannot be taken from the community chart as-is: s6 needs
  to write under `/run`, and that directory is part of the root filesystem.

Consequences for this release:

- start as root (`runAsNonRoot: false`), set `HERMES_UID`/`HERMES_GID` to the target uid, and let
  the image drop the gateway process. The root process is the s6 supervisor only;
- keep the root filesystem writable for the first release, and record the deviation. A follow-up can
  copy the image's `/run` into an emptyDir from an init container and mount it back, which is the
  only path to a read-only root filesystem with this image; that is a task, not a claim;
- drop all capabilities, disable service-account token mounting, use `RuntimeDefault` seccomp, and
  keep the mutable surface to `/opt/data`, `/tmp`, and `/run`.

`gVisor` is what makes the root supervisor acceptable: it cannot reach the node's kernel directly,
and the gateway process itself is unprivileged.

### 3 — gVisor, not a RunnerClass per workload

The cluster already exposes `runtimeClassName: gvisor` (`runsc`). Every container in the Pod —
init, gateway, dashboard — inherits it. This is the strongest boundary available here: stronger than
runc, which is what NanoClaw's per-session containers would have used, and much stronger than
OpenClaw's in-process separation.

`[UNVERIFIED]` Chromium and the browser tools under gVisor. The first release disables the browser
toolset; enabling it is a separate task with its own test.

### 4 — No inbound surface

Hermes uses Slack **Socket Mode**, so it opens an outbound WebSocket and needs no public URL. The
release therefore has no IngressRoute, no Service, and no homepage entry. The dashboard that the
image supervises stays bound inside the Pod and is not exposed. This removes the ingress, oauth2-proxy
and token surface that OpenClaw needed for its Control UI.

### 5 — Network boundary

NetworkPolicy egress:

- DNS to `kube-system` (UDP/TCP 53);
- in-cluster LiteLLM on `data` port 4000;
- TCP 443 to the internet, for Slack's WSS endpoint and the web tools Hermes may call.

Ingress: none. The 443 rule is broad because the cluster's CNI enforces L3/L4, not FQDN, policy;
allowing Slack necessarily allows any HTTPS destination. The alternative is a Cilium FQDN policy or
an egress proxy, neither of which is installed. This is named as a residual risk rather than hidden.

`[VERIFIED]` on this cluster: a NetworkPolicy applied to an agent pod blocked direct LiteLLM access
and allowed only the named destination. The same controller (`kube-router`) enforces this policy.

### 6 — Credentials stay in Kubernetes secrets

`envFrom` the existing secrets:

- `litellm-auth-credentials` → `OPENAI_API_KEY` (the LiteLLM key);
- `mcp-slack-token` → `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`.

No key is rendered into values or a ConfigMap. Hermes keeps the model key in the gateway process, so
there is no equivalent of a credential gateway here; the mitigations are a read-only LiteLLM key,
`security.redact_secrets`, MCP environment filtering, and gVisor. This is weaker than a vault and is
accepted for a single-tenant homelab gateway.

### 7 — Model path

LiteLLM is OpenAI-compatible, which is Hermes' native path:

```yaml
model:
  provider: custom
  default: opencode-go/deepseek-v4.1-flash
  base_url: http://<release>-data-litellm.data.svc.cluster.local:4000/v1
```

`OPENAI_API_KEY` supplies the bearer token. The endpoint was probed from inside the cluster:
`POST /v1/chat/completions` for that alias returned HTTP 200. Auxiliary tasks (compression, titles,
approval scoring) default to the main model; that cost is accepted, with per-task overrides possible
later.

### 8 — Slack reuses the existing app

The existing app (`automation/mcp-slack-token`) is the `homelab` bot in `DataHub.local`. Checks
against the live tokens:

- `auth.test` → ok, bot `U08SHC076NL`;
- `apps.connections.open` → ok, so Socket Mode is enabled;
- the only human member is `alvsanand` (`U08RV08387L`), who becomes `SLACK_ALLOWED_USERS`.

The Slack MCP server runs the same app as **stdio**, so it does not hold a Socket Mode connection;
Hermes can own the socket without the delivery conflict OpenClaw accepted. The app's event
subscriptions and bot scopes are not readable with a bot token. Hermes needs `message.im`,
`message.channels`, `app_mention` and `files:read`; if the app lacks them the bot will connect but
stay silent. Verifying/adding them is a task, and a dedicated Hermes app is the fallback.

### 9 — State and lifecycle

- One replica, `strategy: Recreate`: `HERMES_HOME` (`/opt/data`) is mutable and single-writer.
- 5 Gi Longhorn PVC. RWO is enough because only one Pod mounts it; no node pin is needed, so the
  gateway can reschedule.
- `terminationGracePeriodSeconds` long enough for the gateway to finish a turn; the community
  chart uses 120 s.
- Probes use the gateway's own status command (`hermes gateway status`), not a TCP check: a process
  that listens but has lost its channel socket is not healthy.

### 10 — Explicitly out of scope

Operator mode and `HermesTenant` CRDs, multi-tenant isolation, the dashboard behind ingress, the
browser under gVisor, channels other than Slack, and a dedicated credential gateway.

## Risks

- **The image's root entrypoint.** It is upstream's supported model, but it is a root supervisor.
  gVisor, dropped capabilities and no SA token are the compensating controls; a future image that
  supports non-root s6 would remove the deviation.
- **Writable root filesystem.** Accepted until the `/run` copy is proven; the mutable surface is
  still limited by mount layout.
- **Broad 443 egress.** Required by Slack with an L3/L4 CNI. An egress proxy would narrow it.
- **Slack app scopes.** Socket Mode works, but event delivery is unproven until a DM is answered.
- **Unofficial chart drift.** We copy its intent, not its code; upgrades are ours to review.
