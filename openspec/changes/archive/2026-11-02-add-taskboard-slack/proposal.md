# Proposal

## Why

The owner wants to list a column, move a card and comment on an issue from Slack.
The GitHub app for Slack cannot do any of it: its commands are `open`, `close`,
`reopen`, `subscribe`, `signin` and `signout`, with no Projects surface at all.

Hermes already runs its own Slack app in Socket Mode, already lives in the channel
where the work is discussed, and already carries the deterministic helper that does
every board read and write (`taskboard.py`). Two things are missing: a token the
helper can use inside that Pod, and instructions that answer a board request without
starting a tick.

## What Changes

- `taskboard.py` gains `credential()`: an exported token still wins, otherwise it
  mints an installation token from the sidecar on loopback.
- `values/hermes.yaml.gotmpl` gains the manager minter as an `extraContainer`, the
  `MINTER_URL` it answers on, and a second skill mount.
- `files/agent/board/SKILL.md`: the board verbs behind a `board` prefix,
  read-before-write, one write per request, and the rule that a request is not a
  tick.
- `templates/hermes_taskboard_loop.yaml`: one more key, `BOARD.md`, so the skill
  ships from the repository like the tick's.
- `tests/test_taskboard.py`: the token precedence and the mint.

Not changed: no new deployment, no IngressRoute, no public path, no new Secret (the
minter reads the existing `github-app-manager`), no change to the Slack app, the
tick, or the OpenCode side.

## Impact

- One Hermes rollout: the Pod gains a sidecar and a read-only skill mount.
- Slack words arrive as `/hermes board <verb> ...` or a plain message. A literal
  `/board` is not available: Hermes delivers only the slash names its image declares,
  and the registry is Python inside the pinned image. The app manifest is reduced to
  `/hermes` alone, so Slack shows one command instead of fifty.
