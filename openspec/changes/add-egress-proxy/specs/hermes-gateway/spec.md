# Spec Delta

## RENAMED Requirements

- FROM: ### Requirement: Egress is limited to DNS, LiteLLM, and HTTPS
- TO: ### Requirement: Egress is DNS, LiteLLM, MCP, the egress proxy, and dex

## MODIFIED Requirements

### Requirement: Egress is DNS, LiteLLM, MCP, the egress proxy, and dex

The chart's NetworkPolicy SHALL stay enabled and its `/spec/egress` list SHALL be replaced by a
`jsonPatch` in `releases/automation/values/_kustomize.yaml.gotmpl`, because the chart template always
emits either `0.0.0.0/0` except RFC1918 or an allow-all and has no "no internet" switch; a strategic
merge would keep the public rule, so the patch replaces the list.

Egress SHALL allow DNS to `kube-system`'s kube-dns, the `app.kubernetes.io/name: mcpserver` pods on
8080, LiteLLM on 4000, the `security` egress proxy on 3128, and `192.168.31.0/24` on 443. That last
rule is dex: the dashboard's OIDC issuer is published through Traefik, which runs hostNetwork, so
the issuer hostname resolves to an RFC1918 node address that no Service selector can match.
No rule SHALL allow a general public address. Ingress SHALL stay limited to the dashboard listener
on 9119 from Traefik's node network and the pod CIDR.

The gateway SHALL set `HTTP_PROXY` and `HTTPS_PROXY` to the proxy Service and `NO_PROXY` to the
cluster and gateway-host suffix, so LiteLLM, the MCP pods, the API server and dex bypass the proxy
while Slack, GitHub and PyPI go through it.

#### Scenario: There is no direct path to the internet

- **WHEN** the gateway or a tool in it opens a socket to a public address without the proxy
- **THEN** the NetworkPolicy denies it
- **AND** the same request through `HTTPS_PROXY` succeeds only when the proxy's allowlist matches

#### Scenario: The Kubernetes API is unreachable from the agent

- **WHEN** the gateway tries to reach the API server or another private address outside the allowed
  set
- **THEN** the connection is denied

#### Scenario: LiteLLM is reachable

- **WHEN** the gateway calls the in-cluster LiteLLM Service on port 4000
- **THEN** the connection is allowed by the policy and bypasses the proxy

#### Scenario: The OIDC issuer is reachable

- **WHEN** the dashboard starts a login and fetches dex's discovery document
- **THEN** the request to the issuer hostname is allowed by the policy

### Requirement: MCP tools are the namespace's own Sympozium servers

`config.mcp_servers` SHALL register the namespace's Sympozium MCP servers as HTTP MCP endpoints on
port 8080, and the NetworkPolicy SHALL allow egress to the `app.kubernetes.io/name: mcpserver` pods
on that port. Seven of them are the shared `…-mcp-*` Services the Sympozium agents already
use; their stdio bridge speaks MCP over HTTP and needs no credential the Deployments do not already
mount. The `slack` entry is a tool surface on top of the built-in channel, which keeps its own Socket
Mode connection.

The seventh, `sympozium-firecrawl`, SHALL point at a dedicated
`…-mcp-firecrawl-http` Service running `ghcr.io/firecrawl/firecrawl-mcp-server` in its own
stateless HTTP mode, which proxies the self-hosted Firecrawl API in `data`. It SHALL expose only the
scrape, search and map tools through the server's `tools.include` filter, and SHALL need no Firecrawl
account key. Like `sympozium-github`, it SHALL bypass the stdio bridge, because the bridge forwards
each client's `initialize` to one long-lived child and misroutes this server's replies. The gateway
SHALL disable the native `web` and `browser` toolsets on every platform through
`config.agent.disabled_toolsets`, so those tools are not offered on Slack, CLI, dashboard or cron
surfaces. Slack SHALL be reached through the egress proxy, whose allowlist carries `.slack.com`;
there SHALL be no direct public rule for it.

`sympozium-github` SHALL instead point at a dedicated `…-mcp-github-hermes` Service running
the upstream server in its `http` mode, because the bridge re-sends `initialize` to a long-lived
child and `github-mcp-server` v2 rejects the duplicate. That
instance SHALL authenticate with `Authorization: Bearer` resolved from `GITHUB_PERSONAL_ACCESS_TOKEN`
at gateway start, never from a literal in `config.yaml`, SHALL exclude the tools the catalog server
denies (`create_repository`, `fork_repository`, `delete_repository`, `delete_file`,
`merge_pull_request`), and SHALL stay out of Sympozium's MCPServer catalog so its agents keep their
own stdio instance.

#### Scenario: The agent discovers the namespace's tools

- **WHEN** the gateway enumerates MCP tools
- **THEN** every registered server completes the MCP handshake and reports its tools

#### Scenario: github uses its own transport

- **WHEN** the gateway connects to `sympozium-github`
- **THEN** it reaches the dedicated HTTP instance rather than the shared stdio bridge
- **AND** the request carries the token from the Pod environment

#### Scenario: Firecrawl is reachable through the bridge

- **WHEN** the gateway connects to `sympozium-firecrawl`
- **THEN** it reaches the bridge in its own namespace on 8080
- **AND** a scrape returns page markdown from the self-hosted API in `data`

#### Scenario: Firecrawl replaces the native web tools

- **WHEN** the gateway's tool list is read for any platform
- **THEN** `web` and `browser` are absent
- **AND** only the three included Firecrawl tools are registered from `sympozium-firecrawl`
- **AND** Slack still receives events, through the egress proxy

#### Scenario: MCP is the only in-namespace egress besides LiteLLM

- **WHEN** the agent connects to any other Service in this namespace
- **THEN** the NetworkPolicy denies it
