# Design

## Context

One owner, one long-lived coding agent, reachable from a browser and from Hermes, with a search
tool and a GitHub App identity (§4). The cluster already has Hermes (chat), Sympozium (runs), Traefik,
dex, oauth2-proxy, and LiteLLM. OpenCode supplies the agent, its web UI, and an HTTP API.

The agent's work is this repository's helmfile releases and the uv projects in
`datahub-local-ai`, `datahub-local-ai-mcp` and the site. That fact decides the image before any
workload does: the upstream OpenCode image carries no toolchain.

## Decisions

### 1 — Three workloads, each with one job

| Workload | Runs | Reaches |
|---|---|---|
| `opencode-server` | `opencode serve` + minter sidecar | LiteLLM, the Firecrawl bridge in `automation`, GitHub, package registries, helm chart repositories |
| `opencode-web` | reverse proxy | the server on 4096 |
| `opencode-mcp` | MCP shim | the server on 4096 |

The server is the only stateful piece and is never published. The proxy is the only published
surface. The shim is stateless and can be restarted without losing a session.

### 2 — There is no separate OpenCode web process

`opencode serve` is the v2 API **and the web server**; `opencode pair` hands a browser a link to it.
There is no `opencode web` client container to deploy. The "web pod" is therefore an nginx reverse
proxy in front of the server — it does not run OpenCode. Traefik and oauth2-proxy do the auth; nginx
does the forwarding, because the owner wants the server reachable only through a dedicated pod.

nginx must not buffer SSE (`proxy_buffering off`) and must pass the upgrade headers, or the live
session view stalls. The Basic credential is injected by Traefik, so nginx and the browser never
hold it.

### 3 — Hermes needs a shim because the protocols do not meet

Hermes is an MCP client; `opencode serve` is an HTTP API with Basic auth. OpenCode has no MCP server
and no HTTP ACP (`acp` is stdio), and Hermes is an ACP *server*, not a client. The shim is the
smallest thing that bridges them:

- `run_task(prompt, directory?, session_id?, wait_seconds=120)`;
- `get_session(session_id)`;
- `get_diff(session_id, from_message?, context?)` — the patches, for review;
- `list_sessions(limit?, search?)` — how a stateless shim finds a session again;
- `get_transcript(session_id, limit?)` — the newest messages, oldest first;
- `respond(session_id, form_id | request_id, answer)`;
- `abort_session(session_id)`.

It holds no state. "One active session" is read from `GET /api/session/active`, not from memory, so
a shim restart cannot start a second writer.

It targets the v2 API (`/api/session*`, `/api/experimental/session/:id/wait`). The npm package
`opencode-mcp` is not used: 3.1.0 documents OpenCode 1.x support, with v2 planned for 4.0, and it
exposes 70 tools — context no persona needs. `run_task` waits at most 300 seconds and returns
`running|idle|needs_input|error`; the session itself is unbounded and can live for days.

`question` is allowed in OpenCode so the agent can ask the owner; the shim surfaces it as
`needs_input` and `respond` answers the form or permission. Every other `ask` is denied, because
nobody is watching a prompt.

### 4 — The coder App mints the credential

The server runs for days and its shell is the agent, so it needs a credential that does not expire
mid-session and does not name the owner. It authenticates as the coder GitHub App: the `minter`
sidecar reads `github-app-coder` (`GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`,
`GITHUB_APP_PRIVATE_KEY`) and answers `/token` on loopback, and the git credential helper and the
`gh` wrapper ask it per operation. Nothing is cached under `/opt/data`; an installation token lives
an hour, a session lives days.

