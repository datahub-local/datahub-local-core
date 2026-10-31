# Spec Delta

## MODIFIED Requirements

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
surfaces. Public egress SHALL remain allowed for Slack; this is not a network boundary.

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
- **AND** public egress remains allowed for Slack

#### Scenario: MCP is the only in-namespace egress besides LiteLLM

- **WHEN** the agent connects to any other Service in this namespace
- **THEN** the NetworkPolicy denies it
