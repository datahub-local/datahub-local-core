# Design

## Context

Measured on this cluster on 2026-10-18 against
`ghcr.io/openclaw/openclaw:extended-stable-browser` on an amd64 node, not read from upstream docs.

**Image channel.** `extended-stable-browser` resolves to **2026.9.33** while `latest`/`2026.10.4` is
newer. A gateway refuses to open a state database whose schema is newer than the build
(`uses schema 20; this build supports 19`) and exits 78. `extended-stable` moves only on
trailing-month releases, so it is a *stability* channel, not the newest build; a deployment that
starts on `2026.10.4-slim` cannot later move to `extended-stable-browser` without wiping state. Pin a
versioned `-browser` tag for anything that must be reproducible; this release pins the index digest
of `extended-stable-browser` so the moving tag cannot change under it.

**Runtime class — why this release does not set one.** The gateway boots under
`runtimeClassName: gvisor` and its embedded agent path works (an `agent exec` turn reached LiteLLM and
answered), but its HTTP surface is unusable, which kills the whole product surface — Control UI,
CLI-over-gateway, browser control, channels:

| Setup, in-cluster, minimal Node HTTP server | Result |
| --- | --- |
| runc, server on `127.0.0.1`, client → `127.0.0.1` | 200 in 18 ms |
| gvisor, server on `127.0.0.1`, client → `127.0.0.1` | client aborts (SIGABRT), no response |
| gvisor, server on `0.0.0.0`, client → `127.0.0.1` | 200 in 55 ms |

An in-pod client cannot reliably reach a server bound *specifically* to `127.0.0.1`, and the real
gateway is worse than the minimal case: with `gateway.bind: lan` and `httpGet` probes the probe
answers refused → 503 → timeout, and in-pod requests to both the loopback address and the pod IP time
out. So no RuntimeClass is set. The one untried lever is a second containerd handler running `runsc`
with `platform = "ptrace"` instead of the default `systrap`; the attempt was abandoned before the
node restart it needs, so this is an open question rather than a finding.

**Probe shape.** `exec`, not `httpGet`. The `exec` probe is the only one that asserts the JSON body
(`ready === true`) rather than a status code — the Control UI answers unknown paths with a catch-all
200, so a status-only check would pass against a broken gateway. That mattered doubly while the bind
was loopback and a probe against the pod IP could never connect; with the non-loopback bind (below)
an HTTP probe would connect but still prove nothing. In `app-template` a probe also needs
`enabled: true`; omitting it drops the probe silently, which is how the first render came out.

**State-directory lifetime.** The gateway logs a ~315 s drain budget at startup
(`drain=315000ms shutdown=325000ms`). Kubernetes' 30 s default grace period SIGKILLs it mid-drain and
leaves an owner lease behind; the next start refuses with `failed to acquire gateway state ownership |
Another Gateway owner lease is still active for this state directory`. This release sets
`terminationGracePeriodSeconds: 360`.

**Browser.** The `-browser` variant bakes Playwright's Chromium at `~/.cache/ms-playwright`
(`chromium-1243/chrome-linux64/chrome` on amd64, `chrome-linux-arm64` on arm64). It needs
`browser.noSandbox: true` because Chromium's namespace sandbox cannot initialize here — the same
`unshare -U` → `EPERM` under runc with `RuntimeDefault` seccomp measured separately — and a
`/dev/shm` above the 64 Mi pod default. Auto-detection works on amd64 and does **not** on arm64, so
no `executablePath` is set: pinning it hard-codes both the version and the architecture. Note the
cache redirection: `XDG_CACHE_HOME` must be writable because the rootfs is read-only, and it points
away from the baked browser directory, which is why `executablePath` was needed on arm64.

**Model plane.** LiteLLM at
`http://{{ .Values.release_name }}-data-litellm.data.svc.cluster.local:4000/v1`, reached as an
`openai-completions` custom provider with the key from the gateway secret. Verified: the gateway logs
`agent model: litellm/opencode-go/deepseek-v4.1-flash` and an agent turn returns through the proxy
(`status=200`). `request.allowPrivateNetwork: true` is set because the endpoint is RFC1918.

**Plugins and the plugin-API floor.** Four plugins are declared: `slack`, `github`, `diffs`, `google`.
`github` and `google` ship inside the image; the other two install from ClawHub at boot. That install
is what decides the image tag, and the answer is *not* "upgrade the image": the plugin packages carry
the **same dist-tags as core**, so `@openclaw/diffs@extended-stable` installs cleanly on the
2026.9.33 runtime while the bare name resolves to `@latest` (2026.10.4) and is refused with
`requires plugin API >=2026.10.4`. Verified both ways on the 2026.9.33 image:

