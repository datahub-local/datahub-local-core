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

### 4 — The dashboard is the only inbound surface

`hermes gateway run` is outbound-only: Slack uses Socket Mode, so the gateway itself needs no public
URL. The one listener that is turned on is the chart's management dashboard, which is the browser
chat and session UI and the only built-in web UI. The API server and the webhook receiver stay
disabled.

The dashboard binds `0.0.0.0:9119` inside the Pod and upstream fails closed without an auth
provider, so it signs in against the cluster's dex. That means:

- one Traefik `IngressRoute` for `automation-hermes.<gateway_hostname>` in
  `releases/automation/templates/ingress_route.yaml`, backed by the release's Service on port 9119,
  with a homepage entry — no `oauth2-proxy` middleware, because the dashboard's own OIDC gate is
  mandatory and a second login would only be a second hop;
- `dashboard.publicUrl` set explicitly, since the chart derives it from a chart-managed Ingress this
  release does not use, and the OIDC callback is built from it;
- `dashboard.trustedProxies` listing Traefik's node network (`192.168.31.0/24`) and the pod CIDR
  (`10.42.0.0/16`): Traefik runs hostNetwork, so the dashboard sees a node address, and without the
  list the session cookies are silently not marked `Secure`;
- a NetworkPolicy `extraIngress` for port 9119 from that node network, because the chart's policy
  denies all inbound by default.

The dashboard shows API keys to whoever signs in and can create shell hooks, so sign-in is shell
access to the Pod; dex is the access control, and the client is restricted there.

This still removes the gateway-token surface OpenClaw required for its Control UI.

### 5 — Network boundary

The chart's NetworkPolicy:

- `enabled: true`, `allowDns: true`;
- `blockPrivateEgress: true`, so RFC1918 and the cloud metadata endpoint are denied by default;
- one `extraEgress` rule for LiteLLM, scoped to the `data` namespace and the LiteLLM Pod label, port
  4000;
- one `extraEgress` rule for the Traefik node network, port 443: dex is published through Traefik
  (hostNetwork), so the issuer resolves inside RFC1918 and OIDC discovery is otherwise denied;
- one `extraIngress` rule for the dashboard, port 9119, from Traefik's node network and the pod CIDR.
  The pod CIDR is not belt-and-braces: verified on this cluster, a hostNetwork Traefik on another
  node reaches a gVisor sandbox SNATed to the pod network's gateway address (`10.42.<n>.0/.1`), not
  to `192.168.31.<node>`. With only the node block, the router on the pod's own node answered and
  every other replica produced 502 Bad Gateway for the same service;
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

The dashboard's dex client secret is the exception to "no key in a rendered manifest": it is the
shared value the other dex clients already use, it lives in `/helm-values/security.yaml` rather than
this repository, and it has to reach the Pod as `HERMES_DASHBOARD_OIDC_CLIENT_SECRET` because
`config.dashboard.oauth.self_hosted` renders into a ConfigMap.

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

The Slack MCP server uses the app over stdio, not Socket Mode, so the tool surface adds no socket;
the channel does, and the Sympozium responder adds a second one on the same app. Event subscriptions
and bot scopes cannot be read with a bot token. Hermes needs
`message.im`, `message.channels`, `app_mention` and `files:read`; if the app lacks them it will
connect but stay silent. A live message in `#agent-hermes` is the test, and a dedicated app is the
fallback.

Hermes is scoped to `#agent-hermes` (`C0CBX92B6PQ`, bot and `alvsanand` already members) with
`SLACK_ALLOWED_CHANNELS` and `SLACK_FREE_RESPONSE_CHANNELS`, so it answers plain messages there
without an @mention. The Sympozium channel responder mounts the same Secret and opens its own Socket
Mode connection on the same app with `SLACK_ALLOWED_TRIGGERS=mention,dm`; plain channel messages are
outside that trigger set, which keeps the two apart in practice, but Slack still splits an app's
events across its connections, so a DM can land on either one.

### 9 — State and lifecycle

- One replica; the chart forces `Recreate` when persistence is enabled, so the new Pod cannot race
  the RWO volume.
- 5 Gi Longhorn PVC at `/opt/data`; RWO is enough because only one Pod mounts it. Pinned to
  `datahublocal-amd-1` by hostname, which gives up rescheduling: gVisor drives the sandbox clock
  from the host TSC, amd-2's kernel has blacklisted the TSC (`available_clocksource` is
  `hpet acpi_pm` only), so `CLOCK_MONOTONIC` there jumps backwards by up to 1.6 s — measured on a
  fresh sandbox — and Node's `GetNowUint64` `CHECK_GE` aborts the dashboard chat TUI at start-up
  (53 of 800 `node` starts on the running Pod). amd-1 reports `tsc` as its clocksource and is clean.
- `terminationGracePeriodSeconds` stays at the default unless the gateway drain is raised; the
  image's current default interrupts in-flight work and exits fast. If `restart_drain_timeout` is
  ever set, the grace period must exceed it.
- Probes ask s6 for the supervised gateway service (`s6-svstat`) and, for readiness, curl the
  dashboard port so Traefik does not route to a Pod whose dashboard has not started listening yet —
  the first boot syncs bundled skills and can take minutes. `hermes gateway status` is the
  documented check but takes ~35 s per call in this Pod and only reports the process, so it is not
  a probe.

### 10 — MCP tools are the Sympozium servers already in the namespace

