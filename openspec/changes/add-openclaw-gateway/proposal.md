# Proposal

## Why

The hands-on evaluation of OpenClaw on this cluster (2026-10-18) produced a working deployment and a
set of facts that otherwise exist only in that conversation. The upstream `docs/install/kubernetes.md`
ships a minimal kustomize starting point and says so; it does not carry the four things this cluster
needs, and three of them were only found by deploying it:

- the gateway drains for ~315 s on SIGTERM, so the 30 s Kubernetes default SIGKILLs it mid-drain and
  leaves a stale owner lease in the state directory, after which **every** start fails with
  `Another Gateway owner lease is still active`;
- the probes must be `exec`, because the gateway binds loopback and an `httpGet`/`tcpSocket` probe
  against the pod IP can never pass;
- the bundled Chromium needs `browser.noSandbox: true` (`RuntimeDefault` seccomp blocks the user
  namespace Chromium's sandbox needs) and a `/dev/shm` larger than the 64 Mi pod default;
- the image must be pinned to a `-browser` variant on **amd64**: `extended-stable-browser` currently
  resolves to an *older* build than `latest`, the bundled Chromium does not auto-detect on arm64, and
  a build refuses to open a state database written by a newer one.

Separately, the cluster's `gvisor` RuntimeClass cannot be used for the gateway, and the reason is
worth writing down so nobody retries it blindly (see `design.md`).

## What Changes

- Add an `openclaw` release to `releases/automation/`, built on the `app-template` chart this
  repository already uses, with the four fixes above carried in comments where they apply.
- Configure the **Slack** channel (Socket Mode) as the first messaging surface, reusing the
  `slack-root` app credentials already delivered to `automation/mcp-slack-token`.
- Point the model plane at the in-cluster LiteLLM proxy, the same way every other service here does.

Not changed: the LiteLLM proxy, `datahub-local-ai-mcp`, the ArgoCD ApplicationSet, and every existing
release.

## Capabilities

### New Capabilities

- `openclaw-gateway`: how the OpenClaw gateway is packaged and hardened for this cluster — its image
  channel, probe shape, state-directory lifetime, browser requirements, egress policy, and Slack
  channel wiring. New rather than a delta because nothing here deploys it today.

### Modified Capabilities

<!-- None. -->

## Impact

- One new release in `releases/automation/`. It needs a secret named `openclaw-secrets` in
  `automation` (gateway token plus the LiteLLM key); until that exists the pod stays unready. That is
  a `datahub-local-secrets` change, called out in `tasks.md` rather than made here.
- Slack reuses the app whose Socket Mode connection the Slack MCP server already holds. Two
  socket-mode connections for one app is a real conflict, so `design.md` states the options.
