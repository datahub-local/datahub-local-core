# Spec Delta

## ADDED Requirements

### Requirement: Firecrawl runs as one house-chart release and does not touch the CNPG cluster

The release `{{ .Values.release_name }}-data-firecrawl` SHALL be rendered by
`bjw-s-labs/app-template` in the `data` namespace and SHALL contain exactly the `api`, `worker`,
`nuq-worker`, `playwright` and `nuq-postgres` controllers. It SHALL NOT render
a Redis, a RabbitMQ, a prefetch worker, an extract worker, a cclog worker, a browser UI, or an Ingress,
and it SHALL NOT
add a role, database, extension or setting to the CNPG cluster.

#### Scenario: The render is self-contained

- **WHEN** the release is rendered
- **THEN** the output contains five Deployments and no `redis`, `rabbitmq`, `prefetch`, `extract-worker`
  or `cclog-worker` workload
- **AND** the only Services are the API on 3002, Playwright on 3000 and NuQ Postgres on 5432
- **AND** no CloudNativePG resource is changed by this release

#### Scenario: Every Firecrawl container reaches its dependency

- **WHEN** the API Pod environment is inspected
- **THEN** `REDIS_URL` points at the shared Valkey
- **AND** `NUQ_DATABASE_URL` and `NUQ_DATABASE_URL_LISTEN` point at the release's `nuq-postgres`
  Service
- **AND** `PLAYWRIGHT_MICROSERVICE_URL` points at the release's Playwright Service

### Requirement: Only official images are pinned

Every Firecrawl workload SHALL run an official `ghcr.io/firecrawl/*` image at a tag and digest
pinned in `values/_version.yaml`. No workload SHALL run a `winkkgmbh/*` image or an unpinned `latest`.

#### Scenario: The render is immutable

- **WHEN** the rendered Pod specs are searched for image references
- **THEN** every Firecrawl image is a digest-pinned official image
- **AND** no `latest` tag remains unpinned

### Requirement: PostgreSQL is a dedicated, disposable instance

