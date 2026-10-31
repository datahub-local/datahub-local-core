# Tasks

## 1. Image and pins

- [ ] 1.1 Add `agents/adapters/opencode/` to `datahub-local-ai`: a `Dockerfile` on
  `node:22-bookworm-slim` that copies the pinned upstream OpenCode Linux release binary for the
  target architecture, keeps `ENTRYPOINT ["opencode"]`, and installs the toolchain from pinned
  release tarballs — `git`, `bash`, `curl`, `openssh-client`, `ca-certificates`, `jq`, `yq`,
  `kubectl`, `helm`, `helmfile`, `kustomize`, `gh`, `node`/`npm`, `python3` + `venv`/`pip`, and `uv`.
- [ ] 1.2 Add the managed Python 3.13: `uv python install 3.13` into `/opt/uv/python` and set
  `UV_PYTHON_INSTALL_DIR`; bookworm's system Python stays 3.11. Assert every tool in the build with
  `git --version`, `helm version`, `helmfile version`, `kubectl version --client`, `kustomize
  version`, `yq --version`, `gh --version`, `node --version`, `npm --version`, `uv --version`,
  `python3 --version`.
- [ ] 1.3 Pin every tool as a Dockerfile `ARG` and make Renovate own the bumps:
  - OpenCode: `ARG OPENCODE_VERSION=<version>` plus a `customManager` with
    `datasourceTemplate: github-releases`, `depNameTemplate: sst/opencode`, and
    `extractVersionTemplate: ^v?(?<version>.*)$`.
  - Toolchain: a `# renovate: datasource=github-releases depName=<owner>/<repo>` line above each
    `ARG`, and one `customManager` whose regex matches the annotation plus the next `ARG`, so helm,
    helmfile, kubectl, kustomize, yq, gh and uv need no per-tool block.
  - The weekly adapter rebuild in `publish-images.yaml` carries base CVE fixes, and merging a
    Renovate bump publishes a new digest. Do not pin a release-asset sha256 that Renovate cannot
    update, or every bump will fail the build until it is edited by hand.
  - Add a `README.md` stating upstream revision, the enabled toolchain, and that this is **not** a
    Sympozium harness adapter — no contract, no capabilities.
- [ ] 1.4 Publish `ghcr.io/datahub-local/datahub-local-ai-opencode-adapter` multi-arch
  (`linux/amd64`, `linux/arm64`). No workflow edit is needed: `publish-images.yaml` discovers
  `agents/adapters/*/Dockerfile` and names the image from the directory.
- [ ] 1.5 Add to `values/_version.yaml`: the adapter image
  (`ghcr.io/datahub-local/datahub-local-ai-opencode-adapter: main@sha256:<digest>` from 1.4),
  `opencode-plugin-litellm` under a `package_version` map, `nginxinc/nginx-unprivileged` (tag), and
  the shim image (digest). Keep the `tag@sha256:…` shape: the existing `container_image_version`
  jsonata manager then proposes the digest bump. No upstream OpenCode image and no Alpine git
  version. Firecrawl is pinned by `add-firecrawl-mcp`.
- [ ] 1.6 Add the three workloads to `releases/automation/` on `bjw-s-labs/app-template`:
  `opencode-server`, `opencode-web`, `opencode-mcp`.
- [ ] 1.7 Server: one replica, `Recreate`, `runtimeClassName: gvisor`, nodeSelector
  `datahublocal-amd-1` + `kubernetes.io/arch: amd64`, uid/gid/fsGroup 1000, read-only root,
  capabilities dropped, no service-account token, `HOME=/opt/data`, `/opt/data` + `/workspace`
  PVCs, `/tmp` memory emptyDir of at least 1Gi. `command: ["opencode"]`, `args: ["serve", …]`.
- [ ] 1.8 Render with `helmfile template` and confirm: server + minter + one plugin init container,
  web proxy, shim, three Services, no ingress to the server, no root container.
- [ ] 1.9 Prove the Renovate path before merging: run
  `renovate --platform=local --dry-run=full --repository-cache=reset --onboarding=false` in
  `datahub-local-ai` and confirm it lists `sst/opencode` and each tool ARG; after the first
  publish, confirm core's Dependency Dashboard proposes a digest update for the adapter.

## 2. Server configuration

