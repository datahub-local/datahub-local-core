# Design

## Context

One self-hosted Firecrawl in `data`, consumed only in-cluster by the Sympozium and Hermes MCP clients.
Firecrawl's durable state is a job queue: `nuq.queue_scrape` rows move queued → active → completed or
failed, and `pg_cron` reaps stalled workers. Losing that queue loses work that can simply be
requested again; it does not lose configuration, credentials, workflows or content.

The cluster already runs CNPG PostgreSQL 18 (Polaris, n8n, Superset, LiteLLM, Airflow, Miniflux,
OpenWebUI) and Valkey 9 (LiteLLM cache). The CNPG cluster is a source of truth for those services, so
Firecrawl does not get a database, role or extension there. Valkey only holds cache and rate-limit
keys, so Firecrawl shares it on logical databases 0 and 1.

Verified on 2026-10-30: Kubernetes 1.36.2, containerd 2.3.2, Valkey `databases=16`, db 0 in use by
LiteLLM and db 1 free.

## Decisions

### 1 — The upstream example on the house chart, with a disposable Postgres

The upstream chart is a source-aligned starting point whose Redis and NuQ Postgres templates render
unconditionally and whose resource defaults exceed the cluster. The house chart is
`bjw-s-labs/app-template`, already used for `polaris-jobs` and `s3-gdrive`; it renders exactly the
controllers we declare, so there are no hidden workloads to gate.

Five controllers, one replica each:

| Controller | Command | Port |
|---|---|---|
| `api` | `node --max-old-space-size=2048 dist/src/index.js` | 3002 |
| `worker` | `node --max-old-space-size=1024 dist/src/services/queue-worker.js` | 3005 |
| `nuq-worker` | `node --max-old-space-size=1024 dist/src/services/worker/nuq-worker.js` | 3006 |
| `playwright` | image entrypoint | 3000 |
| `nuq-postgres` | `docker-entrypoint.sh postgres` + `-c` overrides | 5432 |

`extract-worker` and `cclog-worker` are omitted. `api`, `playwright` and `nuq-postgres` get Services.

### 2 — RabbitMQ is omitted; the queue polls Postgres

The upstream compose sets `NUQ_RABBITMQ_URL`, but Firecrawl treats it as an optional wake-up channel:
`nuq.ts` selects `listen` only when the URL is set and otherwise polls, backing off to 10 s. RabbitMQ
also defaults `guest` to loopback, so deploying it adds a credential and a policy for no acceptance
criterion. `NUQ_WAIT_MODE=poll` is explicit. Webhooks and monitors are the paths that need the broker;
neither is exposed. The prefetch worker is omitted with the broker: `prefetchJobs()` flips queued jobs
to active and hands them to workers only through RabbitMQ, so running it without a broker strands every
scrape and crawl. `nuq-worker` polls `nuq.queue_scrape` for queued rows directly.

### 3 — A dedicated, disposable Postgres rather than the CNPG cluster

The queue needs the `nuq` schema, `pg_crypto`, `pg_cron` and a set of cron jobs. The official
`ghcr.io/firecrawl/nuq-postgres` image is exactly that: PostgreSQL 17 plus `postgresql-17-cron`, with
`shared_preload_libraries = 'pg_cron'` and `cron.database_name = 'postgres'` in the initdb template,
and `apps/nuq-postgres/nuq.sql` copied to `/docker-entrypoint-initdb.d/010-nuq.sql`.

It runs as one Deployment with a 1Gi Longhorn `ReadWriteOnce` PVC at `/var/lib/postgresql/data`,
and `PGDATA=/var/lib/postgresql/data/pgdata` because `initdb` refuses a mount root containing
`lost+found`:

- 512Mi memory limit, 500m CPU limit, 256Mi / 100m requests;
- `POSTGRES_USER=firecrawl`, `POSTGRES_DB=postgres` (the image's `cron.database_name` is `postgres`,
  and `pg_cron` refuses `CREATE EXTENSION` in any other database; the instance is dedicated, so the
  name is only a label);
- `POSTGRES_PASSWORD` from `firecrawl-credentials`;
- command-line overrides for the upstream `ALTER SYSTEM` tuning that assumes a large host:
  `max_wal_size=256MB`, `min_wal_size=32MB`, `wal_buffers=16MB`, `shared_buffers=64MB`,
  `max_connections=50`, `work_mem=2MB`, `maintenance_work_mem=32MB`, `effective_io_concurrency=16`. Command-line
  `-c` wins over the values `nuq.sql` writes during initdb;
