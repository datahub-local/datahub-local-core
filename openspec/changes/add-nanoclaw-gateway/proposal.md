# Proposal

## Why

The OpenClaw deployment was reverted in favour of NanoClaw. The reason is structural, not
cosmetic: OpenClaw runs every agent in one Node process with application-level permissions, while
NanoClaw runs each agent session in its own Linux container and keeps the host small enough to
audit. On a cluster that already runs agent workloads, the second property is the one we want.

NanoClaw does not ship a Kubernetes driver. Its only realization is `DockerSessionDriver`, which
shells `docker run`; there is no Docker daemon on these k3s nodes, and giving the host a socket or a
privileged DinD sidecar would trade the container boundary for cluster-level access. The project
does, however, expose a driver seam (`src/drivers/`) with two implementations (Docker, plus test
fakes) and an overlay hook, so a Kubernetes driver fits the intended extension point rather than
patching the core.

Two other gaps were confirmed against the running cluster:

- the repository publishes no images, so host and agent images must be built and imported;
- NanoClaw's credential model rejects credential values in container env by contract
  (`validateSpec` → `looksLikeCredential`), and its default OneCLI gateway is not deployable here
  as-is, so the model key needs a cluster-side injector.

## What Changes

- Fork NanoClaw and add `KubernetesSessionDriver`, registered through `src/drivers/installed.ts`:
  one Pod per agent session, session state shared with the host through subPath mounts from a
  single PVC.
- Add a minimal `litellm-proxy` gateway provider that contributes `ANTHROPIC_BASE_URL` and a
  placeholder token, plus a cluster-side proxy Deployment that injects the real LiteLLM key.
- Point the agent runtime at the in-cluster LiteLLM proxy through its Anthropic-compatible
  `/v1/messages` endpoint, using the Claude Agent SDK already shipped upstream.
- Add a `nanoclaw` release to `releases/automation/`: host Deployment, PVC, ServiceAccount and
  scoped RBAC (pods only), the credential proxy, and a Service. This is the promotion step after
  the PoC; it is specified and tasked but deliberately not enabled in this change while images
  live on one node and ArgoCD would auto-sync it.
- Pin host and agent pods to one amd64 node so the RWO state volume stays mountable by both.

Not changed: LiteLLM, the MCP servers, the ArgoCD ApplicationSet, and every existing release.
Slack and other channels are out of scope for this change.

## Capabilities

### New Capabilities

- `nanoclaw-gateway`: how NanoClaw is built and run on this cluster — the Kubernetes session
  driver and its lifecycle mapping, the shared session-state volume, the credential-injecting
  model proxy, the model path, pod hardening, and the single-node constraint.

### Modified Capabilities

<!-- None. -->

## Impact

- New images (`nanoclaw-host`, `nanoclaw-agent`) built from the fork. They are imported into the
  k3s containerd store on the pinned node; there is no registry in this path.
- New namespace-scoped resources in `automation`: PVC, ServiceAccount, Role/RoleBinding, host
  Deployment, credential proxy, Service.
- One secret: the LiteLLM key must exist in the `automation` namespace for the proxy. That is a
  `datahub-local-secrets` change and is called out in `tasks.md` rather than made here.
- The fork lives outside this repository. This repository carries the deployment and the record of
  every driver deviation; the fork carries the driver code.
