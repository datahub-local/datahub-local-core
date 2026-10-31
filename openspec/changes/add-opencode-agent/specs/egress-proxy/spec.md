# Spec Delta

## MODIFIED Requirements

### Requirement: The allowlist is a domain list, not a host list

Squid SHALL allow `CONNECT` only to `443` and only to hosts matching the `pypi`, `github`, `npm`,
`helm`, `alpine` or `slack` `dstdomain` ACL, and SHALL deny every other request. The ACLs SHALL
cover exactly `.pypi.org`, `pypi.python.org`, `.pythonhosted.org`, `.github.com`,
`.githubusercontent.com`, `registry.npmjs.org`, `.github.io`, `airflow.apache.org`,
`downloads.apache.org`, `helm.openwebui.com`, `charts.redpanda.com`, `deploy.sympozium.ai`,
`robusta-charts.storage.googleapis.com`, `ghcr.io`, `8gears.container-registry.com`,
`oci.trueforge.org`, `dl-cdn.alpinelinux.org` and `.slack.com`. Port 80, SSH and every other port
SHALL be denied.

#### Scenario: A dependency install succeeds

- **WHEN** `pip install` or `uv pip install` runs inside the agent with `HTTPS_PROXY` set
- **THEN** `pypi.org` and `files.pythonhosted.org` are reachable through the proxy

#### Scenario: A helmfile render resolves its charts

- **WHEN** the agent runs `helmfile template` in a `datahub-local-core` checkout through the proxy
- **THEN** the GitHub Pages, Apache, Redpanda, Sympozium, Open WebUI, Robusta and OCI chart sources
  in the `helm` ACL are reachable
- **AND** a chart repository outside the list is refused

#### Scenario: An unlisted host is refused before a socket opens

- **WHEN** any client sends `CONNECT example.com:443` to the proxy
- **THEN** the proxy answers `403`
- **AND** the access log records `TCP_DENIED/403`
- **AND** no DNS lookup is made for that host

#### Scenario: An IP literal is not an allowlist bypass

- **WHEN** a client sends `CONNECT 1.1.1.1:443` or `GET http://93.184.216.34/`
- **THEN** both are denied, because no `dstdomain` ACL matches a numeric host
