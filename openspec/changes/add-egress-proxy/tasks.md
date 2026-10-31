# Tasks

## 1. Pins and release

- [x] 1.1 Pin `ubuntu/squid` in `values/_version.yaml` by digest (`latest` is the only stable tag;
  `7.2-26.04` and every other versioned tag 404 on the registry).
- [x] 1.2 Add `{{ .Values.release_name }}-security-egress-proxy` to
  `releases/security/helmfile.yaml.gotmpl` on `bjw-s-labs/app-template` in `security`.
- [x] 1.3 Add `releases/security/values/egress_proxy.yaml.gotmpl`: one controller, one Service on
  3128, one ConfigMap, two NetworkPolicies, `emptyDir` at `/run`, `/var/spool/squid` and `/tmp`.
- [x] 1.4 Render with `helmfile -f releases/security/helmfile.yaml.gotmpl template` and confirm one
  Deployment, one Service, one ConfigMap and two NetworkPolicies, all in `security`, with the image
  by digest.

## 2. Allowlist

- [x] 2.1 Store the allowlist in `releases/security/values/default.yaml.gotmpl` as
  `egress_proxy_domains: {acl: [hosts]}`; generate the `dstdomain` ACL and the `http_access allow`
  line from that map so the two cannot drift.
- [x] 2.2 Keep only the dotted form of each domain. Squid 6.13 fails to start when a bare domain and
  its dotted form share one ACL (`.pypi.org` already covers `pypi.org`).
- [x] 2.3 Deny `0.0.0.0/8`, `10/8`, `127/8`, `169.254/16`, `172.16/12`, `192.168/16` and the IPv6
  private ranges in a `private` ACL, evaluated before the allow rules.
- [x] 2.4 Disable caching (`cache deny all`, `cache_mem 4 MB`) and turn off `forwarded_for` and the
  ICMP pinger (no `NET_RAW` in the Pod).
- [x] 2.5 Verify in a local container under the same restrictions (`--user 13:13`, `--read-only`,
  `--cap-drop ALL`): `pypi.org`, `files.pythonhosted.org`, `github.com`, `api.github.com`,
  `registry.npmjs.org` and `dl-cdn.alpinelinux.org` return 200 through the proxy, while
  `example.com`, `1.1.1.1` and `http://10.0.0.1/` return `TCP_DENIED/403`.

## 3. Policy

- [x] 3.1 Egress NetworkPolicy: DNS to `kube-system`, and `443` to any IPv4 address `except` the
  private ranges, the pod CIDR and loopback.
- [x] 3.2 Ingress NetworkPolicy: 3128 only from the namespace labelled
  `kubernetes.io/metadata.name: automation`.
- [x] 3.3 Pod security: `runAsNonRoot`, uid/gid 13, `fsGroup` 13, `readOnlyRootFilesystem`,
  `allowPrivilegeEscalation: false`, all capabilities dropped, `RuntimeDefault` seccomp.
- [ ] 3.4 Apply and confirm the Pod is admitted, the ConfigMap checksum rolls it on an allowlist
  edit, and the readiness TCP probe passes.

## 4. Verification on the cluster

- [ ] 4.1 From a throwaway Pod in `automation`, `curl -x` the proxy to `pypi.org` and
  `registry.npmjs.org`; both succeed.
- [ ] 4.2 From the same Pod, `curl -x` `https://example.com` and `https://1.1.1.1`; both answer 403.
- [ ] 4.3 From a Pod in `data`, connect to the proxy Service; the connection is dropped, not 403.
- [ ] 4.4 From the `automation` Pod, `curl -x` `https://10.43.0.1:443` and
  `http://169.254.169.254/`; both are denied by the ACL, and the NetworkPolicy denies them too.
- [ ] 4.5 Confirm the access log reaches `kubectl logs` on stdout and no cache directory grows on
  the root filesystem.

## 5. Consumer

- [ ] 5.1 In `add-opencode-agent`: set `HTTPS_PROXY`/`HTTP_PROXY` to
  `http://{{ .Values.release_name }}-security-egress-proxy.security.svc.cluster.local:3128` and
  `NO_PROXY` to the cluster domains on the server container.
- [ ] 5.2 In `add-opencode-agent`: replace the server's public 443 egress with the proxy rule, and
  update the "no egress proxy" residual in its design and spec.

## 6. Hermes

- [x] 6.1 Confirm the chart cannot express "no internet": its template emits either
  `0.0.0.0/0` except RFC1918 or an allow-all, and no value removes the public rule.
- [x] 6.2 Keep `networkPolicy.enabled: true` in `values/hermes.yaml.gotmpl` (ingress stays in
  `extraIngress`) and replace `/spec/egress` with a `jsonPatch` in `values/_kustomize.yaml.gotmpl`,
  wired through `jsonPatches` on the hermes release: DNS, `mcpserver` 8080, LiteLLM 4000, proxy
  3128, and `192.168.31.0/24:443` for dex. No public rule.
- [x] 6.3 Add `HTTP_PROXY`, `HTTPS_PROXY` and `NO_PROXY` (`localhost`, loopback, the pod and Service
  CIDRs, `.svc`, `.svc.cluster.local`, `.homelab.alvsanand.com`) to the container.
- [x] 6.4 Add `.slack.com` to `egress_proxy_domains`; the Slack adapter reads `HTTPS_PROXY` and
  passes it to the Web client and the Socket Mode handler.
- [x] 6.5 Render: one chart-rendered NetworkPolicy whose egress list is the patched one (no
  `0.0.0.0/0`) and whose ingress is unchanged; applies cleanly under `kubectl --dry-run=server`.
- [ ] 6.6 After rollout, confirm Slack reconnects (`wss-primary.slack.com` through the proxy in the
  squid log) and a message round-trips.
- [ ] 6.7 Confirm the dashboard login still works (dex stays direct) and `curl https://example.com`
  from a terminal tool fails with the proxy's `403`.
