# Tasks

- [x] 1.1 Add `github-app-manager-root` and `github-app-coder-root` to
  `datahub-local-secrets`, and the derived `automation/github-app-manager` and
  `automation/github-app-coder` with the env-var key names.
- [x] 1.2 Wire the minter sidecar into `opencode-server` from `github-app-coder`,
  with the egress proxy so the mint call leaves the cluster.
- [x] 1.3 Remove `GITHUB_TOKEN` from the server, add the `gh` wrapper and the bot's
  git identity, and ship `github-proxy.mjs` in the adapter image.
- [x] 1.4 Add the proxy sidecar to the `github-hermes` deployment from
  `github-app-manager`, move the MCP server to loopback, keep the Service on 8080.
- [x] 1.5 Remove the `headers` block and the `mcp-github-token` reference from the
  Hermes config.
- [x] 1.6 Publish the adapter image with `github-proxy.mjs` and the wrapper, and bump
  the digest in `values/_version.yaml`.
- [ ] 1.7 Rollout, then prove inside each pod: the minter answers `/token`, the proxy
  answers `/healthz`, and `gh api user` returns the App bot, not `alvsanand`.
- [ ] 1.8 Open one throwaway issue comment from Hermes and one pull request from the
  coder, and confirm the two bot handles in the timeline.
- [ ] 1.9 Only then, remove `opencode-github` and `mcp-github-token` from the secrets
  repo and the unused ExternalSecret entries in core.
