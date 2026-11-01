# Tasks

- [x] 1.1 Add `releases/automation/files/agent/taskboard-loop/taskboard.py`: the
  `ready`, `issue`, `status`, `comment`, `start`, `pr` and `review` subcommands,
  one marker per machine comment.
- [x] 1.2 Add `releases/automation/files/agent/taskboard-loop/SKILL.md`: the tick
  procedure, the help loop, the review handoff, and what the tick never does.
- [x] 1.3 Render both into the `hermes-taskboard-loop` ConfigMap from the umbrella
  release.
- [x] 1.4 Mount the ConfigMap read-only at
  `/opt/data/skills/devops/taskboard-loop` in `values/hermes.yaml.gotmpl`.
- [x] 1.5 Add the `cron-seed` init container: create `taskboard-tick` only when it
  is absent, `--skill taskboard-loop`, `--deliver local`.
- [x] 1.6 Add `tests/test_taskboard.py` for `pick_ready`, `last_session` and
  `help_state`, and run it.
- [x] 1.7 `helmfile template` renders the ConfigMap, the mount and the init
  container, with no change to the existing init containers.
- [x] 1.7b The live volume predates `mcp_servers.opencode` (the chart seeds
  `config.yaml` only when absent), so the key was written with `hermes config set`
  and `hermes mcp test opencode` now reports seven tools. Values already carry it,
  so a fresh volume gets it without that step.
- [x] 1.9c Add `inbox` and `forwarded` to `taskboard.py`: one queue for issue
  comments and pull-request review comments, de-duplicated by a marker.
- [ ] 1.9b Confirm a `BLOCKED` report sets `Blocked` rather than "branch without a
  pull request", and that an owner answer relayed from Slack is forwarded.
- [ ] 1.8 After the rollout, `hermes cron list` shows `taskboard-tick`, `hermes
  skills` lists `taskboard-loop`, and one manual `hermes cron run taskboard-tick`
  answers `idle` with nothing ready.
- [ ] 1.9 With the default limit, one tick dispatches one issue and stops on the
  next `busy` without commenting.
- [ ] 1.10 Move issue #116 to `Ready` and confirm one tick starts it, sets
  `In Progress`, and records the session on the issue.
