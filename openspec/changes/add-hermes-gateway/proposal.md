# Proposal

## Why

OpenClaw was reverted. NanoClaw was then evaluated and live-tested: a Kubernetes session driver was
written against its driver seam and a host → agent Pod → LiteLLM turn completed. It works, but it
costs a fork of a fast-moving project, locally built images with no registry path, and a
single-node RWO volume because host and agent share the session SQLite files. The isolation it buys
is still runc; stronger isolation would mean adding gVisor on top anyway.

Hermes Agent (Nous Research) keeps the OpenClaw shape without the fork: one gateway process, one
Deployment, one state volume, and channels as configuration. It ships an official image, supports
Slack through Socket Mode, has approvals, user allowlists, skills, memory, cron and MCP, and — unlike
OpenClaw — runs under the cluster's existing `gvisor` RuntimeClass. That last point is the security
argument: every command the agent runs stays inside a user-space kernel, not the node's.

The community Helm chart (`ultraworkers/hermes-agent-helm-chart`) describes the deployment we want,
but it is not published anywhere Helm can consume and its pod defaults do not match the image it
targets (see `design.md`). The cluster already has a house harness for this shape: `app-template`,
used by every other automation release — including the one OpenClaw used.

## What Changes

- Add a `hermes` release to `releases/automation/` on `app-template`, mirroring the community
  chart's intent with values this cluster can actually run.
- Run it under `runtimeClassName: gvisor`, with the image's supported root-entrypoint +
  `HERMES_UID`/`HERMES_GID` privilege drop, no service-account token, all capabilities dropped, and
  no inbound surface.
- Wire **Slack** through Socket Mode using the existing `automation/mcp-slack-token` app, with the
  owner's member ID as the only allowed user.
- Point the model plane at in-cluster LiteLLM through its OpenAI-compatible endpoint, using the
  `opencode-go/deepseek-v4.1-flash` alias.
- Add a NetworkPolicy: DNS, LiteLLM, and HTTPS out (Slack). No ingress.
- Keep state on a 5 Gi Longhorn PVC, one replica, `Recreate`.

Not changed: LiteLLM, the MCP servers, ArgoCD, every existing release, and the Slack app itself.

## Capabilities

### New Capabilities

- `hermes-gateway`: how the Hermes gateway is packaged and hardened on this cluster — its image and
  entrypoint contract, gVisor isolation, privilege drop, network boundary, credential delivery,
  Slack wiring, model path, and state volume.

### Modified Capabilities

<!-- None. -->

## Impact

- One new release in `releases/automation/`; no new image is built or published.
- No new secret: `OPENAI_API_KEY` comes from `automation/litellm-auth-credentials`, Slack tokens
  from `automation/mcp-slack-token`.
- The Slack app must already have Socket Mode and the message events Hermes subscribes to. Socket
  Mode is verified; event subscriptions are not, and are called out in `tasks.md` as a check rather
  than an assumption.
- `datahub-local-secrets` is untouched unless a dedicated Hermes Slack app is chosen later.