```
@openclaw/slack@extended-stable        → Installed plugin: slack
@openclaw/brave-plugin@extended-stable → Installed plugin: brave
@openclaw/diffs@extended-stable        → Installed plugin: diffs
@openclaw/duckduckgo-plugin@extended-stable → Installed plugin: duckduckgo
```

So the stability channel is kept, the image is pinned by digest, and the plugins are pinned to the
exact `2026.9.33` the channel resolves to. The project releases daily, and the channel the user wants
is the one that moves slowly; pinning the exact versions is what makes that choice reproducible.

Three traps came out of that: the CLI **exits 0 even when it refuses a plugin**, so neither the exit
code nor a marker file can gate a re-install; the successful installs land in `npm/projects/<id>`, so
a directory check is fragile; and the manifest id can differ from the package name
(`@openclaw/brave-plugin` → id `brave`, `@openclaw/duckduckgo-plugin` → id `duckduckgo`), so config
keys are not package names. The init container therefore installs on every boot; it asserts the
`Installed plugin` line in each install's output and warns on a miss, but never fails the pod on it.

No `plugins.allow` list is set. That list is authoritative when non-empty, and adding it would drop
the bundled `browser` plugin the evaluation proved working — the entries are declared under
`plugins.entries` instead.

**Search.** `tools.web.search.provider` is `duckduckgo`: key-free, and verified working here — the
plugin installs on this runtime and `html.duckduckgo.com/html/?q=…` answers a real 31 KB results page
from inside the cluster (`lite.duckduckgo.com` answers 202, the bot-challenge path, which is the
fragility the docs warn about). The Google plugin is still configured for **Gemini Search grounding** —
AI-synthesized answers with citations via Google Search, the "ask it like Gemini" experience — and
`plugins.entries.google.config.webSearch.model` is set. Switching is one line
(`provider: "gemini"`) once `GEMINI_API_KEY` is delivered; the key is read via `envFrom` so its
absence leaves search unavailable rather than failing the pod. A Gemini credential does exist, inside
n8n's own store rather than as a cluster secret, so this is a delivery step and not a signup.

**MCP.** Sympozium's `fact_server` is the `datahub-local-ai-mcp-homelab-facts` MCPServer resource, an
HTTP server at `http://datahub-local-ai-mcp-homelab-facts.automation.svc:8080/mcp` exporting 18
tools. It is wired as `mcp.servers.homelab_facts` with `transport: "streamable-http"`, and answers an
MCP `initialize` with HTTP 200. No private-network opt-in was needed; OpenClaw's MCP docs do not
document one, unlike the model-provider path, so this should be re-checked if the connection is ever
refused.

## Security review

Reviewed 2026-10-18 against the rendered release and upstream's own
`docs/gateway/security/hardened-baseline.md`; updated 2026-10-19. Findings 1 (tool policy), 4
(plugin pinning) and 5 (image digest) are now applied in the release; the rest remain pending.

### Already sound (verified in the rendered spec)

Non-root UID 1000, `drop: ALL`, `allowPrivilegeEscalation: false` (which implies
`no_new_privs`), `readOnlyRootFilesystem: true`, `seccompProfile: RuntimeDefault`,
`automountServiceAccountToken: false`, and no `hostNetwork`/`hostPID`/`hostIPC`. The gateway binds
`lan` (`0.0.0.0`) with token auth, but only the oauth2-proxy-gated IngressRoute reaches it and
nothing is internet-exposed; the token stays on behind the proxy. Slack defaults to an allowlist
with no channels listed and pairing for DMs. No GitHub credential exists to leak, because the
bundled plugin fetches public content anonymously. Egress policy is designed and its enforcement
was measured, though it is not enabled.

The model credential is **not** the LiteLLM master key: `openclaw-secrets` templates
`OPENAI_API_KEY` from `litellm-root.readOnlyKey`. `datahub-local-secrets` commit `c2707c0`
("read-only litellm key for all clients, add openclaw-secrets") introduced that key for every
client, and the two values differ (the read-only key is a minted LiteLLM virtual key, short by
design — a length comparison against `masterKey` is not the test). That closes the sharpest
version of the privilege finding: the proxy admin credential never reaches the pod.

