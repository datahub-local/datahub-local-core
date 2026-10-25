# Tasks

## 1. Chart and release

- [x] 1.1 Add `hermes-agent` to `values/_version.yaml` under `helm_chart_version`:
  `repository: oci://ghcr.io/jyje/hermes-agent-helm`, `version: 1.21.0`, and
  `nousresearch/hermes-agent: v0.22.2` under `container_image_version`.
- [x] 1.2 Add a `hermes` release to `releases/automation/helmfile.yaml.gotmpl` using
  `oci://ghcr.io/jyje/hermes-agent-helm/hermes-agent` at the pinned version.
- [x] 1.3 Add `releases/automation/values/hermes.yaml.gotmpl`. Copy the chart's
  `values-hardened.yaml` profile into it (the chart's file is not a separate values source at
  install time) and comment its provenance and the `/run` reason.
- [x] 1.4 Set `runtimeClassName: gvisor`, `controller.type: deployment`, `replicaCount: 1`,
  `persistence.size: 5Gi`, `storageClass: longhorn`.
- [x] 1.5 Keep `dashboard`, `apiServer`, `webhook` and all Teams features disabled; no Service and
  no IngressRoute.
- [x] 1.6 Render with `helm template` and confirm: uid 10000, read-only rootfs, `/run` and `/tmp`
  memory emptyDirs, gVisor, 5 Gi PVC, no Service, no ingress.

## 2. Configuration and credentials

- [x] 2.1 `config.providers.litellm`: `base_url` at the release's LiteLLM Service `/v1`,
  `key_env: OPENAI_API_KEY`, `discover_models: true`; `model.provider: litellm`,
  `model.default: opencode-go/deepseek-v4.1-flash`; `terminal.backend: local`.
- [x] 2.2 `env: { OPENAI_API_KEY: null }` so the chart's Secret renders empty (an empty map
  leaves the default `sk-REPLACE_ME` in place); `extraEnvFrom` the existing
  `litellm-auth-credentials` and `mcp-slack-token` secrets. The later `envFrom` source wins the
  duplicate key.
- [x] 2.3 `extraEnv`: `GATEWAY_ALLOW_ALL_USERS=false`, `SLACK_ALLOWED_USERS=U08RV08387L`; leave
  every other channel unset.
- [x] 2.4 Set `security.redact_secrets: true` and keep approvals at `smart`, with cron/unattended
  modes `deny`.

## 3. Network

- [x] 3.1 `networkPolicy.enabled: true`, `allowDns: true`, `blockPrivateEgress: true`, and one
  `extraEgress` rule for LiteLLM (`data` namespace, `app.kubernetes.io/name: litellm`, port 4000).
- [x] 3.2 Verify from the Pod: LiteLLM 4000 allowed, the Kubernetes API and other private
  addresses denied, Slack's WebSocket connects. Measured: `litellm:4000` connects; `kubernetes.default.svc:443`,
  `10.42.0.1:443` and `192.168.31.100:22` refuse; gateway log `[Slack] Socket Mode connected`.
- [x] 3.3 Confirm the rendered output exposes the dashboard Service and one IngressRoute and no
  apiServer or webhook listener.

## 3b. Dashboard

- [x] 3b.1 `dashboard.enabled: true`, `service.enabled: true`, `dashboard.auth.provider: oidc`,
  `config.dashboard.oauth.self_hosted` issuer `https://security-dex.<gateway_hostname>/dex` and
  client id `hermes`.
- [x] 3b.2 `dashboard.publicUrl: https://automation-hermes.<gateway_hostname>` and
  `dashboard.trustedProxies` listing Traefik's node network plus the pod CIDR.
- [x] 3b.3 `HERMES_DASHBOARD_OIDC_CLIENT_SECRET` in `extraEnv`, from the shared
  `.StateValues.security_github_client_secret`; never in `config.yaml`.
- [x] 3b.4 `extraIngress` for port 9119 from `10.42.0.0/16`: cross-node peers arrive under gVisor
  SNATed to the pod network's gateway address, so a node-only rule answered 502 on every Traefik
  replica except the one on the Pod's own node.
- [x] 3b.5 IngressRoute `automation-hermes.<gateway_hostname>` to the dashboard port with a
  homepage entry, without an `oauth2-proxy` middleware.
- [x] 3b.8 `extraEgress` to `192.168.31.0/24` on port 443: dex resolves to a node address behind
  Traefik, and `blockPrivateEgress` denied it, so `/auth/login` answered 503.
- [x] 3b.6 Register the dex staticClient `hermes` with redirect URI
  `https://automation-hermes.<gateway_hostname>/auth/callback` and the shared secret (dex lives in
  another repository). Present in the dex config Secret, exact callback, `username: alvsanand`.
- [x] 3b.7 Sign in through dex, confirm `/api/auth/me` reports the provider and the session cookies
  are `Secure`. `dashboard-auth.log` has 3 `login_success` and 161 `ws_ticket_minted`;
  `/api/auth/me` without a cookie answers 401 `no_cookie`; `/auth/login?provider=self-hosted` from a
  trusted proxy sets `__Host-hermes_session_pkce … SameSite=none; Secure` and redirects to dex with
  `client_id=hermes`.

## 4. Slack

- [x] 4.1 Confirm the existing app has the events Hermes needs (`message.im`,
  `message.channels`, `app_mention`) and `files:read`. Socket Mode is already verified
  (`apps.connections.open` → ok, bot `homelab`, team `DataHub.local`). `x-oauth-scopes` carries
  `channels:history`, `im:history`, `app_mentions:read`, `files:read`, `chat:write`; only
  `mpim:history` is missing, which matches the group-DM warning the adapter logs.