- a 1Gi PVC, `strategy: Recreate`, `pg_isready` probes over TCP so they do not pass during the initdb
  temporary server. The volume is not backed up; losing it is a retry.

Consequences, accepted deliberately:

- A Postgres Pod restart or a rollout keeps the queue; deleting the PVC (or losing the volume)
  creates an empty queue. Clients retry the scrape or crawl.
- The image's initdb runs `nuq.sql` on a fresh volume, including the `pg_cron` schedules. A new image
  does not re-run it on an existing PVC; a schema change needs the PVC reset, accepted for a
  disposable queue.
- No backup, no PITR, no CNPG role/database/extension and no CNPG restart.
- The image runs its entrypoint as root to chown the mounted volume and `gosu` to `postgres`; dropping all
  capabilities would break both. Root is confined to this disposable instance.

### 4 — The CNPG cluster is not touched

No role, database, extension, preload or backup setting changes in
`releases/data/values/cloudnative-pg-cluster-18.yaml.gotmpl`. Issue 111 (`pg_stat_statements`) is a
separate change; it is not folded into a Firecrawl deployment. This also avoids the CNPG webhook
constraint that rejects an `imageName` change combined with a configuration change under
`switchover`.

### 5 — Valkey is shared, separated by logical database

`REDIS_URL` uses db 0 and `REDIS_RATE_LIMIT_URL` uses db 1 on
`datahub-local-core-data-valkey.data.svc:6379`, with the password in the external Secret. That is the
only separation Valkey offers; there is no key-prefix isolation. No resource change is made: the
added keys are small next to LiteLLM's cache, and `maxmemory-policy` stays `noeviction` so memory
pressure is visible rather than silently evicting LiteLLM. If the cache grows, a dedicated Redis is a
later decision.

### 6 — No extract worker and no model-provider keys

The extract worker calls a model provider; the MCP server exposes scrape, search and map, not extract.
Running the worker with no provider key would accept work it cannot finish, so it is omitted and the
extract/agent tools are never exposed. This removes `OPENAI_API_KEY`, `SUPABASE_*` and `BULL_AUTH_KEY`
from the secret set: with `USE_DB_AUTHENTICATION=false` the internal API is keyless.

### 7 — One external Secret carries the connection strings

`firecrawl-credentials` carries `POSTGRES_PASSWORD`, `REDIS_URL`, `REDIS_RATE_LIMIT_URL`,
`NUQ_DATABASE_URL` and `NUQ_DATABASE_URL_LISTEN`. It is composed by `datahub-local-secrets` from a
**new** `firecrawl-postgres-root` (never `admin-root`, so the queue password cannot unlock the shared
cluster) and the existing `admin-root` for the Valkey URLs. The Postgres container reads the password,
the API reads the URLs. Both database URLs target
`…-data-firecrawl-nuq-postgres:5432/postgres`; there is no pgbouncer in front of this instance.

### 8 — The MCP server is a stdio catalog entry; filtering is per client

Sympozium wraps stdio servers with its HTTP bridge on 8080. `toolsAllow` is applied when Sympozium
registers a catalog server for its own agents, not by the bridge: a direct `tools/list` returns the
upstream server's raw 28 tools (verified live). For Sympozium agents the allowlist narrows that to
`firecrawl_scrape`, `firecrawl_search` and `firecrawl_map`, and `toolsPrefix: fc` exposes them as
`fc_firecrawl_scrape` and friends. Crawl, agent, monitor, interact, parse and feedback can be added
later by name.

Hermes and OpenCode connect over HTTP directly, so neither inherits `toolsAllow` or `toolsPrefix`.
Hermes filters with `mcp_servers.sympozium-firecrawl.tools.include` (three raw names) and Hermes adds
its own `mcp_<server>_` prefix. OpenCode likewise sees the raw names behind its server-name prefix;
the `fc_*` names do not exist for either client. Narrowing at the bridge itself would need a proxy,
because the upstream image has no include-list option.

The server runs without `FIRECRAWL_API_KEY`; `FIRECRAWL_API_URL` points at the internal Service in
`data`. The controller always starts the workload as `/adapter/mcp-bridge --stdio-adapter` and passes
`deployment.cmd`/`args` through `STDIO_CMD`/`STDIO_ARGS`, so the MCPServer must set the image's own
entrypoint (`node dist/index.js`, workdir `/app`); without it the bridge exits with
`STDIO_CMD is required in stdio-adapter mode`. The controller sets
`app.kubernetes.io/name: mcpserver` on the Pod, which the agent and Hermes egress policies require for
port 8080.