This is the credential model `agent-github-identity` introduced; that capability owns the App, its
roots, the derived secrets and the Hermes-side proxy. This release only consumes it. The commit
identity is the bot (`datahub-local-coder[bot]` with the App's noreply address), so the timeline and
the branch history name the agent rather than `alvsanand`.

SSH was tried first and does not work for this workspace: the existing `gitSshKey` is a deploy key
scoped to `datahub-local-ai` (verified with `ssh -T`), and GitHub cannot attach the same key to the
other two repositories. Three deploy keys plus a multi-key agent would work, but it is more moving
parts than one App.

The `opencode-github` ExternalSecret the first draft used is gone. `github-root` never reaches a
container.

### 5 — The image is built in `datahub-local-ai`, with the toolchain baked in

The upstream image is not deployable for this job. `ghcr.io/anomalyco/opencode` is Alpine 3.23 plus
`libgcc`/`libstdc++` and one musl Bun binary: no shell tooling, no `git`, no `helm`, no Python. An
`apk --root` init container can add one binary and still leaves the agent unable to run a release
or a test. The image is therefore ours:

- `datahub-local-ai/agents/adapters/opencode/` builds
  `ghcr.io/datahub-local/datahub-local-ai-opencode-adapter` from `node:22-bookworm-slim` (Debian
  bookworm). Debian is the choice, not Alpine: the Python projects need glibc wheels, and `uv`,
  `helmfile`, `kubectl`, `helm`, `kustomize`, `gh` and `yq` publish static or glibc builds.
- It copies the pinned OpenCode Linux release binary for the target architecture and keeps the
  upstream entrypoint shape (`ENTRYPOINT ["opencode"]`); the core release supplies
  `args: ["serve", …]`. Nothing OpenCode-specific is patched or rebuilt.
- The toolchain is installed at build time and pinned: `git`, `bash`, `curl`, `openssh-client`,
  `ca-certificates`, `jq`, `yq`, `kubectl`, `helm`, `helmfile`, `kustomize`, `gh`, `node`/`npm`,
  `python3` with `venv` and `pip`, `uv`, and the OpenSpec CLI the repositories gate on. `uv` also
  carries a managed Python 3.13 under `/opt/uv/python` (`UV_PYTHON_INSTALL_DIR`), because
  `datahub-local-ai-mcp` requires 3.13 while bookworm ships 3.11.
- `ansible`, `dbt`, `dlt` and every other project dependency are **not** in the image. They are
  resolved by `uv sync` from the checkout's lockfile, which is the only version that matches the
  repository being edited.
- Multi-arch like every image that repository publishes: `linux/amd64` and `linux/arm64`.
- Every tool version is an `ARG` in the Dockerfile and tracked by a Renovate `customManager` in
  `datahub-local-ai/renovate.json`; the weekly adapter rebuild carries base-image CVE fixes. The
  cluster consumes the result by digest, never `:main`.

Renovate is what moves the pin, in two hops. In `datahub-local-ai`, the built-in `dockerfile`
manager is disabled, so a `customManager` reads the `# renovate:` line above each tool `ARG` —
helm, helmfile, kubectl, kustomize, yq, gh, uv and the OpenSpec CLI — and merges the bump, which
publishes a new digest. The OpenCode release is the exception: GitHub's `latest` release still
points at v1, so `github-releases` cannot see the v2 line; `publish-images.yaml` resolves the newest
v2 tag and passes it as `OPENCODE_VERSION`, and no Renovate rule watches it. In this repository the
existing jsonata manager for `container_image_version` then raises the digest PR for
`…-opencode-adapter: main@sha256:…` — no new core configuration is needed for the image, as long as
the value keeps the `tag@sha256:…` shape. The base tag `node:22-bookworm-slim` is deliberately left
to the weekly adapter rebuild, not to Renovate.

It lives under `agents/adapters/` only because `publish-images.yaml` discovers every
`agents/adapters/<dir>/Dockerfile`. It is **not** a Sympozium harness adapter: it implements no
harness contract and declares no capabilities, and its README says so.

The agent's own files ship in the image, not in a ConfigMap: `opencode.json` at
`/etc/opencode/opencode.json` (v2's machine-wide directory), `AGENTS.md` at
`/opt/opencode/AGENTS.md` and named by `instructions`, the skills under `/opt/opencode/skills`,
`gitconfig` at `/etc/gitconfig`, and under `/usr/local/bin` the credential helper, the `gh` wrapper
that asks the same helper, the minter, and the `github-proxy`/`mcp-forward` scripts. `/opt/data` is
a volume, so anything baked under `$HOME` would be hidden; `/etc` and `/usr/local` are not. The
Firecrawl endpoint, the Kubernetes bridge, the default model and the reviewer model are read from
the environment through v2's `{env:…}` substitution, so the image never hardcodes a Service address
or a model choice.

Consequences: no `apk`, no `--initdb`, no root process, no runtime download of `git` or a toolchain,
and a read-only root filesystem that still lets the agent clone, render and test.

### 6 — Firecrawl is the self-hosted bridge, not a second deployment

Firecrawl is one of OpenCode's five native websearch providers (Exa, Firecrawl, Parallel, Tavily,
TinyFish), but the requirement here is the MCP server, not the provider: it gives `search`,
`scrape` and `map` tools that the native `websearch` does not. The MCP server is the one deployed by
`add-firecrawl-mcp` in `automation`; this release only registers it as a remote MCP at
`http://{{ .Values.release_name }}-automation-mcp-firecrawl-http.automation.svc.cluster.local:8080/mcp`
(the HTTP transport Service, not the MCPServer name).

There is no Firecrawl Deployment, no `firecrawl-token` Secret and no `api.firecrawl.dev` egress here.
That change runs the server keyless against the self-hosted API in `data`.

A second remote MCP server, `k8s`, points at the read-only Kubernetes bridge
(`OPENCODE_K8S_MCP_URL`). The server has no route to the Kubernetes API and no client credential,
so the bridge is how the agent sees the workloads it changed; its egress rule is the same
`mcpserver` port 8080 as Firecrawl's.

The native `websearch` and `webfetch` tools stay disabled. `webfetch` would fetch any URL with no
reviewed surface; the bridge exposes only `fc_firecrawl_scrape`, `fc_firecrawl_search` and
`fc_firecrawl_map`. Crawl, agent, monitor, interact, parse and feedback are not registered at all,
so the OpenCode permission list does not need to deny what is absent.

### 7 — Internet access goes through the egress proxy, never direct

The CNI cannot allow `github.com` and deny the rest on 443, and the agent has `shell`: `curl` and
`git` are in the image, so it can fetch any URL even with `webfetch` denied. Tool permissions shape
quality and context, not reachability.

`add-egress-proxy` deploys Squid in `security` with a domain allowlist, and this change is its
consumer:

- The server Pod sets `HTTPS_PROXY`/`HTTP_PROXY` to the proxy Service on 3128 and a `NO_PROXY` for
  `data.svc`, `automation.svc` and the cluster suffix.
- Its egress policy keeps DNS, LiteLLM on 4000, the MCP bridges on 8080 and the proxy on 3128,
  and drops the public 443 rule. A binary that ignores the variables fails instead of leaking.
- The allowlist gains a `helm` group: `.github.io` (every GitHub Pages chart repo this cluster
  uses), `airflow.apache.org`, `downloads.apache.org`, `helm.openwebui.com`,
  `charts.redpanda.com`, `deploy.sympozium.ai`, `robusta-charts.storage.googleapis.com`, and the
  OCI registries `ghcr.io`, `8gears.container-registry.com` and `oci.trueforge.org`. Two chart
  sources redirect off their GitHub Pages host: `cloudnative-pg.github.io` lands on
  `cloudnative-pg.io` (HTTPS, allowlisted), and `stirling-tools.github.io` lands on
  `docs.stirlingpdf.com` over plain HTTP, which the proxy denies — so `values/_version.yaml`
  points the Stirling chart at the HTTPS host directly, under a new repository alias because Helm
  refuses to re-add an existing alias at a different URL, and the proxy keeps port 80 denied.
  Without these, `helmfile template` cannot resolve a chart and the toolchain is decoration.
- PyPI and GitHub cover `uv sync` and `git`. Browsing is the Firecrawl bridge's job, not the
  proxy's.

The remaining residual is granularity, not reachability: an allowlisted domain is allowlisted for
every path, and content inspection would need TLS interception.

A chart repository that redirects is a second residual: the target host has to be allowlisted too,
and a redirect to plain HTTP cannot be made to work while port 80 stays denied. The two sources
that do this are fixed at the source (one allowlisted target, one HTTPS repository URL) rather than
by opening port 80.

### 8 — Model path is a declared provider

LiteLLM is configured as an ordinary provider in the baked config — `providers.litellm` with the
`@opencode/ai/providers/openai-compatible` package, `{env:LITELLM_BASE_URL}` and `LITELLM_API_KEY`
from the environment, plus the models the agent uses. `enabled_providers: ["litellm"]` is exclusive, so `litellm/*` is
the only selectable path. That matters for more than the built-in free provider: a `GITHUB_TOKEN` in
the environment would otherwise offer `github-copilot/*` (28 models, measured in the live Pod) —
the token now lives in the sidecar, but the allowlist is still what keeps the agent on LiteLLM.

The default model and the reviewer's model are values, not image contents: `OPENCODE_MODEL`
(`litellm/opencode-go/deepseek-v4.1-flash`) writes the change, and `OPENCODE_REVIEW_MODEL`
(`litellm/opencode-go/glm-5.3-flash`) reviews it in the `reviewer` subagent, which cannot edit files
or ask questions. Changing either is a values edit and a rollout; both models are declared in the
baked config so a list-models check sees them.

That replaces the LiteLLM plugin the first draft used. The plugin discovered the proxy's catalogue,
but it installed a package into `$HOME/.cache/opencode/npm/<spec>` on first server start, and a cold
`opencode models` raced that activation and exited with `Location plugins did not finish activating`.
An init container could only hide that race. A declared provider removes the install, the cache, the
init container and the race; the cost is that a new LiteLLM model needs a config edit and an image
rebuild, which is acceptable for one pinned default model.

Readiness asks the running server for `/api/model` and requires a `litellm` provider. The CLI is not
used: it starts its own private server.

### 9 — Permissions

v2 uses an ordered `permissions` ruleset of `{action, resource, effect}`, in the image so a policy
change is reviewed and shipped like the code it governs. Ordered (last match wins):

```
deny   webfetch, websearch
deny   read *.env, *.env.*, *.pem, id_rsa*, id_ed25519*, .netrc, .kube/**
deny   bash curl *, wget *, git push --force*, git push -f*
deny   external_directory *
allow  external_directory /workspace/*, /tmp/*, /opt/data/.config/opencode/*
allow  question
allow  fc_firecrawl_scrape, fc_firecrawl_search, fc_firecrawl_map, k8s_*
```

The secret-file denies matter because `/workspace` holds checkouts of repositories that may carry a
`.env`; the `bash` denies close the obvious network and history-rewriting paths, though the egress
proxy, not the permission list, is what makes an ignored variable fail. `question` is allowed
because it is surfaced, not stalled. The directory allows are what make `git`, `/tmp`, and
`AGENTS.md` work; a blanket deny breaks the agent. There is no git install under `/opt/data` any
more, so no path for it is allowed.

### 10 — Isolation and state

The server Pod runs under `gvisor` on `datahublocal-amd-1`, because `datahublocal-amd-2` blacklists
the TSC and Node's monotonic clock check fails inside the sandbox (53 of 800 starts measured during
the Hermes investigation). Every container is non-root, read-only root, no capabilities, no
service-account token. `/opt/data` (home, OpenCode state) and `/workspace` (repos) are separate
Longhorn RWO volumes; one replica, `Recreate`. The image makes every tool available under `/usr`
and `/usr/local`, so nothing needs to be installed into the state volume and there is no root
process at all.

### 11 — ACP stays out

Neither Hermes nor Sympozium speaks ACP as a client, and OpenCode's ACP is stdio. It would add a hop
with no consumer. The HTTP API plus the shim is the contract.
