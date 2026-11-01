# Tasks

## 1. Image and pins

- [x] 1.1 Add `agents/adapters/opencode/` to `datahub-local-ai`: a `Dockerfile` on
  `node:22-bookworm-slim` that copies the pinned upstream OpenCode Linux release binary for the
  target architecture, keeps `ENTRYPOINT ["opencode"]`, and installs the toolchain from pinned
  release tarballs — `git`, `bash`, `curl`, `openssh-client`, `ca-certificates`, `jq`, `yq`,
  `kubectl`, `helm`, `helmfile`, `kustomize`, `gh`, `node`/`npm`, `python3` + `venv`/`pip`, and `uv`.
  It also carries the agent's own files: `opencode.json` (v2 config at `/etc/opencode`), `AGENTS.md`,
  `gitconfig` at `/etc/gitconfig`, the credential helper and the minter.
- [x] 1.2 Add the managed Python 3.13: `uv python install 3.13` into `/opt/uv/python` and set
  `UV_PYTHON_INSTALL_DIR`; bookworm's system Python stays 3.11. Assert every tool in the build with
  `git --version`, `helm version`, `helmfile version`, `kubectl version --client`, `kustomize
  version`, `yq --version`, `gh --version`, `node --version`, `npm --version`, `uv --version`,
  `python3 --version`.
- [x] 1.3 Pin every tool as a Dockerfile `ARG` and make Renovate own the bumps:
  - OpenCode: `ARG OPENCODE_VERSION=<version>` plus a `customManager` with
    `datasourceTemplate: github-releases`, `depNameTemplate: anomalyco/opencode` (`sst/opencode`
    redirects there; the tags did not move), and `extractVersionTemplate: ^(?:kustomize/)?v?(?<version>.*)$`.
  - Toolchain: a `# renovate: datasource=github-releases depName=<owner>/<repo>` line above each
    `ARG`, and one `customManager` whose regex matches the annotation plus the next `ARG`, so helm,
    helmfile, kubectl, kustomize, yq, gh and uv need no per-tool block.
  - The weekly adapter rebuild in `publish-images.yaml` carries base CVE fixes, and merging a
    Renovate bump publishes a new digest. Do not pin a release-asset sha256 that Renovate cannot
    update, or every bump will fail the build until it is edited by hand.
  - Add a `README.md` stating upstream revision, the enabled toolchain, and that this is **not** a
    Sympozium harness adapter — no contract, no capabilities.
- [x] 1.4 Publish `ghcr.io/datahub-local/datahub-local-ai-opencode-adapter` multi-arch
  (`linux/amd64`, `linux/arm64`); published index digest
  `sha256:6cd7f90206b910c544313f21223d4f1828468f6f35f304acd92aeb1554ade967`. No workflow edit is needed: `publish-images.yaml` discovers
  `agents/adapters/*/Dockerfile` and names the image from the directory.
- [x] 1.5 Add to `values/_version.yaml`: the adapter image
  (`ghcr.io/datahub-local/datahub-local-ai-opencode-adapter: main@sha256:<digest>` from 1.4),
  `nginxinc/nginx-unprivileged` (tag), and the shim image (digest). Keep the `tag@sha256:…` shape: the existing `container_image_version` jsonata
  manager then proposes the digest bump. The adapter is pinned to the published index digest; the
  shim is still a zero placeholder until it is published. No upstream OpenCode image and no Alpine
  git version. Firecrawl is pinned by `add-firecrawl-mcp`.
- [x] 1.6 Add the three workloads to `releases/automation/` on `bjw-s-labs/app-template`:
  `opencode-server`, `opencode-web`, `opencode-mcp`.
- [x] 1.7 Server: one replica, `Recreate`, `runtimeClassName: gvisor`, nodeSelector
  `datahublocal-amd-1` + `kubernetes.io/arch: amd64`, uid/gid/fsGroup 1000, read-only root,
  capabilities dropped, no service-account token, `HOME=/opt/data`, `/opt/data` + `/workspace`
  PVCs, `/tmp` memory emptyDir of at least 1Gi. `command: ["opencode"]`, `args: ["serve", …]`.
- [x] 1.8 Render with `helmfile template` and confirm: server, web proxy, shim, three Services, no
  init container, no ingress to the server, no root container.
- [ ] 1.9 Prove the Renovate path before merging: run
  `renovate --platform=local --dry-run=full --repository-cache=reset --onboarding=false` in
  `datahub-local-ai` and confirm it lists `anomalyco/opencode` and each tool ARG; after the first
  publish, confirm core's Dependency Dashboard proposes a digest update for the adapter.
  Extraction verified with the Renovate container: it reported `anomalyco/opencode`, `helm/helm`,
  `helmfile/helmfile`, `astral-sh/uv` and the two helmfile deps. Without a GitHub token it proposes
  no updates, so the digest-PR half still needs a token.

## 2. Agent files and model provider