The shape of that secret is deliberate and worth not "simplifying" later. `openclaw-root` lives in
`secret_roots` even though it holds a single value, because `openclaw-secrets` is assembled by
External Secrets from **two** roots (`openclaw-root` for the gateway token, `litellm-root` for the
model key) and an ExternalSecret reads through a ClusterSecretStore **per source namespace** —
so every key it reads has to sit in `security`. Moving the gateway token to a single-use secret in
`automation` would break the assembly.

### Findings

**1 — No `tools` policy, so the agent has shell and filesystem on the gateway pod.** Highest
severity. OpenClaw's sandboxing is off by default and its docs are explicit: *"If sandboxing is
off, `tools.elevated` changes nothing since exec already runs on the host."* With no
`tools.profile` and no deny list, core tools stay unfiltered, so `group:runtime` (`exec`,
`process`, `code_execution`) and `group:fs` (`read`, `write`, `edit`, `apply_patch`) are live
against the pod. This is what converts a prompt injection into an incident. Upstream's hardened
baseline sets `profile: "messaging"`, denies `group:automation`/`group:runtime`/`group:fs` plus
`sessions_spawn`/`sessions_send`, `fs.workspaceOnly: true`, `exec: { security: "deny", ask:
"always" }`, `elevated.enabled: false`, and `agentToAgent.enabled: false`. Adapted so search,
browser and `bundle-mcp` keep working, that is the fix — and it is now applied: `profile:
"messaging"` with `alsoAllow: ["group:web", "browser"]` (the profile omits both) and
`sessions.visibility: "agent"`; `bundle-mcp` is implicit in the profile.

**2 — The pod environment holds the remaining crown jewels.** The gateway token and the Slack bot
and app tokens are in the pod's environment, because those are the credentials the process itself
needs: `envFrom` is not over-broad here — `openclaw-secrets` carries exactly the gateway token and
the model key, and `mcp-slack-token` the Slack pair. Narrowing it would not remove the exposure,
because any credential the gateway uses to authenticate is readable by anything that can read the
process environment. The exposure is a consequence of finding 1, and finding 1 is the fix; if a
tighter boundary is wanted later, the answer is the shared secret store's sentinel/egress-proxy
path rather than per-key refs.

**3 — Egress is wide open.** The `NetworkPolicy` is designed but not enabled, so the pod can
reach the LAN, the in-cluster API, and every service in the cluster. Cheapest fix, largest
blast-radius reduction.

**4 — Plugin code is fetched from npm at every boot, unpinned.** `@openclaw/slack@extended-stable`
is a *moving* tag, installed by an init container and executed with the pod's environment. A
compromised plugin release inherits finding 2. The CLI also **exits 0 on failure**, so a bad
install is silent. Applied: exact `2026.9.33` pins, and the init container asserts `Installed
plugin` in each install's output, warning loudly on a miss without failing the boot.

**5 — Moving image tag, no digest pin.** `extended-stable-browser` can change without a commit,
and `imagePullPolicy: IfNotPresent` lets different nodes hold different digests. No signature or
attestation verification. Applied: the index digest is pinned, so `IfNotPresent` can no longer
drift; signatures/attestation remain out of scope.

**6 — No Pod Security Admission labels on the `automation` namespace.** Nothing at admission
prevents a later edit from adding a privileged container. Enabling `restricted` must be checked
against the namespace's other pods first.

**7 — `fact_server` accepts unauthenticated calls in-cluster.** Probed anonymously, HTTP 200. Not
this release's defect, but the MCP surface is open to anything in the cluster, not just the
assistant.

**8 — Chromium runs with `noSandbox: true`.** Forced on this cluster (the namespace sandbox
cannot initialise under `RuntimeDefault` seccomp), so a browser RCE lands in the pod's process
space — the same space as finding 2. Findings 1, 2 and 8 chain.

**Minor:** `session.dmScope` unset (the baseline uses `per-channel-peer`); `exec.ask` not set;
the reloader annotation restarts the gateway on secret rotation, which interacts badly with the
360 s drain.

### Correction worth recording

The gateway token is an **auth** credential, not a key. OpenClaw does not encrypt its store at
rest: *"Store values are not encrypted at rest… stored unencrypted in the shared state SQLite
database (`state/openclaw.sqlite`)"*, protected only by 0600/0700 permissions. If encryption at
rest is ever required, the documented path is an external exec provider (1Password, Vault
SecretRefs), not this token.

### Not verified

None of this was exercised at runtime. Tool-policy behaviour, whether `profile: "messaging"`
still permits the browser and MCP tools as expected, and whether the read-only LiteLLM key is
accepted by the proxy for OpenClaw's model calls all need a deploy to confirm. The new
IngressRoute/oauth2-proxy path and the non-loopback bind are likewise unverified until the release
is deployed — in particular that Traefik's WebSocket upgrade and the `allowedOrigins` match hold.