The official `firecrawl-mcp-server:v3.36.0` image is amd64-only, while three of the six nodes are
arm64. The MCPServer CRD exposes no `nodeSelector`, and the controller rewrites the Deployment on
every reconcile, so a one-off patch is drift. A cluster-scoped `MutatingAdmissionPolicy` injects
`kubernetes.io/arch: amd64` into the Deployment, matched by the Deployment's exact name: the
controller sets `app.kubernetes.io/instance` only on the Pod template, so an `objectSelector` on
Deployment metadata never fires (the first live Deployment had no selector and landed on amd-2 by
chance). The binding needs an explicit `matchResources.namespaceSelector` for `automation`. It is
declarative and survives reconciles; verified live on 2026-10-31: an update added the selector and
the replacement Pod scheduled on `datahublocal-amd-1`.

### 9 — Hermes uses the same bridge, without its own web tools

`config.mcp_servers.sympozium-firecrawl` points at the automation-namespace bridge, not at `data`,
and its `tools.include` keeps only the three raw Firecrawl names. Hermes' existing egress rule allows
`name=mcpserver` in its own namespace on 8080, so no new Hermes policy is needed.

`config.platform_toolsets.slack` omits the native `web` and `browser` toolsets, so `web_search`,
`web_extract` and the browser tools are not offered; the Firecrawl bridge is the web surface instead.
This is a tool-surface control, not a network boundary: public egress stays allowed because Slack
Socket Mode needs it, and `terminal` can still reach the internet. Blocking that would need an
explicit egress proxy, not another NetworkPolicy (the chart's policy always allows public egress).

`seed-config` writes `config.yaml` only when the volume has none, so adding these keys needs one deploy
with `bootstrap.overwrite=true`; leaving it on would overwrite runtime edits.

### 10 — OpenCode stops using the SaaS server

`add-opencode-agent` planned a `firecrawl-mcp` Deployment against `api.firecrawl.dev` with a
`firecrawl-token` Secret. That is the same MCP server this change runs, one namespace away, with no
key. The OpenCode change is still unarchived, so it is edited in place: remove its Firecrawl workload,
secret and SaaS egress, point `opencode.json` at the bridge URL, and allow the raw Firecrawl tool names
under OpenCode's server-name prefix. This change is the only Firecrawl deployment.

### 11 — Resource envelope

| Controller | Request | Limit |
|---|---|---|
| api | 512Mi / 250m | 2Gi / 1 |
| worker | 384Mi / 100m | 1Gi / 500m |
| nuq-worker | 384Mi / 100m | 1Gi / 500m |
| playwright | 512Mi / 250m | 2Gi / 1 |
| nuq-postgres | 256Mi / 100m | 512Mi / 500m |

Concurrency knobs are cut with the replicas: `NUM_WORKERS_PER_QUEUE=2`, `MAX_CONCURRENT_JOBS=2`,
`CRAWL_CONCURRENT_REQUESTS=2`, `BROWSER_POOL_SIZE=2`, `NUQ_WORKER_COUNT=1`. Total requests are about
2.0Gi and 0.8 CPU. Raise any value only after reading actual usage.

### 12 — Failure and restart behavior

Postgres is the source of truth for the queue and has a 1Gi PVC, not backed up. Valkey holds cache
and rate-limit keys and has AOF. The API and workers are stateless.

- Deleting an API or worker Pod loses no accepted job; the queue row is already in Postgres.
- Deleting the Postgres Pod does not lose the queue because the PVC is reattached. Deleting the PVC
  loses it, by design; clients retry and no backup is taken.
- An `active` row whose worker dies is returned to `queued` by
  `nuq_queue_scrape_lock_reaper` after one minute, which is why the image's `pg_cron` matters.
- Both queue workers carry a `startupProbe` with a 150 s budget (30 × 5 s), and liveness starts only
  after it passes. Their Node process can exceed the 20 s liveness grace to bind the health port on
  an arm64 node capped at 500m CPU, which restarted the first rollout 4–7 times.

### 13 — Out of scope

No ingress, no browser UI, no public API, no autoscaling, no Valkey backup, no CNPG change, and no
issue-111 `pg_stat_statements` work. The `docs/services/data.md` page lives in
`datahub-local/datahub-local` and is a follow-up there.
