# Design

## Context

NanoClaw's host is one Node process. Channel adapters route a message to a session, the host writes
it into `data/v2-sessions/<session>/inbound.db`, and a per-session agent container polls that file,
calls the model, and writes `outbound.db`. The host polls `outbound.db` and delivers the reply. There
is no IPC and no shared memory; the two SQLite files are the whole interface, one writer each.

That shape decides the cluster mapping:

- the host and every agent session must see the **same host filesystem paths**, because the spec
  carries `hostPath` → `containerPath` mounts;
- the two SQLite files must be `journal_mode=DELETE` and must not cross a filesystem whose locking
  semantics differ from local disk;
- the container runtime is swappable only through `SessionDriver`; nothing above it may branch on
  the driver's identity.

## Decisions

### 1 — Pods, not Docker-in-Docker

The upstream driver runs `docker run`. This cluster is k3s with containerd and no Docker daemon. The
alternatives were:

- **Docker socket mounted into the host pod.** Gives the host control of the node's whole container
  runtime. The agent container is the security boundary; this removes it.
- **Privileged DinD sidecar.** Equivalent blast radius, plus a nested daemon per host.
- **Kubernetes driver.** One Pod per session, created through the API with a namespace-scoped
  ServiceAccount.

The third is chosen. The driver seam already exists for exactly this (`src/drivers/installed.ts` is
the overlay hook), and pod-level realization keeps the host's RBAC limited to `pods` in one
namespace.

**Accepted deviation:** `prepare()` creates the Pod and the Pod starts immediately; `start()` is a
no-op. Docker can create without starting; Kubernetes cannot, short of a sleep-image handshake that
would add a second container and a readiness dance. The seam's observable contract is unchanged —
`prepare()` is idempotent on the session key, `start()` is safe to call once — and the PoC does not
depend on "prepared but not running".

### 2 — One RWO volume, one node

Session state is a directory of SQLite files that both the host and the agent Pod open. Options:

- **Longhorn RWX** across nodes. The share-manager serves NFS; SQLite's `journal_mode=DELETE` is
  safer over NFS than WAL, but locking still depends on the NFS implementation. `[UNVERIFIED]`.
- **`local-path` RWO with host and agents on one node.** `ReadWriteOnce` permits multiple Pods on
  the same node, and the volume is a real local directory. No network filesystem, no cross-node
  locking.

The second is chosen for the PoC: host and agent Pods carry
`nodeSelector: kubernetes.io/hostname=<pinned amd64 node>`. The cost is explicit — no HA and no
rescheduling while a session lives. A later change can move to Longhorn RWX after proving SQLite
behaviour under its NFS share; nothing in the driver assumes a single node beyond the node selector.

Mounts are realized as `persistentVolumeClaim` volumes with `subPath`, one per `MountSpec`.
`subPath` keeps the rest of the PVC out of the agent: the central DB and other groups' folders are
not visible just because they share a volume. The host mounts the volume at the project root
(`/data/nanoclaw`); that is what makes every `hostPath` in the spec resolvable and identical in
every Pod.

### 3 — The model key stays out of agent Pods

NanoClaw's `validateSpec` refuses credential values in both env lanes (`looksLikeCredential`:
`sk-…`, JWTs, cloud keys, private keys). That is deliberate: the sanctioned path is a gateway that
holds credentials and injects them at request time. Upstream ships that as the OneCLI gateway, a
local process plus a pinned SDK, which is not a good fit for this deployment yet.

For the PoC, a small **credential proxy** runs as its own Deployment:

```
agent Pod ──ANTHROPIC_BASE_URL──▶ nanoclaw-litellm-proxy:4001 ──x-api-key──▶ LiteLLM:4000/v1/messages
   (placeholder token)                    (key from Secret)
```

The agent sees a placeholder `ANTHROPIC_AUTH_TOKEN` and a base URL. The proxy reads the LiteLLM key
from its own Secret and adds `x-api-key` to every forwarded request. A minimal `litellm-proxy`
gateway provider contributes the two env vars, so nothing in the core composition is patched and
the credential check stays intact.

