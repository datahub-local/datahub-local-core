# Proposal

## Why

The agent and the board are wired but nothing polls one to feed the other. An issue
sits in `Ready` until a human tells Hermes to pick it up in Slack, the status never
changes on its own, and the answer to a question the agent asked exists only in
Slack. The missing piece is small and entirely on the Hermes side: read the board,
start the session, move the card, report.

It is also the piece most likely to rot if it lives in a chat log. Hermes keeps
scheduled jobs in `HERMES_HOME/cron/jobs.json` on a Longhorn volume and skills in
`HERMES_HOME/skills`, so a job created by hand survives a reinstall of everything
else and drifts from the repository. This change puts both in git.

## What Changes

- A Hermes skill, `taskboard-loop`, shipped as a ConfigMap from
  `releases/automation/files/agent/taskboard-loop/` and mounted read-only at
  `/opt/data/skills/devops/taskboard-loop`.
- `taskboard.py` beside it: every board read, board write, comment, session marker
  and pull-request lookup as one subcommand, so the model judges over facts instead
  of composing GraphQL. Owner answers are recognised by the absence of a
  `<!-- taskboard: -->` marker, because the PAT makes the owner the author of every
  machine comment too.
- A `gateway:startup` hook that creates the `taskboard-tick` job (every 10 minutes,
  `--skill taskboard-loop`, `--deliver local`) only when it is absent, so a fresh or
  restored volume is provisioned, the owner's other jobs are left alone, and no
  extra container is needed.
- `--deliver local` on purpose: the job speaks in Slack through the Slack MCP
  server only when something moved, so an idle tick is silent.

Not changed: the Hermes chart, its model, its other MCP servers, the opencode
release, and the board's own automations.

## Impact

- `releases/automation/templates/hermes_taskboard_loop.yaml`: one ConfigMap.
- `releases/automation/values/hermes.yaml.gotmpl`: one volume, one mount, one init
  container.
- `releases/automation/files/agent/taskboard-loop/{SKILL.md,taskboard.py}`.
- `tests/test_taskboard.py`: the three decisions the tick makes, pinned.
- One Hermes rollout. The Pod restarts; its volume, sessions and other jobs are
  untouched.
