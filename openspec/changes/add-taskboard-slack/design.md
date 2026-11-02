# Design

## Context

Three facts from the live Pod decided this shape, and all three were checked there
rather than assumed:

- Hermes' Slack adapter is `slack-bolt` in Socket Mode and handles slash commands,
  so no public endpoint is needed for Slack to reach it.
- The commands it accepts are the ones in `COMMAND_REGISTRY`, through
  `slack_native_slashes()`. The adapter comments that "Socket Mode won't deliver
  undeclared commands at all", and a name absent from the registry has no listener,
  so Slack gets no ack.
- Text after `/hermes` that is not a registry subcommand is handled as a regular
  message.

The declared set is `agents, approvals, approve, bg, blueprint, branch, btw,
bundles, busy, codex-runtime, commands, compress, context, curator, deny, fast,
footer, goal, help, hermes, kanban, learn, loop, memory, model, new, personality,
plan, profile, queue, reasoning, reload-mcp, reload-skills, restart, resume, retry,
rollback, save, sessions, sethome, start, steer, stop, subgoal, suggestions, title,
undo, usage, voice, yolo`. `board` is not one of them.

`taskboard.py` owns the project query, the Status option ids, and the comment
marker. Hermes has no GitHub token: the manager App key lives in the MCP proxy
sidecar in the `mcp` release, which mints per request and never exposes a token.

## Decisions

### 1 — A skill, reached through `/hermes` or a plain message

A literal `/board` would need a `CommandDef` appended to `COMMAND_REGISTRY` inside
the Hermes image, plus a rebuilt image, a new digest pin and a regenerated app
manifest. That is a fork of upstream code to buy one word in Slack.

`/hermes <words>` is already declared, already delivered, and already treated as a
regular message when the words are not a subcommand. A plain message in
`#agent-hermes` reaches the same place. So the surface is instructions, not
transport.

### 2 — A second skill, not a section in the tick's

`taskboard-loop` starts with `sync`, `board`, then dispatch. Auto-loaded or chosen
for a chat message, those steps would dispatch issues because somebody asked what
was in a column.

`board` is its own directory with its own mount and says the opposite at the top: do
the one thing asked, run no dispatch, move nothing unnamed. Two skills that share
one helper, and neither can be mistaken for the other.

### 3 — The helper mints its own token

`credential()` keeps the exported variable first, because that is what a manual run
and the tests use, then asks `MINTER_URL` for an installation token. The sidecar
holds the App key; the container that runs the model does not, and no process caches
a token past the hour it is valid for.

This also closes the gap that kept the tick from running: before this change,
`taskboard.py` demanded a PAT that the identity refactor had removed from the Pod.

### 4 — Read before write, one write per request

Every move reads `issue <n>` first. The reply can then say "moved from Blocked", and
a card already in the asked column is answered rather than written again. A chat
request writes once: no comment plus a move plus a dispatch unless the message asked
for all three.

### 5 — A move to Ready is the owner's to make

The tick may never set `Ready`; that is how a human reads an issue before work
starts. The board skill may, because the owner is the one asking. The same rule for
`Done` and `Backlog`, which the tick also refuses to set on its own.

## Residuals

- A native `/board` needs the image patch described above. Until then the command is
  `/hermes`, and the words after it are the request.
- `channel_skill_bindings` in values would bind the skill to `#agent-hermes`, and
  with the repository as the only source of `config.yaml` it would take effect on
  the next rollout. It is left out on purpose: a binding loads the board
  instructions into every message in the channel, and the description is enough to
  select the skill when the words are about the board.
- `taskboard.py` reads the first 100 items. A bigger board needs pagination before
  the listing is complete.
- Nothing is echoed to a channel thread and the reply is the agent's message, not a
  card the owner can click.
