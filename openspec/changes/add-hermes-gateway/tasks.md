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
- [ ] 3.2 Verify from the Pod: LiteLLM 4000 allowed, the Kubernetes API and other private
  addresses denied, Slack's WebSocket connects.
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
- [x] 3b.4 `extraIngress` for port 9119 from `192.168.31.0/24`.
- [x] 3b.5 IngressRoute `automation-hermes.<gateway_hostname>` to the dashboard port with a
  homepage entry, without an `oauth2-proxy` middleware.
- [ ] 3b.6 Register the dex staticClient `hermes` with redirect URI
  `https://automation-hermes.<gateway_hostname>/auth/callback` and the shared secret (dex lives in
  another repository).
- [ ] 3b.7 Sign in through dex, confirm `/api/auth/me` reports the provider and the session cookies
  are `Secure`.

## 4. Slack

- [ ] 4.1 Confirm the existing app has the events Hermes needs (`message.im`,
  `message.channels`, `app_mention`) and `files:read`. Socket Mode is already verified
  (`apps.connections.open` → ok, bot `homelab`, team `DataHub.local`).
- [ ] 4.2 DM from `U08RV08387L` and get an answer. If the app is silent, create a dedicated Hermes
  Slack app from `hermes slack manifest --agent-view` and move the tokens to a new secret.
- [ ] 4.3 Confirm a user outside the allowlist gets no response.

## 5. Lifecycle and verification

- [ ] 5.1 Probe the s6-supervised gateway service (`s6-svstat`) for liveness, readiness and startup,
  with readiness also requiring the dashboard on 9119; `hermes gateway status` is too slow (~35 s)
  and only reports the process. Verify readiness fails while the gateway service is down.
- [ ] 5.2 Keep the chart's `Recreate` strategy; verify an upgrade does not attempt to mount
  `/opt/data` twice.
- [ ] 5.3 Live checks: Pod admitted under gVisor, process uid 10000, read-only rootfs, model turn,
  Slack reply, NetworkPolicy, no exposed dashboard.
- [ ] 5.4 Record the exact failures met on the way here — the hardened profile under gVisor is the
  one combination the chart's CI does not cover.
- [ ] 5.5 Confirm the chart's `helm test` passes (it checks the image/entrypoint path).
- [ ] 5.6 Revisit Postgres-backed state when upstream lands the `SessionDBProvider` seam
  (NousResearch/hermes-agent#23717); nothing to configure in v0.22.2.