- [ ] 2.1 Add `releases/automation/files/opencode/opencode.json`: default model
  `litellm/opencode-go/deepseek-v4.1-flash`, `"plugins": ["opencode-plugin-litellm@<version>"]`,
  the Firecrawl remote MCP entry, `credential.helper` at the helper script, and the permission
  ruleset from design §9.
- [ ] 2.2 Add `AGENTS.md` with the agent's operating rules: work inside `/workspace`, report changed
  files, push only to a branch it created.
- [ ] 2.3 Add `git-credential-opencode` (shell, `curl`-based) and mount it at
  `/opt/data/bin/git-credential-opencode` with mode `0755`.
- [ ] 2.4 Add `releases/automation/templates/opencode_config.yaml` as one ConfigMap with the three
  keys via `.Files.Get`.
- [ ] 2.5 Mount the config and instructions as `subPath` files; do not replace the config directory.
- [ ] 2.6 The only init container installs the plugin (`opencode plugin add` when the cache is cold)
  as uid 1000. No `apk`, no `--root`, no git install.
- [ ] 2.7 Verify as uid 1000 under a read-only root filesystem: `git`, `helm`, `helmfile`,
  `kubectl`, `kustomize`, `yq`, `jq`, `gh`, `node`, `npm`, `uv`, `python3` and `curl` all run, and
  `git clone` over HTTPS works through the minter helper.

## 3. Minter sidecar

- [ ] 3.1 Create the GitHub App with `contents: write`, `pull_requests: write`, `metadata: read`,
  install it on the intended repositories, and create the `github-app` Secret (`app-id`,
  `installation-id`, `private-key`).
- [ ] 3.2 Add the minter sidecar: sign a 10-minute JWT, exchange at
  `POST /app/installations/<id>/access_tokens`, keep the token in memory, and serve it on loopback.
- [ ] 3.3 Re-mint when fewer than 10 minutes remain; never write a credential file.
- [ ] 3.4 Verify the server container has no `GITHUB_APP_*` and no long-lived GitHub credential.
- [ ] 3.5 Test clone/push/PR, then force cache expiry and confirm the next git call mints a new
  token without a restart.

## 4. Web proxy

- [ ] 4.1 Add the nginx Deployment + Service: `proxy_pass http://opencode-server:4096`,
  `proxy_buffering off`, upgrade headers, and a read timeout longer than a session.
- [ ] 4.2 Add an `IngressRoute` at `automation-opencode.<gateway_hostname>` to the proxy, with
  `security/oauth2-proxy-auth` and the `/oauth2/` route, plus a homepage entry.
- [ ] 4.3 Add the Traefik `headers` middleware injecting `Authorization: Basic …`.
- [ ] 4.4 Verify: anonymous redirects to dex; after login the UI loads with no second prompt;
  SSE updates stream; direct access to the server's 4096 is denied.

## 5. MCP shim

- [ ] 5.1 Add `servers/opencode/` to `datahub-local-ai-mcp` and publish
  `ghcr.io/datahub-local/mcp-opencode` by digest (one replica, no volume).
- [ ] 5.2 Implement `run_task`, `get_session`, `respond`, `abort_session` against the server API with
  Basic auth: `POST /api/session`, `POST /api/session/:id/prompt`, `GET /api/session/:id`,
  `POST /api/experimental/session/:id/wait`, `GET /api/session/:id/diff`,
  `GET/POST /api/session/:id/form*`, `GET/POST /api/session/:id/permission*`,
  `POST /api/session/:id/interrupt`, `GET /api/session/active`.
- [ ] 5.3 `run_task` waits at most `wait_seconds` (default 120, max 300), returns
  `running|idle|needs_input|error`, and never ends the session on the timeout.
- [ ] 5.4 Busy is read from `GET /api/session/active`, not memory, so a restart cannot start a
  second writer.
- [ ] 5.5 Bounded output with the truncation marker; reject a `directory` outside `/workspace`.
- [ ] 5.6 Tests: bounded wait, busy, `needs_input` + `respond`, error, truncation, directory escape.

## 6. Firecrawl

- [ ] 6.1 Register the `add-firecrawl-mcp` bridge in `opencode.json` as a remote MCP server at
  `http://{{ .Values.release_name }}-automation-mcp-firecrawl.automation.svc.cluster.local:8080/mcp`.
