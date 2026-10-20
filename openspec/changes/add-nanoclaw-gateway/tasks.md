# Tasks

## 1. Fork and driver

- [x] 1.1 Fork `nanocoai/nanoclaw` at `4813e21` and add `src/drivers/kubernetes-driver.ts`.
- [x] 1.2 Register the driver in `src/drivers/installed.ts` (the overlay hook), selected by
  `NANOCLAW_RUNTIME_DRIVER=kubernetes`.
- [x] 1.3 Implement the seam: `prepare`, `start`, `status`, `stop`, `execSpec`, `listSessions`,
  `watchSessions`, `reapResidue`, `capabilities`. Watch is a bounded poll; no raw Kubernetes stream.
- [x] 1.4 Realize mounts as PVC `subPath` volumes; refuse a host path outside the volume root with
  a non-retryable spec error. Verified in the live Pod: nine mounts, `/app/src` and group config
  read-only, the volume root not mounted.
- [x] 1.5 Map Pod phase to `SessionStatus`, including the container exit code on `Failed`. Verified
  `running` on a live Pod and `stopped` when the Pod is gone; `Failed` not exercised by a clean run.
- [x] 1.6 Report `imageBuild: false`, `pidsLimit` and `shmSizeMb` as `unrealized`. The selected
  driver log line shows exactly that capability set.

## 2. Credential proxy and provider

- [x] 2.1 Add a `litellm-proxy` gateway provider contributing `ANTHROPIC_BASE_URL` and a
  placeholder `ANTHROPIC_AUTH_TOKEN`; registered in `src/gateway-providers/installed.ts`.
- [x] 2.2 Ship the proxy as a small Node HTTP forwarder: read the key from
  `/etc/nanoclaw/litellm-key`, add `x-api-key`, forward to `LITELLM_URL`.
- [x] 2.3 Verify the Anthropic-compatible endpoint: `POST /v1/messages` with
  `opencode-go/deepseek-v4.1-flash` returned HTTP 200 through the proxy.
- [x] 2.4 Prove the agent never receives the key: the Pod spec carries `placeholder` for both
  tokens and only the proxy URL; no secret volume is mounted.

## 3. Images

- [x] 3.1 Host image: Node 22, `pnpm install --frozen-lockfile`, `pnpm build`, `kubectl` v1.36.2,
  the fork at `/opt/nanoclaw`.
- [x] 3.2 Agent image: upstream `container/Dockerfile`, unmodified.
- [x] 3.3 Import both into `datahublocal-amd-1`'s containerd store; `IfNotPresent` resolves without
  a registry. `node:22-slim` imported for the proxy as well.

## 4. Live PoC

- [x] 4.1 Namespace `spike-nanoclaw`, PVC (`local-path`, 20 Gi), ServiceAccount, Role and
  RoleBinding limited to `pods` in that namespace.
- [x] 4.2 Host Job seeds the PVC from `/opt/nanoclaw` and runs `scripts/test-v2-host.ts`.
- [x] 4.3 Agent Pod reached the proxy, LiteLLM answered, and `outbound.db` contains
  `E2E works!` with `processing_ack status=completed`.
- [x] 4.4 Failure modes met on the way, recorded rather than smoothed over:
  - `No agent mailbox registered` — `scripts/test-v2-host.ts` bypasses `src/index.ts`, so the
    sqlite mailbox side-effect import is required in the script.
  - `Container config not found for agent group` — the v2 script predates `container_configs`;
    `ensureContainerConfig()` must be called for the test group.
  - The agent omitted the `<message to="…">` wrapper when the prompt asked only for text; the
    prompt now asks for the exact envelope.
- [x] 4.5 NetworkPolicy: direct LiteLLM from the agent Pod is refused (`ECONNREFUSED`); the proxy
  answers HTTP 200. The allowed path still completes the e2e run.

## 5. Release

- [ ] 5.1 Add a `nanoclaw` release to `releases/automation/helmfile.yaml.gotmpl` using
  `app-template`. Deliberately not done in this change: the PoC images exist only on one node, and
  a release would auto-sync through ArgoCD. Promotion needs a registry (or an image-import job)
  first.
- [ ] 5.2 Values: host Deployment, state PVC, RBAC, proxy Deployment, Service, NetworkPolicy, and
  the single-node pin.
- [ ] 5.3 `helm template` renders, and every deviation from upstream's Docker path is commented
  where it appears.
- [ ] 5.4 Declare the LiteLLM key Secret in `datahub-local-secrets`; the release reads it by
  reference only.

## 6. Deferred

- [ ] 6.1 Slack channel (needs a channel skill applied to the fork and a second Slack app decision).
- [ ] 6.2 Replace the credential proxy with a real gateway provider or OneCLI.
- [ ] 6.3 Multi-node state: Longhorn RWX after testing SQLite `journal_mode=DELETE` on its NFS
  share.
- [ ] 6.4 Scheduled tasks and approvals end-to-end.
