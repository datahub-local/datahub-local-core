# Proposal

## Why

`add-opencode-agent` leaves the server's 443 egress as "any HTTPS host". The CNI cannot match on
hostname, the agent has `shell`, and `wget` is in the image, so the permission ruleset and the
disabled `webfetch` tool shape quality but not reachability. The only allowed public surface today is
whatever the container happens to call.

The agent still needs three things directly: a Python package index for dependencies, GitHub for git
and for the App token exchange, and its own plugin/git installs. It does not need the open web —
browsing is the self-hosted Firecrawl bridge's job. That split is expressible with one forward proxy
and a domain allowlist.

## What Changes

- Add release `{{ .Values.release_name }}-security-egress-proxy` in `security` on
  `bjw-s-labs/app-template`: one `ubuntu/squid` Deployment on 3128, one Service, one ConfigMap
  holding the allowlist, and two NetworkPolicies.
- Allowlist by destination domain: PyPI (`pypi.org`, `files.pythonhosted.org`, `pypi.python.org`),
  GitHub (`github.com`, its subdomains, `*.githubusercontent.com`), npm
  (`registry.npmjs.org`), Alpine's CDN, and Slack (`*.slack.com` for Hermes' Socket Mode socket,
  Web API and file uploads). Everything else is denied, with no interception: plain `CONNECT`
  tunnels, so no CA is distributed and no certificate is forged.
- Deny cluster addresses, loopback, `169.254.0.0/16` and private ranges twice — in squid's ACLs and
  in the NetworkPolicy `except` list — so a proxy request cannot become an SSRF into the cluster or
  the node metadata endpoint.
- Accept connections only from the `automation` namespace. No other namespace and no ingress
  controller publishes the proxy.
- The proxy is the only Pod with public egress. The agent change is updated to point `HTTP_PROXY`/
  `HTTPS_PROXY` at it and to drop its own 443 rule.
- Hermes in `automation` keeps the chart's NetworkPolicy and replaces its egress list with a
  helmfile `jsonPatch`: DNS, the MCP pods, LiteLLM, the proxy, and dex — no public rule. Slack moves
  behind the proxy, which hermes' adapter already supports through `HTTPS_PROXY`.

Not changed: LiteLLM, Firecrawl, dex, oauth2-proxy, Traefik, the `security` namespace's other
releases, and every other namespace.

## Capabilities

### New Capabilities

- `egress-proxy`: the Squid workload in `security`, its domain allowlist, the NetworkPolicies that
  make it the only public egress path, and the consumer contract the agent uses.

### Modified Capabilities

- `hermes-gateway`: egress becomes DNS, LiteLLM, MCP, the proxy and dex; the chart's policy is
  replaced and Slack moves behind the proxy.

## Impact

- `releases/security/helmfile.yaml.gotmpl`: one new `app-template` release.
- `releases/security/values/default.yaml.gotmpl`: the `egress_proxy_domains` map that both the ACLs
  and the `http_access` rules are generated from.
- `releases/security/values/egress_proxy.yaml.gotmpl`: one Deployment, one Service, one ConfigMap,
  two NetworkPolicies, three `emptyDir` volumes.
- `values/_version.yaml`: `ubuntu/squid` pinned by digest (`latest` is the only stable tag).
- `releases/automation/values/hermes.yaml.gotmpl`: proxy variables added; ingress stays in
  `networkPolicy.extraIngress`.
- `releases/automation/values/_kustomize.yaml.gotmpl` and `helmfile.yaml.gotmpl`: the `jsonPatch`
  that replaces the gateway's egress list, wired through `jsonPatches`.
- No Secret, no PVC, no image build, no DNS change.
- Consumer: `add-opencode-agent` sets `HTTPS_PROXY`/`HTTP_PROXY` on the server and drops its public
  443 egress. No workload in `data` or `media` is affected.