- [ ] 6.2 Allow `fc_firecrawl_scrape`, `fc_firecrawl_search` and `fc_firecrawl_map` in the
  permission ruleset; the bridge registers nothing else.
- [ ] 6.3 Verify search and scrape work and `FIRECRAWL_API_KEY` is absent from both the server and
  the bridge containers.
- [ ] 6.4 Confirm this release renders no Firecrawl Deployment, no `firecrawl-token` Secret and no
  `api.firecrawl.dev` egress.

## 7. Network

- [ ] 7.1 Server policy: DNS, `data/litellm` 4000, the automation Firecrawl bridge on 8080,
  `security` egress proxy 3128; ingress on
  4096 only from the proxy and shim Pods. No public 443.
- [ ] 7.2 Proxy policy: DNS + server 4096 only.
- [ ] 7.3 Shim policy: DNS + server 4096 only.
- [ ] 7.4 Server env: `HTTP_PROXY`/`HTTPS_PROXY` at
  `http://{{ .Values.release_name }}-security-egress-proxy.security.svc.cluster.local:3128` and
  `NO_PROXY` for `data.svc`, `automation.svc` and `svc.cluster.local`.
- [ ] 7.5 Verify each workload is denied outside its list, including the Kubernetes API, and that a
  direct `https://pypi.org` from the server fails while the proxied one succeeds.

## 8. Registration

- [ ] 8.1 Add a `sympozium.ai/v1alpha1 MCPServer` for the shim with `transportType: http`,
  `spec.url` at `/mcp`, `sympozium.ai/catalog: "true"`, and `app.kubernetes.io/name: mcpserver` on
  the Service.
- [ ] 8.2 Add `mcp_servers.opencode` to `releases/automation/values/hermes.yaml.gotmpl` with
  `timeout: 900`.
- [ ] 8.3 Deploy Hermes once with `bootstrap.overwrite=true`, then return it to `false`.
- [ ] 8.4 From Hermes: `hermes mcp test opencode` lists four tools; a Slack request starts a task,
  returns `running`, and a later status message returns the result.
- [ ] 8.5 Confirm a Sympozium persona can list the four tools.

## 9. Isolation and state

- [ ] 9.1 Confirm the server Pod is under gVisor on `datahublocal-amd-1`, every container is
  non-root, and the plugin cache survives a restart.
- [ ] 9.2 Confirm no service-account token is mounted and only `/opt/data`, `/workspace`, `/tmp` are
  writable.
- [ ] 9.3 Confirm a rollout terminates the old server Pod before the new one mounts either PVC.
- [ ] 9.4 Confirm no container runs `apk`, `apt`, `--initdb` or a runtime installer, and that no
  process runs as uid 0.

## 10. Verification

- [ ] 10.1 A task edits a file, runs a test, returns the final text and the changed file.
- [ ] 10.2 `.env` reads and direct `webfetch` are denied; `fc_firecrawl_search` works; `git` works.
- [ ] 10.3 A second task returns busy; `abort_session` stops the first; `get_session` reports state.
- [ ] 10.4 Record cold-start (plugin install → ready) and warm-start.
- [ ] 10.5 Clone `datahub-local-core` and run `helmfile template` from the server workspace; clone
  `datahub-local-ai` and run `uv sync --extra dev`. Both succeed through the proxy with no tool
  installed at runtime.

## 11. Egress proxy consumer (moved from `add-egress-proxy`)

- [ ] 11.1 On the server container set `HTTPS_PROXY`/`HTTP_PROXY` to
  `http://{{ .Values.release_name }}-security-egress-proxy.security.svc.cluster.local:3128` and
  `NO_PROXY` to the cluster domains.
- [ ] 11.2 Replace the server's public 443 egress with the proxy rule on 3128 and update the
  "no egress proxy" residual in the design and spec.
- [ ] 11.3 Add the `helm` allowlist group to `releases/security/values/default.yaml.gotmpl`:
  `.github.io`, `airflow.apache.org`, `downloads.apache.org`, `helm.openwebui.com`,
  `charts.redpanda.com`, `deploy.sympozium.ai`, `robusta-charts.storage.googleapis.com`,
  `ghcr.io`, `8gears.container-registry.com`, `oci.trueforge.org`.
- [ ] 11.4 Verify `helmfile template` in a cloned `datahub-local-core` resolves every chart through
  the proxy, and that an unlisted chart repository is refused.
