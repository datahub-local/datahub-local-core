# Design

## Context

Hermes already holds a GitHub MCP server with the `projects` toolset and a token
that carries the `project` scope, and the `opencode` shim exposes seven tools. The
lifecycle this serves is specified in
`datahub-local/openspec/changes/agent-issue-pipeline/`.

## Decisions

### 1 — A script decides, the model narrates

Board status reads, status writes, comment posting and pull-request lookups are
deterministic. Handing them to the model as REST calls invites three failures: a
wrong GraphQL field, a guessed option id, and a status write with no evidence read
first. `taskboard.py` has one subcommand per verb, prints compact JSON, and is the
only thing that talks to the API. The skill tells Hermes when to call which.

### 2 — The marker is the identity, not the author

The Pod's `GITHUB_PERSONAL_ACCESS_TOKEN` is the owner's PAT, so the agent's comments
and Hermes' comments are authored by `alvsanand`. A rule like "an owner comment
after the question resumes the session" would then match Hermes' own comment and
answer itself. Every machine comment therefore ends with a
`<!-- taskboard:... -->` marker, and an owner answer is a comment without one.
`help_state()` is where that rule lives, and `tests/test_taskboard.py` pins it.

### 3 — A ConfigMap mount, not a copy into the volume

`/opt/data` is a Longhorn volume: anything written there once outlives the deploy
that wrote it. Mounting the skill directory read-only over the volume means the
repository is the source, a deploy replaces it, and a `HERMES_HOME` restored from
backup still reads the current rules. The same reason the Slack ack plugin is
mounted this way.

### 4 — Seed the cron job, do not own the file

`jobs.json` holds the owner's other jobs and Hermes rewrites it at runtime. The
init container greps for the job name and creates it only when it is missing, so
the first boot of a fresh volume gets the loop and every later boot is a no-op. A
ConfigMap over `jobs.json` would delete whatever the owner has scheduled since.

`--deliver local` keeps the ten-minute output out of Slack; the skill posts through
the Slack MCP server only when something moved, so an idle tick is silent by
construction rather than by prompt discipline.

### 5 — One dispatch per tick, lowest number first

The shim is serial: an active session, including one waiting on a question, makes
`run_task` return `busy`. Dispatching several issues in one tick would produce
`busy` on all but the first. One dispatch per tick, and the queue is reported once
rather than every ten minutes.

### 6 — Failures do not look like questions

A transport error leaves the status alone and is reported on the issue. Only a
session that actually asked something sets `Blocked`. The distinction matters
because `Blocked` is the owner's queue: a false positive puts an outage in the same
list as work waiting on a decision.

## Residuals

- Zero cost when idle is not claimed: the tick is a model run every ten minutes,
  even when it answers `idle`. A monitor script over the board could suppress the
  run entirely; that is a follow-up, and it needs its own quiet signal.
- Review comments on a pull request do not reach the agent automatically. The
  `run_task(session_id=...)` path exists; the trigger is a follow-up.