- [x] 2.1 Bake `opencode.json` at `/etc/opencode/opencode.json` in the adapter image: v2 shapes —
  `model: litellm/opencode-go/deepseek-v4.1-flash`, `providers.litellm` (`openai-compatible`,
  `{env:LITELLM_BASE_URL}`), `enabled_providers: ["litellm"]`, `mcp.servers.fc` with
  `codemode: false` and `{env:OPENCODE_FIRECRAWL_MCP_URL}`, `permissions` from design §9,
  `update: "disable"`, and `instructions: ["/opt/opencode/AGENTS.md"]`.
- [x] 2.2 Bake `AGENTS.md` at `/opt/opencode/AGENTS.md`: work inside `/workspace`, report changed
  files, push only to a branch it created.
- [x] 2.3 Bake `gitconfig` at `/etc/gitconfig` (identity plus `credential.helper =
  git-credential-opencode`) and the helper at `/usr/local/bin/git-credential-opencode` (0755). Git
  reads the system file and resolves the helper through PATH. The helper answers from
  `GITHUB_TOKEN`, so it works before the App exists.
- [x] 2.4 Bake the minter at `/usr/local/bin/opencode-minter.mjs`, unused until the deferred App
  exists (task 3.1).
- [x] 2.5 Ship no ConfigMap for these files and mount none under `/opt/data`: the state volume would
  hide them, and the image is the versioned source.
