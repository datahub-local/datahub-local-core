# Design

## Context

One owner, one long-lived coding agent, reachable from a browser and from Hermes, with GitHub
credentials and a search tool. The cluster already has Hermes (chat), Sympozium (runs), Traefik,
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
- `respond(session_id, form_id | request_id, answer)`;
- `abort_session(session_id)`.

It holds no state. "One active session" is read from `GET /api/session/active`, not from memory, so
a shim restart cannot start a second writer. `run_task` waits at most 300 seconds and returns
`running|idle|needs_input|error`; the session itself is unbounded and can live for days.

`question` is allowed in OpenCode so the agent can ask the owner; the shim surfaces it as
`needs_input` and `respond` answers the form or permission. Every other `ask` is denied, because
nobody is watching a prompt.

### 4 — GitHub credentials are a minter sidecar, not a PAT

The server runs for days and its shell is the agent. A PAT in its environment is a write credential
the agent can read and, with 443 open, send anywhere. So the App key lives in a sidecar:

- The minter signs a ≤10-minute JWT and exchanges it for an installation token valid ≤1h.
- It serves a loopback endpoint that returns the cached token while >10 minutes remain, otherwise
  mints.
- `git-credential-opencode` (a ConfigMap shell script using `curl`, which the image now carries)
  asks that endpoint whenever git runs.

Nothing is written to disk, so a session that runs for a week still works: the next `git` call gets
a token minted at that moment. The server container never sees the App key. A stolen token dies
within the hour.

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
  `python3` with `venv` and `pip`, and `uv`. `uv` also carries a managed Python 3.13 under
  `/opt/uv/python` (`UV_PYTHON_INSTALL_DIR`), because `datahub-local-ai-mcp` requires 3.13 while
  bookworm ships 3.11.
- `ansible`, `dbt`, `dlt` and every other project dependency are **not** in the image. They are
  resolved by `uv sync` from the checkout's lockfile, which is the only version that matches the
  repository being edited.
- Multi-arch like every image that repository publishes: `linux/amd64` and `linux/arm64`.
- Every tool version is an `ARG` in the Dockerfile and tracked by a Renovate `customManager` in
  `datahub-local-ai/renovate.json`; the weekly adapter rebuild carries base-image CVE fixes. The
  cluster consumes the result by digest, never `:main`.

Renovate is what moves the pin, in two hops. In `datahub-local-ai`, the built-in `dockerfile`
manager is disabled, so a `customManager` reads `ARG OPENCODE_VERSION` with
`datasource=github-releases` and `depName=sst/opencode` (the release tags are `v1.19.5`; the regex
captures `1.19.5` and `extractVersion` strips the prefix). A second annotated pattern extracts every
tool `ARG` from a `# renovate: datasource=… depName=…` line, so one manager covers helm, helmfile,
kubectl, kustomize, yq, gh and uv. Merging the bump publishes a new digest. In this repository the
existing jsonata manager for `container_image_version` then raises the digest PR for
`…-opencode-adapter: main@sha256:…` — no new core configuration is needed for the image, as long as
the value keeps the `tag@sha256:…` shape. The base tag `node:22-bookworm-slim` is deliberately left
to the weekly adapter rebuild, not to Renovate.

It lives under `agents/adapters/` only because `publish-images.yaml` discovers every
`agents/adapters/<dir>/Dockerfile`. It is **not** a Sympozium harness adapter: it implements no
harness contract and declares no capabilities, and its README says so.

Consequences: no `apk`, no `--initdb`, no root process, no runtime download of `git` or a plugin
toolchain, and a read-only root filesystem that still lets the agent clone, render and test.

### 6 — Firecrawl is the self-hosted bridge, not a second deployment

Firecrawl is one of OpenCode's five native websearch providers (Exa, Firecrawl, Parallel, Tavily,
TinyFish), but the requirement here is the MCP server, not the provider: it gives `search`,
`scrape` and `map` tools that the native `websearch` does not. The MCP server is the one deployed by
`add-firecrawl-mcp` in `automation`; this release only registers it as a remote MCP at
`http://{{ .Values.release_name }}-automation-mcp-firecrawl.automation.svc.cluster.local:8080/mcp`.

There is no Firecrawl Deployment, no `firecrawl-token` Secret and no `api.firecrawl.dev` egress here.
That change runs the server keyless against the self-hosted API in `data`.

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
- Its egress policy keeps DNS, LiteLLM on 4000, the Firecrawl bridge on 8080 and the proxy on 3128,
  and drops the public 443 rule. A binary that ignores the variables fails instead of leaking.
- The allowlist gains a `helm` group: `.github.io` (every GitHub Pages chart repo this cluster
  uses), `airflow.apache.org`, `downloads.apache.org`, `helm.openwebui.com`,
  `charts.redpanda.com`, `deploy.sympozium.ai`, `robusta-charts.storage.googleapis.com`, and the OCI
  registries `ghcr.io`, `8gears.container-registry.com` and `oci.trueforge.org`. Without it
  `helmfile template` cannot resolve a chart and the toolchain is decoration.
- PyPI and GitHub cover `uv sync` and `git`; npm covers the LiteLLM plugin. Browsing is the
  Firecrawl bridge's job, not the proxy's.

The remaining residual is granularity, not reachability: an allowlisted domain is allowlisted for
every path, and content inspection would need TLS interception.

### 8 — Model path and plugin

The litellm plugin is installed at startup into `$HOME/.cache/opencode/npm/<spec>` and listed in
`opencode.json`. Measured: a cold `opencode models` once raced the install and failed with
`Location plugins did not finish activating`; a second run completed it and listed
`litellm/opencode-go/deepseek-v4.1-flash`. The init container removes the race by running before the
server; readiness additionally waits for a model.

The image ships `node` and `npm`, so the install no longer depends on what the upstream image
happens to carry, but the cache still lives on the state volume because `HOME` is `/opt/data`.

### 9 — Permissions

Ordered (last match wins):

```
deny   webfetch, websearch
deny   read *.env, *.env.*
deny   external_directory *
allow  external_directory /workspace/*, /tmp/*, /opt/data/.config/opencode/*
allow  read /opt/data/.config/opencode/*
allow  fc_firecrawl_scrape, fc_firecrawl_search, fc_firecrawl_map
```

`question` is allowed because it is surfaced, not stalled. The directory allows are what make
`git`, `/tmp`, and `AGENTS.md` work; a blanket deny breaks the agent. There is no git install under
`/opt/data` any more, so no path for it is allowed.

### 10 — Isolation and state

The server Pod runs under `gvisor` on `datahublocal-amd-1`, because `datahublocal-amd-2` blacklists
the TSC and Node's monotonic clock check fails inside the sandbox (53 of 800 starts measured during
the Hermes investigation). Every container is non-root, read-only root, no capabilities, no
service-account token. `/opt/data` (home, plugin cache) and `/workspace` (repos) are separate
Longhorn RWO volumes; one replica, `Recreate`. The image makes every tool available under `/usr`
and `/usr/local`, so nothing needs to be installed into the state volume and there is no root
process at all.

### 11 — ACP stays out

Neither Hermes nor Sympozium speaks ACP as a client, and OpenCode's ACP is stdio. It would add a hop
with no consumer. The HTTP API plus the shim is the contract.
