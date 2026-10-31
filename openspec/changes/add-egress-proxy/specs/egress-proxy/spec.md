# Spec Delta

## Purpose

`security` runs the cluster's only forward proxy: a Squid allowlist that lets the automation
workloads reach the package registries, GitHub and Slack they need, and nothing else. Everything
else is either in-cluster or denied, and browsing is the Firecrawl bridge's job.

## ADDED Requirements

### Requirement: The proxy is one release in `security` and the only public egress

The release `{{ .Values.release_name }}-security-egress-proxy` SHALL be rendered by
`bjw-s-labs/app-template` in the `security` namespace and SHALL contain exactly one Deployment, one
Service on 3128, one ConfigMap carrying `squid.conf`, and two NetworkPolicies. The container SHALL
run as non-root with a read-only root filesystem and all capabilities dropped, and SHALL mount
`emptyDir` volumes at `/run`, `/var/spool/squid` and `/tmp`. The image SHALL be pinned by digest in
`values/_version.yaml`.

#### Scenario: The render is self-contained

- **WHEN** the release is rendered
- **THEN** the output contains one Deployment, one Service, one ConfigMap and two NetworkPolicies
- **AND** no PVC, Secret, IngressRoute or ingress controller object is created
- **AND** the image reference carries a `sha256` digest

#### Scenario: No other workload keeps public egress

- **WHEN** the egress policies of the `automation` and `security` namespaces are listed
- **THEN** the proxy Pod is the only workload with an egress rule to a public address
- **AND** the agent workload's public 443 rule is replaced by the proxy rule described in
  `add-opencode-agent`

### Requirement: The allowlist is a domain list, not a host list

Squid SHALL allow `CONNECT` only to `443` and only to hosts matching the `pypi`, `github`, `npm`, `alpine` or `slack`
`dstdomain` ACL, and SHALL deny every other request. The ACLs SHALL cover exactly
`.pypi.org`, `pypi.python.org`, `.pythonhosted.org`, `.github.com`, `.githubusercontent.com`,
`registry.npmjs.org`, `dl-cdn.alpinelinux.org` and `.slack.com`. Port 80, SSH and every other port
SHALL be denied.

#### Scenario: A dependency install succeeds

- **WHEN** `pip install` or `uv pip install` runs inside the agent with `HTTPS_PROXY` set
- **THEN** `pypi.org` and `files.pythonhosted.org` are reachable through the proxy

#### Scenario: An unlisted host is refused before a socket opens

- **WHEN** any client sends `CONNECT example.com:443` to the proxy
- **THEN** the proxy answers `403`
- **AND** the access log records `TCP_DENIED/403`
- **AND** no DNS lookup is made for that host

#### Scenario: An IP literal is not an allowlist bypass

- **WHEN** a client sends `CONNECT 1.1.1.1:443` or `GET http://93.184.216.34/`
- **THEN** both are denied, because no `dstdomain` ACL matches a numeric host

### Requirement: Private and cluster destinations are unreachable through the proxy

The proxy SHALL deny destinations in `0.0.0.0/8`, `10.0.0.0/8`, `127.0.0.0/8`,
`169.254.0.0/16`, `172.16.0.0/12`, `192.168.0.0/16`, `::1/128`, `fc00::/7` and `fe80::/10`, even
when the hostname matches an allowlist ACL. Its NetworkPolicy SHALL allow egress to `443` only
`except` those same ranges.

#### Scenario: The agent cannot proxy into the cluster

- **WHEN** the agent sends `CONNECT <any Service IP>:443` or `http://10.42.0.1/` to the proxy
- **THEN** the proxy answers `403` and the connection is not attempted

#### Scenario: The metadata endpoint stays blocked

- **WHEN** a request targets `169.254.169.254`
- **THEN** both the ACL and the NetworkPolicy deny it

### Requirement: Only the `automation` namespace may use the proxy

The proxy's ingress NetworkPolicy SHALL accept port 3128 only from Pods in the namespace labelled
`kubernetes.io/metadata.name: automation`. No IngressRoute SHALL publish the proxy, and no Service
SHALL expose it outside the cluster.

#### Scenario: Another namespace is refused

- **WHEN** a Pod in `data` or `media` connects to the proxy Service
- **THEN** the connection is dropped before reaching squid

#### Scenario: The UI is not on the proxy

- **WHEN** the gateway hostnames are resolved
- **THEN** no IngressRoute points at the proxy Service

### Requirement: Traffic is tunnelled, not intercepted

The proxy SHALL NOT terminate TLS. No CA certificate SHALL be installed in the agent or the proxy,
and no certificate SHALL be forged.

#### Scenario: The upstream certificate is the one the client sees

- **WHEN** a client fetches `https://pypi.org/simple/` through the proxy
- **THEN** the TLS chain is the upstream chain
- **AND** the proxy log records the tunnel, not the request body

### Requirement: The agent consumes the proxy and keeps no direct public path

The server workload SHALL set `HTTP_PROXY` and `HTTPS_PROXY` to the proxy Service on 3128 and a
`NO_PROXY` covering `data.svc`, `automation.svc` and the cluster suffix. Its NetworkPolicy egress
SHALL allow only DNS, LiteLLM on 4000, the Firecrawl bridge on 8080 and the proxy on 3128.

#### Scenario: A tool that ignores the variables fails closed

- **WHEN** a binary in the agent connects directly to a public address on 443
- **THEN** the NetworkPolicy denies it
- **AND** the same request succeeds when sent through the proxy

#### Scenario: In-cluster calls bypass the proxy

- **WHEN** the agent calls LiteLLM or the Firecrawl bridge
- **THEN** the request goes direct, because both are listed in `NO_PROXY`
- **AND** the proxy log shows no entry for them

### Requirement: Hermes reaches the internet only through the proxy

The gateway in `automation` SHALL keep the chart's NetworkPolicy (it owns the name, selector and
policy types) and SHALL have its `/spec/egress` list replaced by a `jsonPatch` in
`releases/automation/values/_kustomize.yaml.gotmpl`, wired through the release's `jsonPatches`, and
SHALL set `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` on its container. Its egress SHALL be DNS, the MCP
pods on 8080, LiteLLM on 4000, the proxy on 3128, and `192.168.31.0/24` on 443 for dex. Slack SHALL
be tunnelled through the proxy, because the adapter reads the proxy variables and passes them to the
Web API client and the Socket Mode handler.

#### Scenario: Slack keeps working without direct egress

- **WHEN** the gateway opens its Socket Mode connection after the policy change
- **THEN** the socket is tunnelled through the proxy and the allowlist admits `.slack.com`
- **AND** a direct `wss-primary.slack.com:443` connection is denied by the policy

#### Scenario: The agent cannot browse

- **WHEN** a terminal tool in the gateway fetches `https://example.com`
- **THEN** the proxy answers `403` and the policy has no direct rule to fall back on