- [x] 2.6 Ship no init container: a declared provider has no package to install, so there is no
  cache to pre-warm and no activation race. Verified by running the image's `opencode models
  --standalone` against LiteLLM: only `litellm/*` is listed.
- [ ] 2.7 Verify as uid 1000 under a read-only root filesystem: `git`, `helm`, `helmfile`,
  `kubectl`, `kustomize`, `yq`, `jq`, `gh`, `node`, `npm`, `uv`, `python3` and `curl` all run, and
  `git clone` over HTTPS works through the minter helper.

## 3. GitHub credentials

- [x] 3.1 Add an `automation/opencode-github` ExternalSecret with the key `GITHUB_TOKEN`, derived
  from `github-root` — no OpenCode-specific root for now. Only the ExternalSecret reads the root;
  no container does. Swapping the source for a fine-grained token or an App changes this one entry
  (#253).
- [x] 3.2 The server takes `GITHUB_TOKEN` from that Secret. `git-credential-opencode` answers from the
  variable and falls back to the minter endpoint; no credential file is written. SSH deploy keys do
  not work here: one key cannot be attached to the three repositories.
- [ ] 3.3 Verify in-cluster: clone a private repository, push a branch; confirm `github-root` is
  absent from the Pod and that revoking this token affects neither Airflow nor the GitHub MCP
  server.
- [ ] 3.4 (Future) Replace the token with App installation tokens: create and install the App, add
  the `github-app` Secret and the minter sidecar, then drop `GITHUB_TOKEN`. Tracked in
  datahub-local-core#253.

## 4. Web proxy

- [x] 4.1 Add the nginx Deployment + Service: `proxy_pass http://opencode-server:4096`,
  `proxy_buffering off`, upgrade headers, and a read timeout longer than a session.
- [x] 4.2 Add an `IngressRoute` at `automation-opencode.<gateway_hostname>` to the proxy, with
  `security/oauth2-proxy-auth` and the `/oauth2/` route, plus a homepage entry.
- [x] 4.3 Add the Traefik `headers` middleware injecting `Authorization: Basic …`.
- [ ] 4.4 Verify: anonymous redirects to dex; after login the UI loads with no second prompt;
  SSE updates stream; direct access to the server's 4096 is denied.

## 5. MCP shim

- [x] 5.1 Add `servers/opencode/` to `datahub-local-ai-mcp` (seven tools, `respx` tests) and publish
  `ghcr.io/datahub-local/mcp-opencode` by digest (one replica, no volume), and add `opencode` to
  `publish.yaml`'s hardcoded server list, dispatch options, weekly cron and prune matrix. The code is
  done — including `get_diff`, `list_sessions` and `get_transcript`, added after reviewing the
  upstream `opencode-mcp` tool set (v1-only, so not adopted). Published as
  `sha256:e423ffd2b9b7db6932d28eacec1f14831a23ca0f84dc29a53af43ebd8f16a05c`.
- [x] 5.2 Implement `run_task`, `get_session`, `respond`, `abort_session` against the server API with
  Basic auth: `POST /api/session`, `POST /api/session/:id/prompt`, `GET /api/session/:id`,
  `POST /api/experimental/session/:id/wait`, `GET /api/session/:id/diff`,
  `GET/POST /api/session/:id/form*`, `GET/POST /api/session/:id/permission*`,
  `POST /api/session/:id/interrupt`, `GET /api/session/active`.
- [x] 5.3 `run_task` waits at most `wait_seconds` (default 120, max 300), returns
  `running|idle|needs_input|error`, and never ends the session on the timeout.
- [x] 5.4 Busy is read from `GET /api/session/active`, not memory, so a restart cannot start a
  second writer.
- [x] 5.5 Bounded output through the runner's budget clamp (truncation marker); `directory` is
  workspace-relative and rejected when absolute or escaping the root.
- [x] 5.6 Tests: bounded wait, busy, `needs_input` + `respond`, error, truncation, directory escape.

## 6. Firecrawl

- [x] 6.1 Register the `add-firecrawl-mcp` bridge in `opencode.json` as a remote MCP server at
  `http://{{ .Values.release_name }}-automation-mcp-firecrawl-http.automation.svc.cluster.local:8080/mcp`
  (the HTTP transport Service; `…-mcp-firecrawl` is the MCPServer name, not a Service).
- [x] 6.2 Allow `fc_firecrawl_scrape`, `fc_firecrawl_search` and `fc_firecrawl_map` in the
  permission ruleset; the bridge registers nothing else.
- [ ] 6.3 Verify search and scrape work and `FIRECRAWL_API_KEY` is absent from both the server and
  the bridge containers.
- [ ] 6.4 Confirm this release renders no Firecrawl Deployment, no `firecrawl-token` Secret and no
  `api.firecrawl.dev` egress.

## 7. Network

- [x] 7.1 Server policy: DNS, `data/litellm` 4000, the automation Firecrawl bridge on 8080,
  `security` egress proxy 3128; ingress on
  4096 only from the proxy and shim Pods. No public 443.
- [x] 7.2 Proxy policy: DNS + server 4096 only.
- [x] 7.3 Shim policy: DNS + server 4096 only.
- [x] 7.4 Server env: `HTTP_PROXY`/`HTTPS_PROXY` at
  `http://{{ .Values.release_name }}-security-egress-proxy.security.svc.cluster.local:3128` and
  `NO_PROXY` for `data.svc`, `automation.svc` and `svc.cluster.local`.
- [ ] 7.5 Verify each workload is denied outside its list, including the Kubernetes API, and that a
  direct `https://pypi.org` from the server fails while the proxied one succeeds.

## 8. Registration

- [x] 8.1 Add a `sympozium.ai/v1alpha1 MCPServer` for the shim with `transportType: http`,
  `spec.url` at `/mcp`, `sympozium.ai/catalog: "true"`, and `app.kubernetes.io/name: mcpserver` on
  the Service.
- [x] 8.2 Add `mcp_servers.opencode` to `releases/automation/values/hermes.yaml.gotmpl` with
  `timeout: 900`.
- [ ] 8.3 Deploy Hermes once with `bootstrap.overwrite=true`, then return it to `false`.
- [ ] 8.4 From Hermes: `hermes mcp test opencode` lists seven tools; a Slack request starts a task,
  returns `running`, and a later status message returns the result.
- [ ] 8.5 Confirm a Sympozium persona can list the seven tools.

## 9. Isolation and state

- [ ] 9.1 Confirm the server Pod is under gVisor on `datahublocal-amd-1`, every container is
  non-root, and OpenCode's state survives a restart.
- [ ] 9.2 Confirm no service-account token is mounted and only `/opt/data`, `/workspace`, `/tmp` are
  writable.
- [ ] 9.3 Confirm a rollout terminates the old server Pod before the new one mounts either PVC.
- [ ] 9.4 Confirm no container runs `apk`, `apt`, `--initdb` or a runtime installer, and that no
  process runs as uid 0.

## 10. Verification

- [ ] 10.1 A task edits a file, runs a test, returns the final text and the changed file.
- [ ] 10.2 `.env` reads and direct `webfetch` are denied; `fc_firecrawl_search` works; `git` works.
- [ ] 10.3 A second task returns busy; `abort_session` stops the first; `get_session` reports state.
- [ ] 10.4 Record cold-start (provider load → ready) and warm-start.
- [ ] 10.5 Clone `datahub-local-core` and run `helmfile template` from the server workspace; clone
  `datahub-local-ai` and run `uv sync --extra dev`. Both succeed through the proxy with no tool
  installed at runtime.

## 11. Egress proxy consumer (moved from `add-egress-proxy`)

- [x] 11.1 On the server container set `HTTPS_PROXY`/`HTTP_PROXY` to
  `http://{{ .Values.release_name }}-security-egress-proxy.security.svc.cluster.local:3128` and
  `NO_PROXY` to the cluster domains.
- [x] 11.2 Replace the server's public 443 egress with the proxy rule on 3128 and update the
  "no egress proxy" residual in the design and spec.
- [x] 11.3 Add the `helm` allowlist group to `releases/security/values/default.yaml.gotmpl`:
  `.github.io`, `airflow.apache.org`, `downloads.apache.org`, `helm.openwebui.com`,
  `charts.redpanda.com`, `deploy.sympozium.ai`, `robusta-charts.storage.googleapis.com`,
  `ghcr.io`, `8gears.container-registry.com`, `oci.trueforge.org`.
- [ ] 11.4 Verify `helmfile template` in a cloned `datahub-local-core` resolves every chart through
  the proxy, and that an unlisted chart repository is refused.
