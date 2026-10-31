# Tasks

## 1. Preflight

- [x] 1.1 Confirm Valkey `databases=16`; db 0 holds LiteLLM keys and db 1 is free.
- [x] 1.2 Confirm the official Firecrawl API and Playwright images are amd64+arm64; the MCP server
  image is amd64 only; `nuq-postgres` is amd64+arm64 at `latest@sha256:d719b361…`.
- [x] 1.3 Confirm Firecrawl's queue is disposable: losing `nuq.*` loses only pending jobs, not
  configuration or credentials.

## 2. Dedicated Postgres

- [x] 2.1 Add a `nuq-postgres` controller on `ghcr.io/firecrawl/nuq-postgres` (pinned in
  `values/_version.yaml`), one replica, `Recreate`, a 1Gi Longhorn RWO PVC at
  `/var/lib/postgresql/data` and `PGDATA=/var/lib/postgresql/data/pgdata`.
- [x] 2.2 Set `POSTGRES_USER=firecrawl`, `POSTGRES_DB=postgres`, `POSTGRES_PASSWORD` from
  `firecrawl-credentials`. The database is `postgres` because the image's `cron.database_name` is
  `postgres` and `pg_cron` refuses any other database.
- [x] 2.3 Override the upstream tuning with `-c max_wal_size=256MB -c min_wal_size=32MB -c
  wal_buffers=16MB -c shared_buffers=64MB -c max_connections=50 -c work_mem=2MB -c
  maintenance_work_mem=32MB -c effective_io_concurrency=16`; the image's `ALTER SYSTEM` block assumes a large host.
- [x] 2.4 Set 256Mi/100m requests and 512Mi/500m limits. Use one 1Gi Longhorn RWO PVC; do not
  back it up.
- [x] 2.5 Add `pg_isready -h 127.0.0.1 -U firecrawl -d postgres` liveness/readiness probes, so they
  do not pass during the initdb temporary server.
- [x] 2.6 Expose a `nuq-postgres` Service on 5432. Point `NUQ_DATABASE_URL` and
  `NUQ_DATABASE_URL_LISTEN` at `…-data-firecrawl-nuq-postgres:5432/postgres`.
- [x] 2.7 Confirm the entrypoint runs as root only to chown the mounted volume and `gosu` to `postgres`; do
  not drop capabilities or set `runAsNonRoot` on this container.
- [ ] 2.8 Verify `SHOW max_wal_size` is `256MB`, not the image's `16GB`, and `SELECT * FROM cron.job`
  returns the queue jobs after first start.
- [ ] 2.9 Delete the Postgres Pod and confirm the PVC is reattached with the queue intact. Delete the
  PVC separately and confirm it re-initializes from `nuq.sql`; that is the accepted data-loss boundary.

## 3. Firecrawl release

- [x] 3.1 Pin the Firecrawl API (`2.11.637`), Playwright (`latest` by digest), NuQ Postgres (`latest`
  by digest) and MCP server (`v3.36.0`) in `values/_version.yaml`. No `winkkgmbh/*`.
- [x] 3.2 Add the `app-template` release to `releases/data/helmfile.yaml.gotmpl`, with `needs` on
  Valkey, and `values/firecrawl.yaml.gotmpl`.
- [x] 3.3 Add controllers `api`, `worker`, `nuq-worker`, `playwright` and
  `nuq-postgres` with the commands, ports, probes and termination grace from the upstream chart,
  plus a startup probe on both queue workers. Omit `extract-worker`, `cclog-worker`,
  `nuq-prefetch-worker` and RabbitMQ: the prefetch worker delivers jobs only over the broker.
- [x] 3.4 Add one ConfigMap with `PORT`, `HOST`, worker ports, `NUQ_WORKER_COUNT: "1"`,
  `NUQ_WAIT_MODE: "poll"`, `USE_DB_AUTHENTICATION: "false"`, `IS_KUBERNETES: "true"`,
  `ENV: "production"`, `NUM_WORKERS_PER_QUEUE: "2"`, `MAX_CONCURRENT_JOBS: "2"`,
  `CRAWL_CONCURRENT_REQUESTS: "2"`, `BROWSER_POOL_SIZE: "2"`, `PLAYWRIGHT_MICROSERVICE_URL`, and the
  Playwright config.
- [x] 3.5 Add `firecrawl-credentials` to `datahub-local-secrets`
  (`external_secrets.firecrawl-credentials`), composed from a new `firecrawl-postgres-root` and the
  existing `admin-root` for Valkey. Keys: `POSTGRES_PASSWORD`, `REDIS_URL`,
  `REDIS_RATE_LIMIT_URL`, `NUQ_DATABASE_URL`, `NUQ_DATABASE_URL_LISTEN`; the database URLs point at
  `…-data-firecrawl-nuq-postgres:5432/postgres`.
- [x] 3.5b Load `POSTGRES_PASSWORD`, `REDIS_URL`, `REDIS_RATE_LIMIT_URL`, `NUQ_DATABASE_URL` and
  `NUQ_DATABASE_URL_LISTEN` from `firecrawl-credentials`.
- [x] 3.6 Expose only `api:3002`, `playwright:3000` and `nuq-postgres:5432` as Services. No
  IngressRoute and no UI.
- [x] 3.7 Set one replica per controller, the resource envelope from design §11, and the one 1Gi PVC.
- [ ] 3.8 Render with `helmfile template` and confirm: exactly five Deployments, no `redis`, no
  `rabbitmq`, no `prefetch`, no `extract-worker`, exactly one 1Gi PVC, no Ingress, and no CNPG
  resource.
- [ ] 3.9 Confirm the render contains no credential: search for passwords, `sk-`, Supabase and
  Firecrawl API keys.

