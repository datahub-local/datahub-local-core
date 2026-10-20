# Tasks

## 1. Release

- [ ] 1.1 Add a `hermes` release to `releases/automation/helmfile.yaml.gotmpl` on `app-template`.
- [ ] 1.2 Add `releases/automation/values/hermes.yaml.gotmpl`: one controller, `Recreate`, one
  replica, `/opt/data` PVC, `/tmp` emptyDir, 1 Gi memory `/dev/shm`, no Service.
- [ ] 1.3 Pin `nousresearch/hermes-agent:v0.22.2` by index digest
  `sha256:36099926da316742423544e055d4734777105ffe6341873af5459b957d0c2919`; add the image to
  `values/_version.yaml` so Renovate tracks it.
- [ ] 1.4 `helm template` renders and `openspec validate --all` passes.

## 2. Runtime security

- [ ] 2.1 Set `runtimeClassName: gvisor` and confirm the Pod is admitted and serves a turn.
- [ ] 2.2 Start the image entrypoint as root with `HERMES_UID=10000` and `HERMES_GID=10000`;
  confirm `ps` inside the Pod shows the gateway under uid 10000. Do **not** pin `runAsUser` to
  1000/10000 — the image rejects it.
- [ ] 2.3 Drop ALL capabilities, disable privilege escalation, set `RuntimeDefault` seccomp, and
  `automountServiceAccountToken: false`.
- [ ] 2.4 Keep the root filesystem writable for the first release and comment the reason (s6 needs
  `/run`). Record the read-only follow-up: copy the image's `/run` into an emptyDir from an init
  container, mount it back, and re-test.
- [ ] 2.5 Disable the browser toolset until a Chromium launch under gVisor is proven.

## 3. Configuration and credentials

- [ ] 3.1 Render `config.yaml` with `model.provider: custom`, the LiteLLM `/v1` base URL, the
  `opencode-go/deepseek-v4.1-flash` alias, `terminal.backend: local`, `security.redact_secrets`,
  and `approvals.mode: smart` with unattended/cron modes `deny`.
- [ ] 3.2 `envFrom` `litellm-auth-credentials` and `mcp-slack-token`; no key in values or
  ConfigMaps.
- [ ] 3.3 Set `GATEWAY_ALLOW_ALL_USERS=false`, `SLACK_ALLOWED_USERS=U08RV08387L`, and leave every
  other channel disabled.

## 4. Network

- [ ] 4.1 NetworkPolicy: DNS to `kube-system`, LiteLLM on 4000, TCP 443 out; no ingress rules.
- [ ] 4.2 Verify from the Pod: direct LiteLLM is allowed, the Kubernetes API and another in-cluster
  service are denied, Slack's WebSocket connects.
- [ ] 4.3 No IngressRoute, no public Service, no homepage annotation.

## 5. Slack

- [ ] 5.1 Confirm the existing app has Socket Mode (verified: `apps.connections.open` → ok) and the
  events Hermes needs (`message.im`, `message.channels`, `app_mention`) plus `files:read`.
- [ ] 5.2 Send a DM from `U08RV08387L` and get an answer. If the app is silent, create a dedicated
  Hermes Slack app from `hermes slack manifest --agent-view` and move the tokens to a new secret.
- [ ] 5.3 Confirm a user outside the allowlist gets no response.

## 6. Lifecycle and verification

- [ ] 6.1 Wire `hermes gateway status` as the liveness and readiness probe; confirm a Pod with the
  channel socket down fails readiness.
- [ ] 6.2 Set `terminationGracePeriodSeconds: 120` and `strategy: Recreate`; verify an upgrade does
  not mount `/opt/data` twice.
- [ ] 6.3 Live checks: model turn, Slack reply, `ps` uid, gVisor runtime class, NetworkPolicy,
  unexposed dashboard.
- [ ] 6.4 Record the exact failures met on the way in `tasks.md` or `design.md`, not just the
  successful result.
