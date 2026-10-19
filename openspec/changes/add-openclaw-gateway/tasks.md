# Tasks

## 1. Release

- [x] 1.1 Add the release to `releases/automation/helmfile.yaml.gotmpl` on `app-template`, the chart
  the other six automation releases use.
- [x] 1.2 Add `releases/automation/values/openclaw.yaml.gotmpl`: controller on amd64 with
  `strategy: Recreate`, the config `ConfigMap`, the home PVC, an `emptyDir` for `/tmp` and a 256 Mi
  memory `emptyDir` for `/dev/shm`, and a ClusterIP Service on 18789.
- [x] 1.3 Take `openclaw.json` and `AGENTS.md` as `configMaps.config.data`, so no model id, provider
  name or channel id needs a template.
- [x] 1.4 Read secrets by `secretKeyRef` only — `openclaw-secrets` for the gateway token and the
  LiteLLM key, `mcp-slack-token` for the Slack pair. Nothing rendered.
- [x] 1.5 Prove it renders: `helm template` against `app-template` 5.3.0 shows the grace period, the
  amd64 selector, `readOnlyRootFilesystem`, all three probes, the PVC storage class, and the
  `/dev/shm` mount.

## 2. Carry the upstream gaps

- [x] 2.1 `terminationGracePeriodSeconds: 360`, with the drain budget named in the comment.
- [x] 2.2 Probes are `exec` (loopback bind), asserting the JSON body. Note `enabled: true` is
  required — `app-template` drops a probe without it, silently.
- [x] 2.3 Browser config defaults to `headless: true` and `noSandbox: true`, with a 256 Mi `/dev/shm`.
- [x] 2.4 Pin the image to a `-browser` variant and default the pod to `kubernetes.io/arch: amd64`.

## 3. Verify against the live cluster

- [x] 3.1 Install on a throwaway namespace and reach `Ready 1/1`.
- [x] 3.2 Prove the model path: an agent turn through LiteLLM answers (`provider=litellm
  api=openai-completions … status=200`).
- [x] 3.3 Prove the browser: `browser start` → `open https://example.com` → `snapshot` returns refs,
  and an agent turn uses the browser tool to read the page.
- [x] 3.4 Prove an egress policy equivalent to the one this release will use: LAN ssh BLOCKED,
  in-cluster API BLOCKED, public OPEN, LiteLLM OPEN.
- [x] 3.5 Record the sandbox-runtime verdict rather than shipping it: `runtimeClassName: gvisor`
  leaves the HTTP surface unusable and the pod never Ready.

## 4. Slack

- [x] 4.1 Configure the Slack channel for Socket Mode, with both tokens read from
  `automation/mcp-slack-token` (already delivered from the `slack-root` app).
- [x] 4.2 Default `groupPolicy: allowlist` with no channels listed, so the bot cannot answer in a
  channel until one is added deliberately.
- [x] 4.3 Reuse the Slack MCP server's app (`slack-root`): one credential, one rotation. The
  delivery conflict is accepted — Slack permits multiple socket-mode connections from one app and
  may deliver an event to only one consumer; mint a second app if that shows up.
- [ ] 4.4 Install the `slack` plugin into the persisted home (it is not in the bundled set) and prove
  it by sending the bot a DM. Needs a mechanism — an init container or a one-off `plugins install` —
  and network access at that moment.
- [ ] 4.5 Add the channels or users the bot may answer, and pair the first DM.

## 5. Plugins and MCP

- [x] 5.1 Declare the plugin entries in `openclaw.json`: `slack`, `github`, `diffs`, `google`. No
  `plugins.allow` list is set, deliberately — a nonempty allow list is authoritative and would drop
  the bundled `browser` plugin that section 3 verified.
- [x] 5.2 Install the two that are not bundled with the image — `@openclaw/slack` and
  `@openclaw/diffs` — from an init container, every boot.
- [x] 5.3 Pin the installs to the image's own channel tag. The plugin packages carry the same
  dist-tags as core, so `@extended-stable` matches the 2026.9.33 runtime; the bare name resolves to
  `@latest` (2026.10.4) and is refused with `requires plugin API >=2026.10.4`. Verified on the
  2026.9.33 image: `@openclaw/slack@extended-stable`, `@openclaw/diffs@extended-stable` and
  `@openclaw/duckduckgo-plugin@extended-stable` all report `Installed plugin: …`.
- [x] 5.4 Keep the stability channel: `extended-stable-browser`, with the plugins pinned to it, rather
  than moving the image to `2026.10.4-browser`.
- [x] 5.5 Wire Sympozium's `fact_server` — the `datahub-local-ai-mcp-homelab-facts` MCPServer — as
  `mcp.servers.homelab_facts`, streamable HTTP, and confirm the endpoint answers an MCP `initialize`
  with HTTP 200.
- [x] 5.6 Wire **no** GitHub credential: the bundled `github` plugin fetches public content
  anonymously ("requests send no GitHub credentials, cookies, or referrer"), so nothing admin is
  involved.