## 4. Valkey

- [x] 4.1 Keep the shared Valkey release unchanged; `REDIS_URL` uses db 0 and
  `REDIS_RATE_LIMIT_URL` uses db 1.
- [ ] 4.2 Confirm `maxmemory-policy` is `noeviction`.
- [ ] 4.3 After Firecrawl is running, confirm keys exist in db 0 (`DBSIZE` with `-n 0`) and db 1
  (`-n 1`), and that LiteLLM still serves a request.
- [ ] 4.4 Watch `valkey_memory_used_bytes` for an hour of normal agent use; record the peak. If it
  approaches the limit, split Firecrawl onto its own Redis rather than evicting LiteLLM keys.

## 5. MCP catalog and Hermes

- [x] 5.1 Add `{{ include "name" . }}-sympozium-mcp-firecrawl` to
  `releases/automation/templates/sympozium_mcp_servers.yaml`: `transportType: stdio`,
  `toolsPrefix: fc`, `timeout: 60`, `label sympozium.ai/catalog: "true"`, image pinned, env
  `FIRECRAWL_API_URL: http://{{ .Values.release_name }}-data-firecrawl-api.data.svc.cluster.local:3002`,
  `cmd: node`, `args: [dist/index.js]`, and
  `toolsAllow: [firecrawl_scrape, firecrawl_search, firecrawl_map]`.
- [x] 5.2 Add the `MutatingAdmissionPolicy` + binding that injects `kubernetes.io/arch: amd64` into
  the MCP Deployment. Match the Deployment by name: the controller sets
  `app.kubernetes.io/instance` only on the Pod template, so the original `objectSelector` never
  fired and the first Deployment had no selector. The binding needs an explicit
  `matchResources.namespaceSelector` for `automation`. Verified live with an update replacing the
  Pod on `datahublocal-amd-1`.
- [x] 5.3 Confirm the controller sets `app.kubernetes.io/name: mcpserver` on the Pod. If it does not,
  fix the label before relying on 8080 egress.
- [x] 5.4 Verify `MCPServer` reports ready, the Pod carries `app.kubernetes.io/name: mcpserver` and
  the amd64 selector, and a direct `tools/list` over `svc:8080/mcp` returns the upstream raw names
  (28 tools). `toolsAllow`/`toolsPrefix` only filter Sympozium agent registration; direct clients
  filter with their own include list.
- [x] 5.5 Add `sympozium-firecrawl` to `releases/automation/values/hermes.yaml.gotmpl` under
  `config.mcp_servers`, pointing at
  `http://{{ .Values.release_name }}-automation-sympozium-mcp-firecrawl.automation.svc.cluster.local:8080/mcp`,
  filtering with `tools.include: [firecrawl_scrape, firecrawl_search, firecrawl_map]`, and set
  `config.platform_toolsets.slack` without the `web` and `browser` toolsets.
- [ ] 5.6 Deploy Hermes once with `bootstrap.overwrite=true`, confirm the key lands in `config.yaml`,
  then return the flag to `false`.
- [ ] 5.7 Verify the MCP Pod can reach `data:3002` and that no NetworkPolicy in either namespace
  denies it.
- [ ] 5.8 From Hermes, list MCP servers and run one scrape of a real URL through
  `sympozium-firecrawl`.
- [ ] 5.9 After the overwrite deploy, run `hermes tools list --platform slack` and confirm `web` and
  `browser` are absent, `sympozium-firecrawl` is listed, and only its three included tools are
  offered.

## 6. Supersede the SaaS server in `add-opencode-agent`

- [x] 6.1 Update that change's proposal, design and spec to remove its `firecrawl-mcp` Deployment,
  `firecrawl-token` Secret and `api.firecrawl.dev` egress.
- [x] 6.2 Point its `opencode.json` Firecrawl entry at
  `http://{{ .Values.release_name }}-automation-sympozium-mcp-firecrawl.automation.svc.cluster.local:8080/mcp`.
- [ ] 6.3 Allow the raw Firecrawl tool names under OpenCode's server-name prefix; `fc_*` does not
  exist on the bridge. Keep crawl, agent, monitor, interact, parse and feedback denied.
- [ ] 6.4 Re-render that release and confirm no Firecrawl API key is referenced and no SaaS host
  remains.

## 7. Verification

- [x] 7.1 `GET /v0/health/readiness` on the API Service returns 200.
- [x] 7.2 `POST /v2/scrape {"url":"https://example.com","formats":["markdown"]}` returns markdown
  with no `Authorization` header.
- [ ] 7.3 The job appears in `nuq.queue_scrape` and reaches `completed`; no row stays `active` beyond
  one minute.
- [ ] 7.4 Force a scrape failure and confirm there is no orphaned `active` row and the row is
  `failed` with a reason.
- [ ] 7.5 Delete the API Pod and one nuq worker during a scrape; confirm the queue resumes and the
  job completes.
- [ ] 7.6 Delete the Postgres Pod and confirm the queue survives; delete the PVC and confirm a new
  empty queue comes up and a new scrape succeeds. That is the accepted data-loss boundary.
- [ ] 7.7 Confirm no Firecrawl account key exists and no SaaS egress is used.
- [x] 7.8 `POST /v2/search {"query":"opencode","limit":2}` returns results; keyless `search` works
  against the self-hosted API (200, two web results on 2026-10-31).

## 8. Docs and spec

- [x] 8.1 Update `docs/services/data.md` in `datahub-local/datahub-local` with the Firecrawl release,
  the disposable Postgres, Valkey db 0/1 and the MCP entry.
- [x] 8.2 Run `openspec validate add-firecrawl-mcp --strict`.
- [ ] 8.3 Run `helmfile template` before review.
