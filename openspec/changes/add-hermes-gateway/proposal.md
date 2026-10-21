# Proposal

## Why

OpenClaw was reverted. NanoClaw was evaluated and live-tested with a Kubernetes session driver; it
worked, but required a fork of a fast-moving project, locally built images, and a single-node volume
so host and agent could share SQLite files. Its isolation was still runc, not a kernel boundary.

Hermes Agent (Nous Research) keeps the gateway shape without the fork: one process, one Deployment,
channels as configuration, an official image, Slack over Socket Mode, approvals, allowlists, memory,
cron and MCP. It can also run under the cluster's existing `gvisor` RuntimeClass, which gives the
agent's shell execution a user-space kernel instead of the node's.

The deployment vehicle is the community chart `jyje/hermes-agent-helm`. It is published as OCI and
as a Helm repository, tracks upstream `v0.22.2`, and — unlike the other community chart — ships the
two overlays this deployment needs: a Pod Security Standards `restricted` profile that actually
boots the image, and a LiteLLM/egress-lockdown example. Using it avoids both a fork and a
hand-maintained template.

## What Changes

- Add a `hermes` release to `releases/automation/` from
  `oci://ghcr.io/jyje/hermes-agent-helm/hermes-agent`, pinned to chart `1.21.0` (Hermes `v0.22.2`).
- Layer `values-hardened.yaml`: non-root uid/gid 10000, read-only root filesystem, writable
  executable `/run` and `/tmp`, all capabilities dropped, `RuntimeDefault` seccomp.
- Set `runtimeClassName: gvisor`; no ingress, Service, dashboard or homepage entry — Slack uses
  Socket Mode, which is outbound only.
- Wire **Slack** with the existing `automation/mcp-slack-token` app, allowing only the owner's member
  ID.
- Point the model plane at in-cluster LiteLLM through the chart's custom provider support
  (`config.providers.litellm`), model `opencode-go/deepseek-v4.1-flash`.
- Add a NetworkPolicy from the chart: DNS, public HTTPS, and a precise in-cluster exception for
  LiteLLM on port 4000.
- Keep state on a 5 Gi Longhorn PVC, one replica, `Recreate`.

Not changed: LiteLLM, the MCP servers, ArgoCD, the Slack app, and every existing release.

## Capabilities

### New Capabilities

- `hermes-gateway`: how the Hermes gateway is packaged and hardened on this cluster — chart and
  image pinning, gVisor isolation, the restricted security profile, network boundary, credential
  delivery, Slack wiring, model path, probes, and state volume.

### Modified Capabilities

<!-- None. -->

## Impact

- One new release in `releases/automation/`; no image is built or published by us.
- No new secret: `OPENAI_API_KEY` comes from `automation/litellm-auth-credentials`, Slack tokens
  from `automation/mcp-slack-token`, both through `extraEnvFrom`.
- The Slack app must have Socket Mode (verified) and the message events Hermes subscribes to
  (unverified). A dedicated app is the fallback.
- One new entry in `values/_version.yaml` so Renovate tracks the chart.