The namespace already runs seven MCP servers for Sympozium (`k8s`, `argocd`, `github`, `grafana`,
`postgres`, `trino`, `slack`). Their stdio adapter publishes each as a plain-HTTP MCP endpoint on
`Service:8080`, so Hermes needs only a `config.mcp_servers` entry per server plus one egress rule to
the `app.kubernetes.io/name: mcpserver` pods — no new Deployment, no bridge, and no credential: the
adapter reuses the `mcp-*-token` secrets its Deployments already mount.

Verified from another Pod in this namespace: `initialize` over `POST /mcp` answers for all seven at
the protocol version each one supports, and `GET` answers 405, so the endpoint is HTTP-transport MCP
rather than SSE.

`slack` is deliberately both a channel and an MCP tool surface. The channel is the Socket Mode
connection Hermes makes itself; the MCP server exposes the Slack Web API as tools (search, read,
post). They share the `mcp-slack-token` Secret but not a connection, and a second `apps.connections.open`
is not requested.

One operational trap: `bootstrap.overwrite` is `false`, so the chart's `seed-config` init container
skips an existing `config.yaml` and a new key never reaches a live volume. Adding `mcp_servers` (or any
later config key) therefore needs one deploy with `bootstrap.overwrite: true`; the flag goes back to
`false` so runtime config edits survive later rollouts. The same caveat already applies to
`dashboard.public_url` and `trusted_proxies`.

### 11 — Start-up cost is a feature of the deployment, not of resume

Every dashboard resume opens a PTY and starts a new CLI process; nothing is reused, so resume costs
the same as a fresh session. Measured on the release Pod: `import hermes_cli.main` 7.8–9.4 s,
`hermes mcp list` 10–18 s, a one-shot turn 55–65 s to first token. Stack sampling attributes the
silent part to module compilation, a `/proc/*/fd` scan for stale SQLite WAL holders, a glob in
update-pause recovery on the Longhorn volume, MCP discovery, and the environment probe.

Two changes cut it. The image runs with `PYTHONDONTWRITEBYTECODE=1` and ships almost no `.pyc`
(three files in `hermes_cli/__pycache__`), so each process compiles the tree; setting it to `0` with
`PYTHONPYCACHEPREFIX=/opt/data/.pycache` measured 10.1 s cold → 3.0 s warm for the same import. And
because the work is CPU-bound, the Pod is pinned to the amd64 nodes — gVisor's RuntimeClass only
supplies `datahub.local/gvisor`, so the arch selector merges with it rather than replacing it.

The v0.22.5 image adds a second, unrelated cost on the dashboard path. Every chat PTY now passes
`profile=default`, which resolves to `/opt/data`, so `_resolve_chat_argv` skips
`HERMES_TUI_GATEWAY_URL` and the TUI bootstraps a gateway of its own. That discovery refuses a
`HERMES_HOME` it does not own (`unsafe_control_path`), and the Longhorn mountpoint is owned by root:
the chart's `seed-config` chowns it only when that container starts as root, which the hardened
profile prevents by running it as 10000. The TUI then backs off 1+2+4+8+16+30 s and the prompt stays
queued. A root init container chowns the mountpoint alone (everything inside is already 10000), and
the TUI attaches to the s6 gateway again; the main container keeps its non-root profile.

### 12 — Explicitly out of scope

API server/webhook, multi-tenant or team mode, channels other than Slack, browser tools under gVisor,
a dedicated credential gateway, and a Postgres-backed state store.

On that last one: Hermes v0.22.2 keeps all of its state in SQLite. `SessionDB` in `hermes_state.py`
hardcodes `sqlite3.connect`, and the only knob is `config.database.journal_mode`; the pluggable
provider that would allow Postgres is still an open RFC ([#23717][rfc], `needs-decision`). The
`asyncpg` dependency belongs to the Matrix extra, not core state. Longhorn is a network filesystem,
so Hermes detects it and falls back to `journal_mode: DELETE` — its documented mitigation, WAL
concurrency off. Revisit when the provider seam ships.

[rfc]: https://github.com/NousResearch/hermes-agent/issues/23717

## Risks

- **Community chart.** Pinned version and Renovate tracking; upgrades are reviewed against the
  chart changelog, not auto-merged blindly.
- **Hardened profile + gVisor is a new combination.** The chart verifies the profile on kind, not
  under gVisor. A failed start is a release blocker, not something to paper over with a writable
  rootfs.
- **Broad HTTPS egress.** Required by Slack with an L3/L4 CNI.
- **Slack delivery is unproven.** The shared app also holds a Socket Mode connection from the
  Sympozium channel responder, and Slack splits an app's events across its connections, so a message
  in `#agent-hermes` can land on either one. Scoping Hermes to that channel with free-response keeps
  plain channel messages with Hermes (the responder's triggers are `mention,dm`); DMs stay a coin
  flip until a dedicated app exists.
- **Node TUI vs. gVisor's clock.** The dashboard chat is a Node process, and Node aborts on a
  backwards `CLOCK_MONOTONIC` (`GetNowUint64`). gVisor inherits the host TSC, so the Pod is pinned to
  amd-1; amd-2 would crash roughly one in fifteen session starts.
- **Dashboard is shell access.** Whoever signs in can read API keys and create shell hooks, so the
  dex client is the access control and nothing else may be granted on it.
- **Dashboard host changes are sticky.** `public_url` and `trusted_proxies` are written into
  `config.yaml` on first seed; changing host or proxies later needs `bootstrap.overwrite=true`, and a
  stale `public_url` breaks the OIDC callback.
- **Rootless image contract.** The chart's uid 10000 is the image's own user; a future image that
  changes that uid requires a values change.
