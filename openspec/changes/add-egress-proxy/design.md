# Design

## Context

The cluster enforces L3/L4 only, so "the agent may reach these sites" cannot be a NetworkPolicy.
The agent runs in `automation` with `shell`, a working `wget`, and an upstream `git`; the only thing
currently bounding it is the credential set. `add-opencode-agent` documents that as a residual.

The owner's split is: package dependencies come from a registry, browsing comes from the self-hosted
Firecrawl bridge, nothing else is reachable.

## Decisions

### 1 — Squid, because the problem is a forward proxy

A reverse proxy is the wrong shape; Traefik has no forward-proxy `CONNECT` at all. Among forward
proxies:

| Option | Verdict |
|---|---|
| Squid | one `dstdomain` ACL per site, `CONNECT` allowed only to matched hostnames, battle-tested, logs each request |
| Envoy | works (`sni_cluster` or a CONNECT tunnel with RBAC on `:authority`), but far more config for the same allowlist, and nothing else here runs Envoy |
| tinyproxy | same idea via a filter file, weaker ACLs, no useful access log |
| mitmproxy | would give path-level rules, at the cost of a CA in every container; not needed for an allowlist |

Squid is one 128Mi Pod and a text file. `ubuntu/squid` is the maintained image; it publishes no
stable version tag, so the pin is `latest@sha256:6a097f68…` like the other latest-only images in
`values/_version.yaml`.

### 2 — Domain allowlist, no TLS interception

The ACL is `dstdomain`, so `CONNECT pypi.org:443` is tunnelled untouched and a host absent from the
list is answered `403` before any socket opens. No CA, no forged certificate, no client changes
beyond `HTTPS_PROXY`.

Two Squid behaviours were measured against the pinned image (6.13) and shape the config:

- `.pypi.org` already covers `pypi.org`; listing both is a **fatal** config error
  (`'.pypi.org' is a subdomain of 'pypi.org'`). The file keeps only the dotted form.
- A `CONNECT` to a bare IP address never matches a `dstdomain` ACL, so `https://1.1.1.1` is denied
  without a separate numeric-IP rule.

### 3 — The allowlist is the five things the agent actually runs

| ACL | Hosts | Used by |
|---|---|---|
| `pypi` | `.pypi.org`, `pypi.python.org`, `.pythonhosted.org` | `pip`, `uv` |
| `github` | `.github.com`, `.githubusercontent.com` | git clone/push, App token exchange, release assets |
| `npm` | `registry.npmjs.org` | the OpenCode LiteLLM plugin installed at startup |
| `alpine` | `dl-cdn.alpinelinux.org` | the `apk` init container that installs git |
| `slack` | `.slack.com` | Hermes' Socket Mode socket, Web API and file uploads |

Only TCP 443 is allowed; plain HTTP, SSH (22) and every other port are denied, so git must use its
HTTPS remote.

Firecrawl needs no rule: the bridge is in `automation` and the agent reaches it over the cluster
network, not through the proxy. Slack is the one browser-side service: hermes resolves `HTTPS_PROXY`
itself and passes it to both the `AsyncWebClient` and the `SocketModeHandler`, so `.slack.com`
tunnels through the same path as everything else.

Adding a host is one list entry under `egress_proxy_domains` in
`releases/security/values/default.yaml.gotmpl`; the ACL and `http_access` lines in `squid.conf` are
generated from that map, so the two halves cannot drift. The chart puts a checksum of the ConfigMap
on the Pod template, so the edit rolls the proxy; no manual restart.

### 4 — Enforcement is two-part, and the proxy alone is not enough

Squid can only be the boundary if it is the only workload that may open a public socket:

- Proxy NetworkPolicy: egress to any IPv4 `443`, `except` the private ranges, the pod CIDR, loopback
  and `169.254.0.0/16`; DNS to `kube-system` only.
- Consumer (in `add-opencode-agent`): `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` on the server and an
  egress policy that drops its public `443` rule, keeping DNS, LiteLLM, the Firecrawl bridge and the
  proxy. Clients that ignore the variables then fail instead of leaking.

`NO_PROXY` must cover `data.svc`, `automation.svc` and the cluster suffix, or LiteLLM and Firecrawl
calls would be sent to a proxy that denies private destinations.

### 5 — Private destinations are denied twice

Squid's `private` ACL and the NetworkPolicy `except` list cover the same ranges on purpose. The ACL
survives a policy edit; the policy survives a config typo. Either one alone stops
`CONNECT 10.43.x.x:443` from reaching the API server or another Service.

### 6 — Nothing is cached

Responses crossing this proxy include GitHub installation tokens, private repository objects and
wheels. `cache deny all` and a 4 MB memory cap make the process unable to serve a stale or another
tenant's object, and keep it inside the 128Mi limit.

### 7 — Hermes' own chart cannot say "no internet", so the egress list is patched

The hermes-agent chart renders its NetworkPolicy from a template with a single switch:
`blockPrivateEgress: true` emits `0.0.0.0/0` except the private ranges (all public HTTPS allowed),
and `false` emits an allow-all. There is no "deny public" variant, and NetworkPolicies are additive,
so a second policy cannot subtract a rule.

The chart's policy stays enabled — it owns the name, labels, selector and both policy types — and the
release's `jsonPatches` entry in `values/_kustomize.yaml.gotmpl` replaces the whole `/spec/egress`
list, which is the repo's rule for a chart-rendered resource its values cannot express:

- Egress: DNS, the `mcpserver` pods on 8080, LiteLLM on 4000, the proxy on 3128, and
  `192.168.31.0/24` on 443 for dex (Traefik is hostNetwork, so the issuer host is a node address).
- Ingress: stays in `extraIngress` — the dashboard on 9119 from Traefik's node network and the pod
  CIDR.

`replace` is used rather than a strategic merge because a list merge would keep the public rule
alongside the new ones.

Hermes already understands proxies: `resolve_proxy_url()` reads `HTTPS_PROXY` under
`gateway.trust_env` (default true), the Slack adapter applies it to the Web client and the Socket
Mode handler, and `NO_PROXY` is matched with apex-plus-subdomain and CIDR rules. So `NO_PROXY` lists
the cluster suffixes and the gateway domain, and Slack tunnels.

### 8 — Slack stays a dependency, not a hole

Slack is not a browsing surface; Socket Mode is the gateway's inbound channel over an outbound
socket, so denying it would leave Hermes reachable only through the dashboard. Allowlisting
`.slack.com` keeps one host group open on 443, and the bot token still bounds what the gateway can do
there. The adapter logs a warning when `NO_PROXY` covers the Slack hosts and falls back to direct
egress, which the policy now refuses — the failure is visible instead of silent.

## Residuals

- The proxy itself may open a socket to any public address on 443; the allowlist lives in its config,
  not in the kernel. A compromised proxy process is the boundary failure mode, which is why it runs
  non-root, read-only, with all capabilities dropped, and is the only Pod in `security` with that
  egress.
- An allowlisted domain is allowlisted for every path. `github.com` can host arbitrary content, so
  this is a host boundary, not a content boundary; path- or payload-level control needs TLS
  interception and is out of scope.
- Squid is a single replica. A rollout drops in-flight tunnels; a client retries. It is not a
  throughput path.
- The Pod reaches DNS through `kube-system`, so a poisoned cluster DNS can still answer a public
  name with a private address — prevented by the `private` ACL and the `except` list, not by a
  pinned resolver.
