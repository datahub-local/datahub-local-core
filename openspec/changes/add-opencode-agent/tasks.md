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
  - OpenCode: `ARG OPENCODE_VERSION`, resolved by `publish-images.yaml` from the newest v2 tag —
    GitHub's `latest` release still points at v1, so `github-releases` cannot see the v2 line; no
    Renovate rule watches it.
  - Toolchain: a `# renovate: datasource=github-releases depName=<owner>/<repo>` line above each
    `ARG`, and one `customManager` whose regex matches the annotation plus the next `ARG`, so helm,
    helmfile, kubectl, kustomize, yq, gh, uv and the OpenSpec CLI need no per-tool block.
  - The weekly adapter rebuild in `publish-images.yaml` carries base CVE fixes, and merging a
    Renovate bump publishes a new digest. Do not pin a release-asset sha256 that Renovate cannot
    update, or every bump will fail the build until it is edited by hand.
  - Add a `README.md` stating upstream revision, the enabled toolchain, and that this is **not** a
    Sympozium harness adapter — no contract, no capabilities.
- [x] 1.4 Publish `ghcr.io/datahub-local/datahub-local-ai-opencode-adapter` multi-arch
  (`linux/amd64`, `linux/arm64`); the release pins
  `main@sha256:27bc702a431342dcd298ae49896db1fe217cabaf8b5a931655c41f572378fc61`. No workflow edit is needed: `publish-images.yaml` discovers
  `agents/adapters/*/Dockerfile` and names the image from the directory.
- [x] 1.5 Add to `values/_version.yaml`: the adapter image
  (`ghcr.io/datahub-local/datahub-local-ai-opencode-adapter: main@sha256:<digest>` from 1.4),
  `nginxinc/nginx-unprivileged` (tag), and the shim image (digest). Keep the `tag@sha256:…` shape: the existing `container_image_version` jsonata
  manager then proposes the digest bump. The adapter is pinned to the published index digest and the
  shim to `main@sha256:72a270071fc62e2c6088c710e61648d306775f65797df738688756941798f932`. No upstream
  OpenCode image and no Alpine git version. Firecrawl is pinned by `add-firecrawl-mcp`.
- [x] 1.6 Add the three workloads to `releases/automation/` on `bjw-s-labs/app-template`:
  `opencode-server`, `opencode-web`, `opencode-mcp`.
- [x] 1.7 Server: one replica, `Recreate`, `runtimeClassName: gvisor`, nodeSelector
  `datahublocal-amd-1` + `kubernetes.io/arch: amd64`, uid/gid/fsGroup 1000, read-only root,
  capabilities dropped, no service-account token, `HOME=/opt/data`, `/opt/data` + `/workspace`
  PVCs, `/tmp` memory emptyDir of at least 1Gi. `command: ["opencode"]`, `args: ["serve", …]`.
- [x] 1.8 Render with `helmfile template` and confirm: server, web proxy, shim, three Services, no
  init container, no ingress to the server, no root container.
- [x] 1.9 Prove the Renovate path before merging: run
  `renovate --platform=local --dry-run=full --repository-cache=reset --onboarding=false` in
  `datahub-local-ai` and confirm it lists each tool ARG. Extraction verified with the Renovate
  container: it reported `helm/helm`, `helmfile/helmfile`, `astral-sh/uv` and the two helmfile
  deps. The OpenCode release is not Renovate-managed, and without a GitHub token Renovate proposes
  no updates, so the digest-PR half still needs a token.

## 2. Agent files and model provider

- [x] 2.1 Bake `opencode.json` at `/etc/opencode/opencode.json` in the adapter image: v2 shapes —
  `model: {env:OPENCODE_MODEL}` (`litellm/opencode-go/deepseek-v4.1-flash`), a `reviewer` subagent on
  `{env:OPENCODE_REVIEW_MODEL}` (`litellm/opencode-go/glm-5.3-flash`) that cannot edit or ask,
  `providers.litellm` (`openai-compatible`, `{env:LITELLM_BASE_URL}`), `enabled_providers:
  ["litellm"]`, `mcp.servers.fc` (`codemode: false`, `{env:OPENCODE_FIRECRAWL_MCP_URL}`),
  `mcp.servers.k8s` (`{env:OPENCODE_K8S_MCP_URL}`), `skills.paths`, `permissions` from design §9,
  `update: "disable"`, and `instructions: ["/opt/opencode/AGENTS.md"]`.
- [x] 2.2 Bake `AGENTS.md` at `/opt/opencode/AGENTS.md` and the agent skills under
  `/opt/opencode/skills`: work inside `/workspace`, report changed files, push only to a branch it
  created.
- [x] 2.3 Bake `gitconfig` at `/etc/gitconfig` (bot identity plus `credential.helper =
  /usr/local/bin/git-credential-opencode`), the helper at `/usr/local/bin/git-credential-opencode`
  (0755) and the `gh` wrapper at `/usr/local/bin/gh` (0755). Git reads the system file and resolves
  the absolute helper; the wrapper asks the same helper, so a pull request carries the App identity.
