# Proposal

## Why

The platform's agents need one reviewed web surface: search a query, scrape a known URL, and map a
site. The only Firecrawl planned today is the SaaS MCP server in `add-opencode-agent`, which needs a
Firecrawl account key, sends every URL to a third party, and is not part of the Sympozium catalog that
the personas and Hermes consume.

Firecrawl is self-hostable. Its durable state is a disposable job queue, not application data: a lost
scrape is a retry, not a lost workflow. That is the reason to give it its own tiny Postgres instead of
touching the CNPG cluster that holds Polaris, n8n, Superset and the other sources of truth. Valkey is
different — it holds only cache and rate-limit keys — so the existing instance is shared on logical
database 0/1.

## What Changes

- Add release `{{ .Values.release_name }}-data-firecrawl` in `data` on `bjw-s-labs/app-template`,
  reproducing the upstream example chart's `api`, `worker`, `nuq-worker`, `nuq-prefetch-worker`,
  `playwright` and `nuq-postgres` workloads. No bundled Redis, no RabbitMQ, no extract worker, no
  cclog worker, no UI, no ingress.
- Run Firecrawl's `nuq-postgres` as a dedicated 512Mi / 0.5 CPU Deployment with a 1Gi Longhorn PVC, pinned
  to the official image, which already carries `pg_cron` and runs `nuq.sql` at initdb. The upstream
  tuning is overridden on the command line so it fits the small instance.
- Point `REDIS_URL` at the shared Valkey logical db 0 and `REDIS_RATE_LIMIT_URL` at db 1. The
  instance is sized for both; no Redis workload and no Valkey resource change are added here.
- Add `{{ include "name" . }}-sympozium-mcp-firecrawl` to the Sympozium catalog as a stdio MCP server
  running the official `ghcr.io/firecrawl/firecrawl-mcp-server`: `toolsPrefix: fc`, `toolsAllow` of
  scrape, search and map only, `timeout: 60`. The official image is amd64-only, so a cluster-scoped
  `MutatingAdmissionPolicy` pins that Deployment to amd64 nodes; the other Firecrawl images are
  multi-arch.
- Add `sympozium-firecrawl` to Hermes' `config.mcp_servers`, which needs one deploy with
  `bootstrap.overwrite=true`.
- Supersede the SaaS Firecrawl MCP planned by `add-opencode-agent`: that change drops its
  `firecrawl-mcp` workload and `firecrawl-token` Secret and points its `opencode.json` entry at the
  same bridge.

Not changed: the CNPG cluster and its roles/databases/extensions, LiteLLM, the Valkey release, the
other MCP servers, and every other release. Issue
`datahub-local/datahub-local#111` (`pg_stat_statements`) is deliberately not folded in here.

## Capabilities

### New Capabilities

- `firecrawl`: the self-hosted Firecrawl API, its disposable NuQ Postgres, its shared Valkey usage,
  the MCP catalog entry, and the agent wiring.

### Modified Capabilities

- `hermes-gateway`: the MCP tool surface gains a seventh server, `sympozium-firecrawl`.

## Impact

- `releases/data/helmfile.yaml.gotmpl`: one new `app-template` release.
- `releases/data/values/firecrawl.yaml.gotmpl`: six controllers, three Services, one ConfigMap, one
  1Gi PVC.
- `releases/automation/templates/sympozium_mcp_servers.yaml`: one `MCPServer`.
- `releases/automation/templates/firecrawl_mcp_amd64.yaml`: one `MutatingAdmissionPolicy` and binding.
- `releases/automation/values/hermes.yaml.gotmpl`: one `mcp_servers` entry.
- `values/_version.yaml`: Firecrawl API, Playwright, `nuq-postgres` and MCP server images, pinned by
  tag/digest.
- External: `firecrawl-credentials` with `POSTGRES_PASSWORD`, `REDIS_URL`, `REDIS_RATE_LIMIT_URL`,
  `NUQ_DATABASE_URL` and `NUQ_DATABASE_URL_LISTEN`. The database URLs target the dedicated
  `…-data-firecrawl-nuq-postgres` Service on `/postgres`.
- No CNPG restart, no CNPG role/database/extension change and no new image build.