- [ ] 4.2 Message in `#agent-hermes` (`C0CBX92B6PQ`, Hermes scoped there by
  `SLACK_ALLOWED_CHANNELS` + `SLACK_FREE_RESPONSE_CHANNELS`) from `U08RV08387L` and get an answer.
  If the responder takes the event, create a dedicated Hermes Slack app from
  `hermes slack manifest --agent-view` and move the tokens to a new secret.
- [ ] 4.3 Confirm a user outside the allowlist gets no response.

## 5. Lifecycle and verification

- [x] 5.1 Probe the s6-supervised gateway service (`s6-svstat`) for liveness, readiness and startup,
  with readiness also requiring the dashboard on 9119; `hermes gateway status` is too slow (~35 s)
  and only reports the process. Verified: `s6-svstat /run/service/main-hermes` → `up (pid 136)`, the
  readiness one-liner → `READY-OK`, and `s6-svstat` on a missing service exits 1.
- [x] 5.2 Keep the chart's `Recreate` strategy; verify an upgrade does not attempt to mount
  `/opt/data` twice. Deployment `strategy: Recreate`, 1/1, 0 restarts since the last rollout.
- [x] 5.3 Live checks: Pod admitted under gVisor, process uid 10000, read-only rootfs, model turn,
  Slack reply, NetworkPolicy, dashboard reachable only through the OIDC gate. Measured: runtime
  `gvisor`, `uid=10000(hermes)`, `touch /` → `Permission denied`, model turns in the gateway log,
  `/api/auth/me` → 401 without a cookie.
- [x] 5.4 Record the exact failures met on the way here — the hardened profile under gVisor is the
  one combination the chart's CI does not cover. Recorded in `design.md` §11 and §9.
- [x] 5.5 Dropped: ArgoCD renders the chart, so there is no Helm release object and `helm test` has
  nothing to run against.
- [x] 5.6 Revisit Postgres-backed state when upstream lands the `SessionDBProvider` seam
  (NousResearch/hermes-agent#23717); nothing to configure in v0.22.2.

## 6. MCP tools

- [x] 6.1 `config.mcp_servers` for the seven `…-sympozium-mcp-*` Services in this namespace, HTTP on
  port 8080 at `/mcp`; the stdio adapter needs no credential beyond the tokens its Deployments mount.
- [x] 6.2 `extraEgress` to the `app.kubernetes.io/name: mcpserver` pods on port 8080; without it every
  call is refused, because `blockPrivateEgress` covers the whole namespace.
- [x] 6.3 Seed once with `bootstrap.overwrite: true`: `seed-config` skips an existing `config.yaml`, so
  the new key never reaches the volume otherwise. The flag returns to `false` afterwards.
- [x] 6.4 `hermes mcp test` each server from the Pod and one turn that calls an MCP tool. k8s, argocd,
  grafana, postgres, trino and slack connect and list their tools; `github` fails with
  `duplicate "initialize" received` (reproduced twice), which is the `sympozium-mcp-github` adapter or
  server, not Hermes.

## 7. Start-up latency

- [x] 7.1 `PYTHONDONTWRITEBYTECODE=0` and `PYTHONPYCACHEPREFIX=/opt/data/.pycache`: the image disables
  bytecode writes, so every process recompiled the tree; the same import measured 10.1 s → 3.0 s.
- [x] 7.2 Pin the Pod to `kubernetes.io/arch: amd64`; the gVisor RuntimeClass owns the
  `datahub.local/gvisor` selector and both merge.
- [x] 7.3 Re-measure a resume in the dashboard on the amd64 node: a one-shot turn went 65 s → 8 s and
  a resumed session 57 s → 9 s; `hermes status` 41 s → 3 s. `import hermes_cli.main` is 2.3 s cold and
  0.4 s warm against 7.8–9.4 s before.
- [x] 7.4 v0.22.5 launches the dashboard PTY profile-scoped (`profile=default` resolves to
  `/opt/data`), so `HERMES_TUI_GATEWAY_URL` is skipped and the TUI bootstraps its own gateway;
  discovery refuses the root-owned mountpoint (`unsafe_control_path`) and retries
  1+2+4+8+16+30 s. Chown `/opt/data` to 10000 from a root init container, then confirm a dashboard
  resume attaches to the s6 gateway without the retry. Verified: `tui_gateway_crash.log` shows
  `attached shared gateway … profile=/opt/data` with no backoff.
- [x] 7.5 Confirm the root `chown-data` init container starts under gVisor and that a fresh PVC
  ends up owned by 10000. Verified: init container `chown-data` Completed, `/opt/data` is
  `hermes:hermes`.

## 8. Node TUI under gVisor

- [x] 8.1 Pin the Pod to `kubernetes.io/hostname: datahublocal-amd-1`. The dashboard chat TUI is a
  Node process, and Node aborts when `CLOCK_MONOTONIC` goes backwards (`GetNowUint64` `CHECK_GE`);
  gVisor on amd-2 inherits the host TSC, which that kernel has blacklisted (clocksource is
  `hpet acpi_pm` only), and the sandbox clock jumps back by up to 1.6 s. Measured 53 of 800 `node`
  starts aborting on amd-2, 0 in 7.9 M clock samples on amd-1.