- [x] 2.4 Bake the minter at `/usr/local/bin/opencode-minter.mjs`; it is the sidecar's entrypoint
  (task 3.2).
- [x] 2.5 Ship no ConfigMap for these files and mount none under `/opt/data`: the state volume would
  hide them, and the image is the versioned source.
- [x] 2.6 Ship no init container: a declared provider has no package to install, so there is no
  cache to pre-warm and no activation race. Verified by running the image's `opencode models
  --standalone` against LiteLLM: only `litellm/*` is listed.
- [x] 2.7 Verify as uid 1000 under a read-only root filesystem: `opencode`, `openspec`, `git`,
  `helm`, `helmfile`, `kubectl`, `kustomize`, `yq`, `jq`, `gh`, `node`, `npm`, `uv`, `python3` and
  `curl` all run; `/` refuses a write while `/tmp`, `/opt/data` and `/workspace` accept one.
  Verified in the live Pod 2026-11-02.

## 3. GitHub credentials

- [x] 3.1 Use the coder App's derived Secret `automation/github-app-coder`
  (`GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY`), created by
  `agent-github-identity`. `opencode-github` and `github-root` are no longer referenced.
- [x] 3.2 Run `minter` as a sidecar from that Secret; `git-credential-opencode` and the `gh`
  wrapper ask its loopback `/token`. The server carries no `GITHUB_TOKEN`, and the git identity is
  `datahub-local-coder[bot]`. SSH deploy keys do not work here: one key cannot be attached to the
  three repositories.
- [x] 3.3 Verify in-cluster: the checkout under `/workspace` fetches and `git push --dry-run`
  authenticates, `gh api installation/repositories` lists 19 repositories, the bot identity is in
  `/etc/gitconfig`, and `github-root` is absent from both containers. Verified 2026-11-02; a real
  push and pull request is still unexercised (agent-github-identity 1.8).
- [x] 3.4 (Superseded) The App installation tokens replaced the token path: `agent-github-identity`
  owns the App, the roots and the Hermes proxy. datahub-local-core#253 tracked the interim token,
  not this release.

## 4. Web proxy

- [x] 4.1 Add the nginx Deployment + Service: `proxy_pass http://opencode-server:4096`,
  `proxy_buffering off`, upgrade headers, and a read timeout longer than a session.
- [x] 4.2 Add an `IngressRoute` at `automation-opencode.<gateway_hostname>` to the proxy, with
  `security/oauth2-proxy-auth` and the `/oauth2/` route, plus a homepage entry.
- [x] 4.3 Add the Traefik `headers` middleware injecting `Authorization: Basic …`.
- [ ] 4.4 Verify: anonymous redirects to dex; after login the UI loads with no second prompt;
  SSE updates stream; direct access to the server's 4096 is denied. Anonymous access returns the
  oauth2-proxy sign-in page (2026-11-02); the signed-in and SSE halves are unverified.

## 5. MCP shim

- [x] 5.1 Add `servers/opencode/` to `datahub-local-ai-mcp` (seven tools, `respx` tests) and publish
  `ghcr.io/datahub-local/mcp-opencode` by digest (one replica, no volume), and add `opencode` to
  `publish.yaml`'s hardcoded server list, dispatch options, weekly cron and prune matrix. The code is
  done — including `get_diff`, `list_sessions` and `get_transcript`, added after reviewing the
  upstream `opencode-mcp` tool set (v1-only, so not adopted). The release pins
  `main@sha256:72a270071fc62e2c6088c710e61648d306775f65797df738688756941798f932`.
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
  the bridge containers. The key is absent from both (2026-11-02); search and scrape are
  unexercised.
- [x] 6.4 Confirm this release renders no Firecrawl Deployment, no `firecrawl-token` Secret and no
  `api.firecrawl.dev` egress. Verified 2026-11-02.
- [x] 6.5 Register the read-only Kubernetes bridge as `mcp.servers.k8s` at
  `{env:OPENCODE_K8S_MCP_URL}` and allow `k8s_*` in the permission ruleset; the server keeps no
  API route and no credential.

## 7. Network

- [x] 7.1 Server policy: DNS, `data/litellm` 4000, the automation MCP bridges (Firecrawl and
  Kubernetes) on 8080, `security` egress proxy 3128; ingress on
  4096 only from the proxy and shim Pods. No public 443.
- [x] 7.2 Proxy policy: DNS + server 4096 only.
- [x] 7.3 Shim policy: DNS + server 4096 only.
- [x] 7.4 Server env: `HTTP_PROXY`/`HTTPS_PROXY` at
  `http://{{ .Values.release_name }}-security-egress-proxy.security.svc.cluster.local:3128` and
  `NO_PROXY` for `data.svc`, `automation.svc` and `svc.cluster.local`.
- [x] 7.5 Verify each workload is denied outside its list, including the Kubernetes API, and that a
  direct `https://pypi.org` from the server fails while the proxied one succeeds. Verified
  2026-11-02: direct 000, proxied 200, `kubernetes.default.svc` 000.

## 8. Registration

- [x] 8.1 Add a `sympozium.ai/v1alpha1 MCPServer` for the shim with `transportType: http`,
  `spec.url` at `/mcp`, `sympozium.ai/catalog: "true"`, and `app.kubernetes.io/name: mcpserver` on
  the Service.
- [x] 8.2 Add `mcp_servers.opencode` to `releases/automation/values/hermes.yaml.gotmpl` with
  `timeout: 900`.
- [x] 8.3 Deploy Hermes once with `bootstrap.overwrite=true`, then return it to `false`. The live
  config carries `mcp_servers.opencode`; a fresh volume seeds it from values.
- [x] 8.4 From Hermes: `hermes mcp test opencode` lists seven tools; a Slack request starts a task,
  returns `running`, and a later status message returns the result. The seven tools are verified;
  the shim's `run_task` end to end is task 10.1.
- [ ] 8.5 Confirm a Sympozium persona can list the seven tools.

## 9. Isolation and state

- [x] 9.1 Confirm the server Pod is under gVisor on `datahublocal-amd-1`, every container is
  non-root, and OpenCode's state survives a restart. Verified 2026-11-02: gVisor, amd-1, uid 1000,
  and `/opt/data/.local/share/opencode` predates the current Pod.
- [x] 9.2 Confirm no service-account token is mounted and only `/opt/data`, `/workspace`, `/tmp` are
  writable. Verified: no token directory, root filesystem read-only, the three mounts accept writes.
- [x] 9.3 Confirm a rollout terminates the old server Pod before the new one mounts either PVC.
  `strategy: Recreate` on a single replica; two RWO claims.
- [x] 9.4 Confirm no container runs `apk`, `apt`, `--initdb` or a runtime installer, and that no
  process runs as uid 0. Verified: neither binary exists and every `/proc/*/status` reports uid
  1000.

## 10. Verification

- [x] 10.1 A task edits a file, runs a test, returns the final text and the changed file. Verified
  2026-11-02 through the shim: `run_task` created `.mcp-probe.txt` and reported
  `A .mcp-probe.txt (+1 -0)`; `get_diff` returned the patch and `get_transcript` the messages.
- [ ] 10.2 `.env` reads and direct `webfetch` are denied; `fc_firecrawl_search` works; `git` works.
- [ ] 10.3 A second task returns busy; `abort_session` stops the first; `get_session` reports state.
- [ ] 10.4 Record cold-start (provider load → ready) and warm-start. Cold start on 2026-11-02:
  69 seconds from Pod start to Ready. Warm start still unrecorded.
- [ ] 10.5 Clone `datahub-local-core` and run `helmfile template` from the server workspace; clone
  `datahub-local-ai` and run `uv sync --extra dev`. Both succeed through the proxy with no tool
  installed at runtime. `uv sync` succeeds (Python 3.13.18); `helmfile template` failed on
  2026-11-02 because two chart repositories redirect off the allowlist (task 11.5).

## 11. Egress proxy consumer (moved from `add-egress-proxy`)

- [x] 11.1 On the server container set `HTTPS_PROXY`/`HTTP_PROXY` to
  `http://{{ .Values.release_name }}-security-egress-proxy.security.svc.cluster.local:3128` and
  `NO_PROXY` to the cluster domains.
