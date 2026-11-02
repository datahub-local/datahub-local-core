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
- [x] 1.5 Add a `gateway:startup` hook (`HOOK.yaml` + `handler.py`) that creates
  `taskboard-tick` only when `jobs.json` lacks it, `--skill taskboard-loop`,
  `--deliver local`, and logs rather than raising. Verified in the live Hermes pod
  against a scratch `HERMES_HOME`: created once, a second run left one job.
- [x] 1.6 Add `tests/test_taskboard.py` for `pick_ready`, `last_session` and
  `help_state`, and run it.
- [x] 1.7 `helmfile template` renders the ConfigMap, the skill mount and the hook
  mount, with the `cron-seed` init container removed.
- [x] 1.7b The live volume predates `mcp_servers.opencode` (the chart seeds
  `config.yaml` only when absent), so the key was written with `hermes config set`
  and `hermes mcp test opencode` now reports seven tools. Values already carry it,
  so a fresh volume gets it without that step.
- [x] 1.9c Add `inbox` and `forwarded` to `taskboard.py`: one queue for issue
  comments and pull-request review comments, de-duplicated by a marker.
- [ ] 1.9b Confirm a `BLOCKED` report sets `Blocked` rather than "branch without a
  pull request", and that an owner answer relayed from Slack is forwarded.
  `Blocked` is confirmed: #122 moved there with the question commented and the ping
  sent. The relay half is deferred: 1.9e is fixed, but no owner answer has arrived
  through Slack since, so the path is unexercised (design, Residuals).
- [x] 1.9d Review fixes: `board` as the tick's work list, `comment --owner` for a
  relayed answer, resume respecting the checkout rule, the retained PR-mention
  requirement rewritten, the agent no longer closing issues, and the skill's
  no-report-on-busy rule.
- [x] 1.8 After the rollout, `hermes cron list` shows `taskboard-tick`, `hermes
  skills list` shows `taskboard-loop`, and `taskboard.py ready` answers `[]`, so a
  tick has nothing to dispatch. Verified in the Pod 2026-11-02.
- [x] 1.9 With the default limit, one tick dispatches one issue and stops on the
  next `busy` without commenting.
- [x] 1.11 Confirm the dispatch no longer holds the tick: `wait_seconds: 10`, the
  session recorded, the tick ends, and the next tick polls it.
- [x] 1.10 Move #121 to `Ready` and confirm one tick starts it, sets
  `In Progress`, and records the session on the issue. (#116 was closed before this
  ran, so the loop took #121, the first dispatchable issue after it.)
- [x] 1.9e Fix the help ping's destination. The tick posted it to `#workflows`
  (`C08RQNXQV3P`), which Hermes does not read. The skill now names
  `$SLACK_HOME_CHANNEL`, and the `Homelab` app (`B08SHC075UY`) is a member of
  `#agentic-coding` (`C0CDNTM4GTH`), the home channel Hermes reads; verified with
  `conversations.members` and `users.info` on 2026-11-02.
- [x] 1.9h Replace the heredoc `comment` instructions: cron refuses a heredoc as a
  dangerous command, so the helper takes `--text` and both skills pass the body on
  argv. `tests/test_taskboard.py` pins the two paths.
- [x] 1.9f Add `taskboard.py finish <n>`, which refuses `Done` while the issue is
  open. The tick moved #117 to `Done` on three merged pull requests that merely
  reference it, and the card had to be moved back to `Testing` by hand.
- [x] 1.9g Post the tick's Slack lines with Hermes' own bot token instead of
  `mcp__sympozium_slack__slack_post_message`, which authors them as the `@homelab`
  app. Verified from the Pod: `chat.postMessage` with `$SLACK_BOT_TOKEN` answers
  `ok: true` and `bot_profile.name: Hermes`.

## Record

The first live run, 2026-11-02, against two throwaway issues in `datahub-local`.

- #121 was dispatched, moved to `In Progress`, claimed by the coder, which opened PR
  #123; the next tick moved it to `Testing`, requested review and posted one Slack
  line.
- #122 was dispatched on a later tick, the agent stopped to ask which H1 to use, the
  card went to `Blocked`, the question was commented with the help marker, and the
  ping went to Slack. The answer, written on the issue, was forwarded and marked, the
  card returned to `In Progress`, PR #124 opened, then `Testing`.
- A tick with one dispatch took 59s, and a dispatch plus a transition 95s, so the
  ten-second wait does not hold the scheduler.
- Defect: the help ping went to `#workflows`, which Hermes cannot read, and the
  sending app cannot join `#agent-hermes`. The skill now names `$SLACK_HOME_CHANNEL`;
  the membership is still missing.
- Defect: the #121 summary claimed the PR changed `docs/services/automation.md` too
  (+24 −0). PR #123 touches only `docs/services/core.md`, so the coder's workspace
  holds something the pull request does not, and the changed-files line can
  over-report.
- Defect: `review` logged a 404 from `POST .../requested_reviewers` while the review
  request did land. It reads as a retry against an already-requested reviewer.
- Defect: both skills fed `comment` through a quoted heredoc, which cron refuses
  (`dangerous (script execution via heredoc)`), so a tick had no working documented
  way to post a comment. Fixed with `--text` on the helper and the instructions.
- The home channel is `#agentic-coding`; the `Homelab` app is a member, so the help
  ping can be answered there. That relay has not been exercised end to end.