LiteLLM's Anthropic-compatible endpoint was probed from inside the cluster: `POST
/v1/messages` with model `opencode-go/deepseek-v4.1-flash` returned HTTP 200 and a normal
`message` body. No OpenAI-compatible client or OpenCode provider is needed.

The proxy is a PoC stopgap, not the target design. The target is a real NanoClaw gateway provider
(or an OneCLI deployment) with per-session credentials and approvals; this change records the
proxy so the first live run does not pretend the gap does not exist.

### 4 — Driver contract mapping

| `SessionDriver` | Kubernetes realization |
|---|---|
| `prepare(spec)` | `POST /api/v1/namespaces/<ns>/pods` with the composed containers; idempotent by name and labels |
| `start()` | no-op (Pod is already running) |
| `status()` | Pod phase: `Pending`→`preparing`, `Running`→`running`, `Succeeded`→`stopped`, `Failed`→`failed` with the container's exit code |
| `stop()` | `DELETE` with the spec's grace period; placement policy `--wait=false` |
| `listSessions()` | list by `nanoclaw-install` label, rebuild handles from the four canonical labels |
| `watchSessions()` | bounded polling of the list, diffed by phase; events are hints, as the seam requires |
| `execSpec()` | `kubectl exec -it <pod> -- …` |
| `reapResidue()` | delete terminal Pods older than the retention window |

Capabilities:

- `isolationTiers: ['container']`
- `admissionEnforced: false` (mount rules run in code, not in admission)
- `networkPolicy: 'declarative'` (a NetworkPolicy enforces egress)
- `encryptedVolumes: false`
- `unrealized: ['pidsLimit', 'shmSizeMb']` — no per-Pod pids cap; `/dev/shm` uses the emptyDir the
  composition does not request today
- `auxiliaryContainers: true` (the Pod spec can carry them; the PoC composes only the agent)
- `imageBuild: false` (images arrive pre-imported; self-mod rebuilds are denied by core)

### 5 — Images without a registry

There is no registry in this path. Images are built on an amd64 host and imported into the pinned
node's containerd store (`k3s ctr images import`). Consequences, all accepted for the PoC:

- host and agent images live only on that node; a reschedule to another node fails with
  `ErrImageNeverPull` and is visible, rather than silently pulling a stale tag;
- `imagePullPolicy: IfNotPresent` is required, because the tag was never pushed anywhere;
- rebuilding is an operator step, and `imageBuild: false` makes the self-modification path refuse
  instead of pretending it can rebuild.

The host image contains the fork at `/opt/nanoclaw` (built `dist/` and `node_modules`). An init
container copies it to the PVC on first boot, so the running host and the agent Pods execute from a
path that is inside the shared volume. The agent image is upstream's
`container/Dockerfile`, unmodified; its `/app/src` is the subPath mount from the same PVC, which is
how upstream already runs it.

### 6 — Hardening

- Host: non-root (uid 1000), no privilege escalation, all capabilities dropped, `RuntimeDefault`
  seccomp, read-only root filesystem, writable volume only at the project root.
- Agent Pods: non-root, no service-account token, `RuntimeDefault` seccomp, capabilities dropped,
  install surfaces mounted read-only. The root filesystem stays writable because the agent image
  writes `/tmp` and `$HOME`; upstream's Docker driver does the same.
- NetworkPolicy: DNS to `kube-system`, and egress to the credential proxy only. LiteLLM is reached
  by the proxy, not by agents. `[UNVERIFIED]` until the live run shows the agent needs nothing else.
- The host's ServiceAccount can only `create/get/list/watch/delete pods` in `automation`. It cannot
  read Secrets; the proxy mounts its key as a volume.

### 7 — What this change does not cover

Slack (or any channel), approvals, scheduled tasks, multi-node scheduling, and a production
credential gateway. The PoC's proof is one routed message: host → agent Pod → LiteLLM → reply in
`outbound.db`.

## Verification (2026-10-20)

The live PoC in `poc/` ran the upstream end-to-end host script against this driver:

- the host created `ncl-ea08ec18-sess-…` on `datahublocal-amd-1`; the agent Pod reached the proxy,
  LiteLLM answered, and `outbound.db` contained `E2E works!` with `processing_ack status=completed`;
- the agent Pod's env carried only the proxy URL and `placeholder`; no key was present;
- with `NetworkPolicy nanoclaw-agent-egress` applied, direct LiteLLM access from the agent was
  refused (`ECONNREFUSED`) and the proxy answered 200, while the e2e run still completed;
- the Pod carried nine `subPath` mounts and no volume-root mount, so the central DB stayed outside
  the agent.

Three upstream-script gaps surfaced and are recorded in `tasks.md` rather than hidden: the mailbox
side-effect import, the missing `container_configs` row, and the agent output envelope.

## Risks

- **Fork drift.** The driver and the provider are patches to a fast-moving upstream. They live in
  the fork, not here; this repository records only the deployment shape and the deviations.
- **Single node.** Losing the pinned node stops the agent plane. Accepted for the PoC and named in
  the release.
- **SQLite on a shared volume.** Same-node `local-path` avoids the NFS question. Moving to RWX
  without re-testing `journal_mode=DELETE` would be a silent corruption risk.
- **Credential proxy.** It is a single point for model access and a plaintext key holder. It is
  scoped to one namespace and one upstream host, but it is not a long-term gateway.