**Credentials for the plugins.** `github` needs none: the bundled plugin resolves public content
anonymously — "requests send no GitHub credentials, cookies, or referrer" — so nothing admin is
involved, which is what "specific creds, not admin" asks for. Every secret is consumed through
`envFrom` against `openclaw-secrets` and `mcp-slack-token` rather than per-key `secretKeyRef`s,
because the chart's schema rejects `optional: true` on a key ref and a key that has not been added yet
must not stop the pod.

**Egress.** Not yet enabled for this release. Measured on the throwaway install with an equivalent
policy: LAN node ssh BLOCKED, in-cluster API `10.43.0.1:443` BLOCKED, public internet OPEN,
LiteLLM:4000 OPEN. Enable it once Slack and the model plane are proven, because a default deny is
easy to misconfigure into a silent channel.

**Slack.** Socket Mode is OpenClaw's default transport, needing the bot token plus an app-level token
carrying `connections:write`. Both halves already exist in `slack-root` and are delivered to
`automation/mcp-slack-token` as `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`, so this release reads that
secret rather than duplicating a credential.

## Goals / Non-Goals

**Goals.** One release in the namespace already used for automation, built on the chart this
repository already uses. No new chart, no new namespace, no new secret store. The four upstream gaps
documented where the code that carries them lives. Slack working as the first channel.

**Non-Goals.** Not adding a cluster-scoped or chart-scoped abstraction beyond the `app-template`
values file. Not choosing the model or the agent's persona beyond a sane default. Not making gVisor
work.

## Decisions

**`app-template`, in `releases/automation`.** The repository already carries six releases on this
chart, including one that pins to amd64 and one that mounts an nginx config, so the shape here is
copied rather than invented. A bespoke chart would have been a second way to do the same thing.

**Reuse `slack-root` rather than mint a second Slack app.** One credential, one place to rotate.

**The LiteLLM key stays a secret.** The provider block references `${OPENAI_API_KEY}`, and the
deployment reads that from `openclaw-secrets`; no key lands in a values file. This mirrors how n8n
and LiteLLM itself receive credentials in this repository.

**The Control UI rides the repo's standard exposure.** A Traefik `websecure` IngressRoute with the
`oauth2-proxy-auth` middleware — mandatory — like every other app here. Nothing is internet-
reachable; Tailscale reaches the ingress hostname. The gateway binds `lan` — the schema's value for
`0.0.0.0` — so Traefik reaches the pod IP and the exec probes still hit `127.0.0.1`; and
`controlUi.allowedOrigins` carries the proxy origin because a non-loopback bind refuses to start
without explicit origins and startup seeds only `localhost`/`127.0.0.1`. Token auth stays on behind
oauth2-proxy: the middleware gates the network, the token gates the gateway.

**The state store stays unencrypted.** Accepted: `state/openclaw.sqlite` behind 0600/0700. If that
ever changes, the documented path is an exec provider (1Password, Vault), not the gateway token.

**Agent content lives beside `datahub-local-ai`.** This release seeds a minimal `AGENTS.md`; the
authored persona and skills are maintained at that side and delivered into the persisted home.

## Risks / Trade-offs

- **One Slack app, two Socket Mode consumers.** The Slack MCP server already holds a socket-mode
  connection with these tokens; Socket Mode rejects a token pair from two different apps but permits
  multiple connections from one app, and Slack may deliver an event to only one of them. Accepted
  with the reuse decision (4.3); if events visibly land on only one consumer, mint OpenClaw its own
  app (a second root in `datahub-local-secrets`).
- **The Slack plugin is not bundled.** The loaded plugin set does not include `slack`, so it must be
  installed into the persisted home, which needs network at startup. The mechanism is a task, not yet
  verified.
- **OpenClaw moves fast** (roughly daily releases, ~9.5k open issues) and its k8s manifests are
  self-described as not production-ready. A pinned tag is required.
- **The Control UI now leaves loopback.** `lan` (`0.0.0.0`) plus an explicit origin list and the
  oauth2-proxy middleware; the gateway token still gates the gateway itself. Tailscale is the only
  path in — no internet reach.

## Migration Plan

Nothing to migrate: nothing is deployed. Adopting the release is additive, and the two throwaway test
namespaces from the evaluation were removed.

## Open Questions

- Does the `ptrace` platform experiment change the runtime decision? It is the only untried lever.
