# CLAUDE.md

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