- [x] 5.7 Read secrets with `envFrom` rather than per-key `secretKeyRef`, because the chart's schema
  rejects `optional: true` on a key ref and a key that has not been added yet must not stop the pod.
- [x] 5.8 Make search work today: `duckduckgo` as the provider, verified installed on this runtime and
  reachable from inside the cluster (31 KB results page from `html.duckduckgo.com`).
- [ ] 5.9 Deliver `GEMINI_API_KEY` to `openclaw-secrets`, then switch `tools.web.search.provider` to
  `gemini` — one line — for Google Search grounding with citations. A Gemini credential already exists
  inside n8n's own credential store, so this is delivery, not signup.
- [ ] 5.10 Verify the plugin set actually loads on the pinned tag: check the gateway's startup plugin
  list names all four, then run one search to prove the provider end to end.
- [ ] 5.11 Re-verify the browser and the probes. The section 3 verification ran before the plugin set
  and the channel tag were settled.
- [ ] 5.12 If authenticated or private GitHub access is ever wanted, mint a fine-grained PAT. The only
  PAT in the cluster is the admin one that `data/github-auth` and the GitHub MCP server share.

## 6. Security findings

Findings only — `design.md` carries the review. Nothing here is applied.

- [x] 6.1 Add the `tools` policy from upstream's hardened baseline, adapted so search, browser and
  `bundle-mcp` keep working: `profile: "messaging"`, deny `group:automation` / `group:runtime` /
  `group:fs` / `sessions_spawn` / `sessions_send`, `fs.workspaceOnly: true`,
  `exec: { security: "deny", ask: "always" }`, `elevated.enabled: false`,
  `agentToAgent.enabled: false`. This is the highest-severity gap: without it the agent has `exec`
  and `fs` on the gateway pod. Applied, with `alsoAllow: ["group:web", "browser"]` — the messaging
  profile omits both — and `sessions.visibility: "agent"` from the same baseline.
- [ ] 6.2 Nothing to narrow: `envFrom` reads exactly the credentials the gateway authenticates
  with (gateway token, model key, Slack pair), so per-key refs would not reduce the exposure. Treat
  this as a consequence of 6.1, and reach for the shared secret store's sentinel/egress-proxy path
  if a tighter boundary is ever wanted.
- [ ] 6.3 Enable the egress `NetworkPolicy` (DNS, LiteLLM, Slack, public) and add an ingress rule.
- [x] 6.4 Pinned the plugin installs to exact `2026.9.33` — what `@extended-stable` resolved to on
  2026-10-19, and the image's plugin API. The CLI still exits 0 on failure, so the init container
  asserts `Installed plugin` in each install's output and warns loudly on a miss; it does not fail
  the boot.
- [x] 6.5 Pinned the image by index digest
  `sha256:a789522a0c6b37d8496a07f114e57dffeb6099970f5cdb448c9f33a179267f28` (resolved 2026-10-19),
  tag kept for readability. `IfNotPresent` is now safe: a digest cannot drift under a moving tag.
- [ ] 6.6 Consider Pod Security Admission `restricted` on `automation` — check the namespace's other
  pods for compliance first.
- [ ] 6.7 Raise the unauthenticated `fact_server` endpoint with the Sympozium side; the MCP surface
  is currently open to anything in the cluster.
- [x] 6.8 Set `session.dmScope: "per-channel-peer"` and `exec.ask: "always"` for parity with the
  baseline.
- [x] 6.9 Encryption at rest accepted as-is: `state/openclaw.sqlite` stays unencrypted behind
  0600/0700. If that ever changes, the path is an exec provider (1Password, Vault), not the gateway
  token.

## 7. Land it

- [x] 7.1 `openclaw-secrets` exists in `datahub-local-secrets` (`c2707c0`): the `openclaw-root`
  gateway token plus `litellm-root.readOnlyKey`, delivered to `automation` by an ExternalSecret, so
  the master key never reaches the pod. The gateway token is auth, not an encryption key —
  OpenClaw's store is unencrypted at rest. Leave `openclaw-root` in `secret_roots`: the secret spans
  two roots and ESO reads per source namespace, so every key it reads must live in `security`.
- [ ] 7.2 Enable an egress `NetworkPolicy` for the release — DNS, LiteLLM, Slack, public internet —
  and confirm the Control UI and an agent turn still work through it.
- [x] 7.3 The Control UI rides the repo's standard exposure: Traefik `websecure` IngressRoute with
  the `oauth2-proxy-auth` middleware, no internet reach, reached over Tailscale. The gateway binds
  `lan` — the schema's value for `0.0.0.0`, so Traefik reaches the pod IP and the exec probes still
  hit `127.0.0.1` — with `controlUi.allowedOrigins` set to the proxy origin, because a non-loopback
  bind refuses to start without it. Token auth stays on behind oauth2-proxy.
- [x] 7.4 Agent content lives beside `datahub-local-ai`: the authored `AGENTS.md` and skills are
  maintained there and delivered into the persisted home; this release keeps only the seed copy.
