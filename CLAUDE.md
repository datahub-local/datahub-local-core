# CLAUDE.md

## Git commits

Governed by the global rule in `~/.claude/CLAUDE.md`: **never commit unless asked
directly**, and suggest one short subject line instead. The local convention it
points at is below.

## Git commit messages

Angular / Conventional Commits, and **short** — a subject line and nothing else.

```
<type>(<scope>): <subject>
```

- **type** — one of `feat`, `fix`, `chore`, `refactor`, `docs`. `chore(deps)` is
  Renovate's; do not write it by hand.
- **scope** — the service, named as its values file is: `sympozium`, `n8n`,
  `trino`, `ollama`, `airflow`, `polaris`, `superset`, `cloudnative-pg-cluster`,
  `monitoring`. Use the namespace (`data`, `media`, `automation`) only for a
  change that spans it, and drop the scope entirely for a repo-wide one.
- **subject** — imperative mood, lowercase, no trailing period. Aim for 50-70
  characters; hard limit 72. Say what the change does, not which files moved.

```
fix(sympozium): disable auth in NATS
feat(monitoring): surface n8n failures on the dashboard
fix(superset): point async query backends at valkey
```

### No body by default

Six of the last three hundred commits have a body. Rationale belongs in a comment
next to the code it explains, where the next reader will actually find it — not in
a message they would have to go looking for. Write a body only for something the
diff cannot carry: a breaking change, a required manual step, or a dependency on
another repo. Keep it to a line or two when you do.

Do not restate the diff, enumerate every touched file, or explain the reasoning
behind each decision. That is what the review conversation is for.

## Patching upstream charts

When a chart-rendered resource needs a change its values cannot express, patch it
with helmfile instead of adding a standalone template:

- Put the patch under `.Values.kustomize.<release>` in
  `releases/<namespace>/values/_kustomize.yaml.gotmpl`, next to that release's
  other overrides.
- Wire it into the release in `releases/<namespace>/helmfile.yaml.gotmpl` with
  `strategicMergePatches` (whole fields) or `jsonPatches` (a value a merge cannot
  replace, such as a matched service port), each through `toYaml`.
- Leave `metadata.namespace` off the patch target. Chart output carries no
  namespace, and a namespaced target fails to match with `no resource matches
  strategic merge patch`.

Only add a file under `releases/<namespace>/templates/` for a resource the chart
does not render at all.

## Prometheus rules are not validated by a render

`prometheus_rules` in `releases/monitoring/values/default.yaml.gotmpl` is a list
of raw PromQL strings, so `helmfile template` and `--dry-run=server` both accept an
expression the engine cannot parse. The operator then rejects the **whole**
PrometheusRule with `invalid rule`, logs it at `level=warn` and emits a
`Warning/InvalidConfiguration` event — and nothing else fails. `helmfile template`
passes, ArgoCD reports Synced and Healthy, and the rule is simply never evaluated.

Check every new or edited expression with the `promtool` that ships in the running
Prometheus before committing:

```bash
kubectl -n monitoring exec -i prometheus-datahub-local-core-kube-pr-prometheus-0 \
  -c prometheus -- promtool check rules /dev/stdin <<'EOF'
groups:
  - name: <group>
    rules:
      - alert: <AlertName>
        expr: |
          <the expression>
EOF
```

One trap this caught on 2026-09-13: an `offset` binds to the vector selector it
follows, not to the comparison, so
`sympozium_agentrun_info{phase="Failed"} == 1 offset 1h` does not parse. Write the
`offset` on the selector — `sympozium_agentrun_info{phase="Failed"} offset 1h == 1`.
Confirm a fix landed by reading
`kubectl -n monitoring logs deploy/datahub-local-core-kube-pr-operator | grep 'invalid rule'`,
not by the render or the ArgoCD sync state.

## Raising an alert's severity changes which channel it lands in

Robusta has **no MEDIUM**: `SEVERITY_MAP` in its `integrations/prometheus/models.py`
sends `error`, `medium`, `high` and `critical` all to `FindingSeverity.HIGH`, and
the enum itself only has DEBUG, INFO, LOW and HIGH (🔵 ⚪️ 🟡 🔴). A `warning`
alert is LOW. So `severity: error` renders as 🔴 **High**, and asking for a middle
tier means changing Robusta, not the label.

The consequence is routing, not cosmetics. The first sink in
`releases/monitoring/values/robusta.yaml.gotmpl` includes `severity: HIGH`, so
raising any alert to `error` or above adds it to that channel on top of wherever
else it was going. Give the alert family an `exclude` on that sink when it belongs
somewhere specific; `exclude` is evaluated before `include` and wins.

Read the mapping off the running image rather than the docs:

```bash
kubectl -n monitoring exec deploy/datahub-local-core-robusta-runner -c runner -- \
  grep -A 10 'SEVERITY_MAP' /app/src/robusta/integrations/prometheus/models.py
```

## An event alert must not notify on resolve

An alert whose expression carves out a window — `X unless X offset 1h`, the shape
the Sympozium run alerts use — stops firing when the window closes, not when
anything recovered. Alertmanager then sends a resolved webhook and Robusta posts
"resolved" an hour later, which reads as the failed run having fixed itself.

The fix is a second receiver on the same webhook URL with `send_resolved: false`
and a route matching that alert family, placed **before** the catch-all route and
without `continue`, since that route carries `continue: true` and would otherwise
send a second copy through the receiver that does notify. Verify the routing, and
never by reading it:

```bash
kubectl -n monitoring exec -i alertmanager-datahub-local-core-kube-pr-alertmanager-0 \
  -c alertmanager -- amtool config routes test --config.file=/dev/stdin \
  alertname=SympoziumAgentRunFailed severity=error < am.yaml
```

## kube-state-metrics drops an Info metric whose labels all fail to resolve

`addPathLabels` skips a label whose path resolves to nil, and `compiledInfo.values`
emits nothing when that leaves no labels at all (v2.20.0). That is a feature worth
using: a metric declaring only `error: [status, error]` exists for failed
AgentRuns and for nothing else, which is why the error text does not have to ride
on `sympozium_agentrun_info` and sit on every run's series. Resource-level
`labelsFromPath` is added afterwards and does not keep the metric alive.

A Gauge behaves differently — a missing path logs
`got nil while resolving path` at `registry_factory.go:719` and emits nothing.
Those lines are normal for the token-usage gauges of a run that never reached the
model; they are not an error to chase.