- [x] 11.2 Replace the server's public 443 egress with the proxy rule on 3128 and update the
  "no egress proxy" residual in the design and spec.
- [x] 11.3 Add the `helm` allowlist group to `releases/security/values/default.yaml.gotmpl`:
  `.github.io`, `cloudnative-pg.io`, `docs.stirlingpdf.com`, `airflow.apache.org`,
  `archive.apache.org`, `downloads.apache.org`, `helm.openwebui.com`, `charts.redpanda.com`,
  `deploy.sympozium.ai`, `robusta-charts.storage.googleapis.com`, `ghcr.io`,
  `.r2.cloudflarestorage.com`, `.quay.io`, `8gears.container-registry.com`, `oci.trueforge.org`.
  The CDN hosts are what the OCI registries redirect their signed blob URLs to, and
  `archive.apache.org` is where the Airflow index sends its tarball; without them `helm pull`
  fails after the index resolves.
- [x] 11.5 Repoint the Stirling chart at `https://docs.stirlingpdf.com/Stirling-PDF-chart` in
  `values/_version.yaml`, under a new repository alias: Helm refuses to re-add an existing alias at
  a different URL, and a warm ArgoCD helmfile cache still holds the old one. The GitHub Pages URL
  redirects to that host over plain HTTP, and the proxy keeps port 80 denied. Both redirecting
  chart sources were found by rendering through the live proxy; `cloudnative-pg.github.io` lands on
  `cloudnative-pg.io`.
- [ ] 11.4 Verify `helmfile template` in a cloned `datahub-local-core` resolves every chart through
  the proxy, and that an unlisted chart repository is refused. Blocked until 11.3/11.5 are deployed;
  the 2026-11-02 run failed at cloudnative-pg and Stirling.
