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

### 4 — A gateway hook provisions the job, not an init container

`jobs.json` holds the owner's other jobs, Hermes rewrites it at runtime, and a
ConfigMap over it would either be read-only or delete what the owner scheduled. So
the job has to be created by something that runs with the file writable, and the
choice is what runs it.

Hermes loads hooks from `HERMES_HOME/hooks/<name>/` (`HOOK.yaml` plus `handler.py`)
at every gateway start, in-process, and a raising handler is logged rather than
fatal. A `gateway:startup` hook that reads `jobs.json`, returns when the job is
already there, and otherwise calls `hermes cron create` is the same work the init
container did, without a second container, and it repairs a restored volume because
the gateway always starts.

The trade is loudness. An init container that fails stops the pod; a hook that fails
logs and the gateway serves Slack anyway, so an absent job is quiet. That is
acceptable because the failure is visible in `hermes cron list` and in the log, and
because the alternative couples a gateway-owned file to the pod lifecycle.

`--deliver local` keeps the ten-minute output out of Slack; the skill posts through
the Slack MCP server only when something moved, so an idle tick is silent by
construction rather than by prompt discipline.

### 5 — Dispatch until the agent is full, lowest number first

The tick walks the `ready` list in order and stops at the first `busy`. It does not
count sessions, cap parallel work, or decide what "full" means: the shim's
`OPENCODE_MAX_CONCURRENT` does, so the one knob that changes concurrency lives with
the thing that enforces it. Each dispatch passes `directory=<repo>` when the issue
names exactly one repository, which is what makes two issues in different
repositories safe to run at once and two in the same repository queue behind each
other.

### 6 — Failures do not look like questions

A transport error leaves the status alone and is reported on the issue. Only a
session that actually asked something sets `Blocked`. The distinction matters
because `Blocked` is the owner's queue: a false positive puts an outage in the same
list as work waiting on a decision.

## Residuals

- The default limit is one, so the loop dispatches one issue per tick until
  `OPENCODE_MAX_CONCURRENT` is raised, and raising it also needs a resource bump on
  `opencode-server` (2 CPU / 4Gi is sized for one turn).
- Zero cost when idle is not claimed: the tick is a model run every ten minutes,
  even when it answers `idle`. A monitor script over the board could suppress the
  run entirely; that is a follow-up, and it needs its own quiet signal.
- A comment is forwarded as one joined turn. If the owner writes three comments in
  a minute, the agent sees one message made of three; the alternative is one turn
  per comment, which spends a slot and a model call each time.
