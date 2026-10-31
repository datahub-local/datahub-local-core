# Tasks

## 1. Pins and release

- [ ] 1.1 Add to `values/_version.yaml`: `ghcr.io/anomalyco/opencode` (tag),
  `opencode-plugin-litellm` (version), `nginxinc/nginx-unprivileged` (tag), the Alpine git
  version, and the shim image (digest). Firecrawl is pinned by `add-firecrawl-mcp`.
- [ ] 1.2 Add the three workloads to `releases/automation/` on `bjw-s-labs/app-template`:
  `opencode-server`, `opencode-web`, `opencode-mcp`.
- [ ] 1.3 Server: one replica, `Recreate`, `runtimeClassName: gvisor`, nodeSelector
  `datahublocal-amd-1` + `kubernetes.io/arch: amd64`, uid/gid/fsGroup 1000, read-only root,
  capabilities dropped, no service-account token, `HOME=/opt/data`, `/opt/data` + `/workspace`
  PVCs, `/tmp` memory emptyDir of at least 1Gi.
- [ ] 1.4 Render with `helmfile template` and confirm: server + minter + two init containers, web
  proxy, shim, three Services, no ingress to the server.

## 2. Server configuration

- [ ] 2.1 Add `releases/automation/files/opencode/opencode.json`: default model
  `litellm/opencode-go/deepseek-v4.1-flash`, `"plugins": ["opencode-plugin-litellm@<version>"]`,
  the Firecrawl remote MCP entry, `credential.helper` at the helper script, and the permission
  ruleset from design §9.
- [ ] 2.2 Add `AGENTS.md` with the agent's operating rules: work inside `/workspace`, report changed
  files, push only to a branch it created.
- [ ] 2.3 Add `git-credential-opencode` (shell, `wget`-based) and mount it at
  `/opt/data/bin/git-credential-opencode` with mode `0755`.
- [ ] 2.4 Add `releases/automation/templates/opencode_config.yaml` as one ConfigMap with the three
  keys via `.Files.Get`.
- [ ] 2.5 Mount the config and instructions as `subPath` files; do not replace the config directory.
- [ ] 2.6 Init containers: plugin (`opencode plugin add` when the cache is cold) and git
  (`apk add --root /opt/data/git --initdb --no-cache --keys-dir /etc/apk/keys --repositories-file /etc/apk/repositories git=<version>`).
- [ ] 2.7 Set `PATH`, `LD_LIBRARY_PATH`, `GIT_EXEC_PATH` for the git install and verify
  `git --version` and `git clone` as uid 1000.

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

- [ ] 9.1 Confirm the server Pod is under gVisor on `datahublocal-amd-1`, every long-running
  container is non-root, and git/plugin caches survive a restart.
- [ ] 9.2 Confirm no service-account token is mounted and only `/opt/data`, `/workspace`, `/tmp` are
  writable.
- [ ] 9.3 Confirm a rollout terminates the old server Pod before the new one mounts either PVC.

## 10. Verification

- [ ] 10.1 A task edits a file, runs a test, returns the final text and the changed file.
- [ ] 10.2 `.env` reads and direct `webfetch` are denied; `fc_firecrawl_search` works; `git` works.
- [ ] 10.3 A second task returns busy; `abort_session` stops the first; `get_session` reports state.
- [ ] 10.4 Record cold-start (plugin + git install → ready) and warm-start.