The queue SHALL run on the official `ghcr.io/firecrawl/nuq-postgres` image as one Deployment with an
1Gi Longhorn `ReadWriteOnce` PVC at `/var/lib/postgresql/data`, `PGDATA=/var/lib/postgresql/data/pgdata`
(so `initdb` does not see the volume's `lost+found`), one replica, `Recreate`. The PVC SHALL NOT be
backed up. It SHALL use
`POSTGRES_USER=firecrawl`, `POSTGRES_DB=postgres`, and `POSTGRES_PASSWORD` from
`firecrawl-credentials`. It SHALL be capped at 512Mi memory and 500m CPU.

#### Scenario: The database is isolated

- **WHEN** the `data` namespace is inspected
- **THEN** `nuq-postgres` is a Firecrawl-owned Deployment with one 1Gi PVC
- **AND** the CNPG cluster has no `firecrawl` role, database or extension

#### Scenario: The queue survives a Pod restart

- **WHEN** the Postgres Pod is deleted or the release is rolled
- **THEN** the PVC is reattached and the queue is intact
- **AND** no re-initialization runs

#### Scenario: Losing the volume is a retry

- **WHEN** the PVC is deleted
- **THEN** a new instance initializes from the image's `nuq.sql`
- **AND** the queue is empty, which is accepted: a lost job is retried by the client

### Requirement: The queue schema and pg_cron come from the image, with the tuning overridden

The `nuq-postgres` image SHALL run `nuq.sql` at initdb, creating the `nuq` schema, its tables and
indexes, and the `pg_cron` jobs. The `postgres` database SHALL be used because the image sets
`cron.database_name = 'postgres'`. The upstream `ALTER SYSTEM` values that assume a large host SHALL
be overridden on the command line to `max_wal_size=256MB`, `min_wal_size=32MB`, `wal_buffers=16MB`,
`shared_buffers=64MB`, `max_connections=50`, `work_mem=2MB`, `maintenance_work_mem=32MB` and
`effective_io_concurrency=16`.

#### Scenario: The queue and scheduler exist

- **WHEN** the fresh database is inspected
- **THEN** `nuq.queue_scrape`, `nuq.queue_scrape_backlog`, `nuq.queue_crawl_finished` and
  `nuq.group_crawl` exist
- **AND** `SELECT * FROM cron.job` returns the queue cleaners, lock reapers and reindex jobs

#### Scenario: The small instance keeps its limits

- **WHEN** `SHOW max_wal_size` and `SHOW shared_buffers` run
- **THEN** they return `256MB` and `64MB`, not the image's `16GB` / large-host defaults

### Requirement: Valkey is the shared instance with logical database separation

`REDIS_URL` SHALL use logical db 0 and `REDIS_RATE_LIMIT_URL` SHALL use logical db 1 of the existing
shared Valkey. This release SHALL NOT add a Redis workload or change the Valkey release's resources.

#### Scenario: Firecrawl keys do not collide with LiteLLM

- **WHEN** the API has served a scrape and a search
- **THEN** db 0 and db 1 both hold keys
- **AND** LiteLLM continues to serve a request

#### Scenario: No eviction policy is introduced

- **WHEN** the Valkey configuration is read
- **THEN** `maxmemory-policy` is still `noeviction`

### Requirement: The API is internal, keyless, and health-checked

The API SHALL listen only inside the cluster on 3002, with no Ingress and no published surface. It
SHALL run with `USE_DB_AUTHENTICATION=false`, so a scrape needs no API key, and SHALL pass
`/v0/health/liveness` and `/v0/health/readiness`. No model-provider, Supabase or Bull credential
SHALL be mounted.

#### Scenario: An unauthenticated scrape succeeds

- **WHEN** `POST /v2/scrape` is sent with `{"url":"https://example.com","formats":["markdown"]}` and
  no `Authorization` header
- **THEN** the response contains markdown

#### Scenario: Nothing publishes the API

- **WHEN** the release is rendered
- **THEN** there is no IngressRoute or Ingress targeting the API
- **AND** the API Service is `ClusterIP`

#### Scenario: No unused provider key is mounted

- **WHEN** the API Pod environment is inspected
- **THEN** `OPENAI_API_KEY`, `SUPABASE_*` and `BULL_AUTH_KEY` are absent

### Requirement: One external Secret carries the connection strings

The Firecrawl workloads SHALL consume `POSTGRES_PASSWORD`, `REDIS_URL`, `REDIS_RATE_LIMIT_URL`,
`NUQ_DATABASE_URL` and `NUQ_DATABASE_URL_LISTEN` from `firecrawl-credentials`, created outside this
repository. The password SHALL be composed from a dedicated `firecrawl-postgres-root`, never from the
shared cluster's `admin-root`, so a queue credential cannot unlock the CNPG cluster. The Valkey URLs
MAY reuse `admin-root`. No credential SHALL appear in a values file, a ConfigMap, or a rendered
manifest.

#### Scenario: The render holds references, not secrets

- **WHEN** the rendered manifests are searched for credentials
- **THEN** the password and URLs appear only as Secret references
- **AND** no password or API key is a literal

#### Scenario: The queue password is not the cluster password

- **WHEN** the `firecrawl-postgres-root` value is compared with `admin-root`
- **THEN** they are different secrets
- **AND** `firecrawl-credentials` sources `POSTGRES_PASSWORD` from `firecrawl-postgres-root`

### Requirement: The MCP server is a catalog entry with a narrow tool surface

The catalog and its workloads SHALL be one `bjw-s-labs/app-template` release, with the four custom
servers under `controllers`/`service` and the `MCPServer` objects plus cluster RBAC under
`rawResources`; `fullnameOverride` and `forceRename` SHALL produce `…-automation-mcp-*` names.

`{{ .Values.release_name }}-automation-mcp-firecrawl-http` SHALL be a Deployment and Service running
`ghcr.io/firecrawl/firecrawl-mcp-server` in its own stateless HTTP mode, with
`HTTP_STREAMABLE_SERVER=true`, `HOST=0.0.0.0`, `PORT=8080`, and `FIRECRAWL_API_URL` pointing at the
`data` API Service without a Firecrawl API key. It SHALL set `FIRECRAWL_MCP_ALLOWED_HOSTS` to the
Service's short and FQDN names, because FastMCP rejects an unknown `Host` header even when the health
probe passes. It SHALL NOT use Sympozium's stdio bridge: the bridge
misroutes replies, so a `tools/call` can wait out the timeout while a later request receives the
previous result. The Deployment SHALL pin `kubernetes.io/arch: amd64` directly, because the image is
amd64-only and no controller rewrites this pod template. The Pod SHALL carry
`app.kubernetes.io/name: mcpserver` and SHALL be allowed to reach the `data` API Service on 3002.

The `MCPServer` `{{ .Values.release_name }}-automation-mcp-firecrawl` SHALL use `transportType: http` with
`url` at that Service, `toolsPrefix: fc`, `timeout: 60`, and SHALL allow exactly
`firecrawl_scrape`, `firecrawl_search` and `firecrawl_map`. `toolsAllow` and `toolsPrefix` SHALL be
treated as Sympozium agent-registration filters, not transport filters: the server exposes the raw
upstream name set, and each direct HTTP client SHALL narrow it itself. A client that cannot filter
SHALL NOT be pointed at the server.

#### Scenario: Sympozium agents see three prefixed tools

- **WHEN** a Sympozium agent enumerates the catalog server
- **THEN** it is offered `fc_firecrawl_scrape`, `fc_firecrawl_search` and `fc_firecrawl_map`
- **AND** no crawl, agent, monitor, interact, parse, feedback or credit tool is offered

#### Scenario: The server exposes the raw upstream names

- **WHEN** `tools/list` is called on the HTTP instance directly
- **THEN** it returns the upstream names such as `firecrawl_scrape` without the `fc_` prefix
- **AND** that is why every direct client filters with its own include list

#### Scenario: The server runs its own HTTP transport

- **WHEN** the MCP Deployment is rendered
- **THEN** it runs `node dist/index.js` with `HTTP_STREAMABLE_SERVER=true` and no stdio adapter
- **AND** readiness and liveness probe `/health` on 8080

#### Scenario: The Pod is reachable by the agent policies

- **WHEN** an agent connects to the server on 8080
- **THEN** the Pod carries `app.kubernetes.io/name: mcpserver`
- **AND** the call is admitted by the agent egress policy

#### Scenario: The amd64-only image is scheduled safely

- **WHEN** the MCP Deployment is rendered
- **THEN** its pod template has `kubernetes.io/arch: amd64`
- **AND** it does not rely on an admission policy, because this Deployment is not controller-managed
- **AND** the Pod does not land on an arm64 node

#### Scenario: The server reaches the API

- **WHEN** the MCP Pod calls the `data` API Service on 3002
- **THEN** no NetworkPolicy denies the egress

### Requirement: Hermes and OpenCode use the same self-hosted server

Hermes SHALL register `sympozium-firecrawl` in `config.mcp_servers` at the
`…-mcp-firecrawl-http` Service URL, with `tools.include` of `firecrawl_scrape`,
`firecrawl_search` and `firecrawl_map`, and SHALL disable the native `web` and `browser` toolsets on
every platform through `config.agent.disabled_toolsets`. That is a tool-surface control only: public
egress SHALL stay allowed because Slack Socket Mode needs it, and the spec SHALL NOT claim a network
boundary. The OpenCode change SHALL use the same HTTP instance and SHALL NOT deploy a second Firecrawl
or hold a Firecrawl account key.

#### Scenario: Hermes scrapes through the HTTP instance

- **WHEN** Hermes enumerates its MCP servers and calls a scrape tool
- **THEN** `sympozium-firecrawl` is listed
- **AND** the call returns page markdown from the `data` API without waiting out the MCP timeout

#### Scenario: Hermes has no built-in web tools

- **WHEN** `hermes tools list --platform cli` or `--platform slack` runs
- **THEN** `web` and `browser` are absent
- **AND** only the three included Firecrawl tools are offered by `sympozium-firecrawl`

#### Scenario: There is only one Firecrawl

- **WHEN** the cluster is searched for Firecrawl Deployments and Secrets
- **THEN** there is one API release and one MCP server
- **AND** no `firecrawl-token` Secret and no `api.firecrawl.dev` egress exist

### Requirement: Restarts and failures leave no orphaned queue state

Deleting the API Pod or a worker SHALL not lose an accepted job, because Postgres holds the queue.
An `active` row whose worker disappeared SHALL return to `queued` within one minute. Deleting the
Postgres Pod SHALL NOT lose the queue; deleting the PVC MAY, and that is accepted.

#### Scenario: A scrape survives an API restart

- **WHEN** the API Pod and one nuq worker are deleted during a scrape
- **THEN** the job completes after the Pods return
- **AND** no row remains `active` beyond one minute

#### Scenario: A forced failure is terminal

- **WHEN** a scrape is forced to fail
- **THEN** its row is `failed` with a reason
- **AND** no `active` row is left behind

### Requirement: The resource envelope is fixed at one replica and measured

Each controller SHALL run one replica with explicit requests and limits. The release SHALL NOT use
the upstream chart's multi-replica, multi-gigabyte defaults, and SHALL NOT autoscale. `nuq-postgres`
SHALL NOT exceed 512Mi of memory.

#### Scenario: The release fits the cluster

- **WHEN** the rendered resources are summed
- **THEN** total requests stay near 2.0Gi of memory and about 0.8 CPU
- **AND** every controller has both a request and a limit

#### Scenario: Growth is evidence-based

- **WHEN** a replica count, concurrency setting or resource value is raised
- **THEN** measured usage from the running release justifies it
