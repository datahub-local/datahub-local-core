# PoC evidence — 2026-10-20

Cluster: k3s v1.36.2, node `datahublocal-amd-1` (amd64), namespace `spike-nanoclaw`.
Images: `nanoclaw-host:poc`, `nanoclaw-agent:poc`, imported through `k3s ctr images import`.

## Route and reply

Host Job, `scripts/test-v2-host.ts`:

```
[INFO] Session runtime driver selected driver="kubernetes" capabilities={... "imageBuild":false ...}
[INFO] Spawning session sessionId="sess-1792528469204-nmgk2g"
[INFO] Session Pod created pod="ncl-ea08ec18-sess-1792528469204-nmgk2g" namespace="spike-nanoclaw"

messages_in (inbound.db):
  [msg-e2e-1:ag-e2e] status=pending kind=chat

messages_out (outbound.db):
  [msg-1792528485021-kl2p2v] kind=chat
  → E2E works!

processing_ack (outbound.db):
  [msg-e2e-1:ag-e2e] status=completed changed=2026-10-20T20:34:45.043Z
```

Agent Pod log:

```
[agent-runner] Starting v2 agent-runner (provider: claude)
[poll-loop] Processing 1 message(s), kinds: chat
[poll-loop] Session: ...
```

## Agent Pod shape

```
nodeName: datahublocal-amd-1
automountServiceAccountToken: false
securityContext: fsGroup=1000 runAsGroup=1000 runAsNonRoot=true runAsUser=1000 seccomp=RuntimeDefault

env:
  ANTHROPIC_BASE_URL=http://litellm-proxy.spike-nanoclaw.svc.cluster.local:4001
  ANTHROPIC_AUTH_TOKEN=placeholder
  ANTHROPIC_API_KEY=placeholder

mounts:
  /workspace                                      <- data/v2-sessions/ag-e2e/<session>
  /app/.nanoclaw-session.json                     <- data/v2-sessions/ag-e2e/.context/<session>.json (ro)
  /workspace/agent                                <- groups/test-agent-e2e
  /workspace/agent/container.json                 <- groups/test-agent-e2e/container.json (ro)
  /workspace/agent/plugins                        <- groups/test-agent-e2e/plugins (ro)
  /workspace/agent/CLAUDE.md                      <- groups/test-agent-e2e/CLAUDE.md (ro)
  /home/node/.claude                              <- data/v2-sessions/ag-e2e/.claude-shared
  /app/src                                        <- container/agent-runner/src (ro)
  /app/skills                                     <- container/skills (ro)
```

The volume root (`/data/nanoclaw`) is not mounted; the central DB is not visible to the agent.

## Egress

From the agent Pod, with `NetworkPolicy nanoclaw-agent-egress` applied:

```
litellm direct BLOCKED ECONNREFUSED   # http://…-litellm.data.svc:4000
proxy 200                             # http://litellm-proxy.spike-nanoclaw.svc:4001
```

The same e2e run completed after the policy was applied.

## Reproduce

See `README.md`. `poc/nanoclaw-poc.patch` carries the fork changes (driver, gateway provider,
script fixes).
