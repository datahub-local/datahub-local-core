# Tasks

- [x] 1.1 Give `taskboard.py` a `credential()` that prefers
      `GITHUB_PERSONAL_ACCESS_TOKEN` and otherwise mints from `MINTER_URL`.
- [x] 1.2 Add the manager minter as an `extraContainer` in
      `values/hermes.yaml.gotmpl`, with `github-app-manager` as its only secret and
      `MINTER_URL` in the Hermes container.
- [x] 1.3 Add `files/agent/board/SKILL.md`: the verb map, read-before-write, one
      write per request, dictated comments as `--owner`, and the rule that a request
      is not a tick.
- [x] 1.4 Add `BOARD.md` to the `hermes-taskboard-loop` ConfigMap and mount it at
      `/opt/data/skills/devops/board` so its `SKILL.md` is a skill directory.
- [x] 1.5 Add tests for the token precedence, the mint, and the missing-source
      failure to `tests/test_taskboard.py`.
- [x] 1.6 `helmfile template` renders the sidecar, the `MINTER_URL` env, the board
      skill mount and the whole namespace.
- [x] 2.1 Deploy, then confirm from inside the Pod that
      `python3 .../taskboard.py ready` mints and answers, and that `hermes skills`
      lists `board`.
- [x] 2.2 Reduce the Slack app manifest to the one `/hermes` entry (paste
      `features.slash_commands`, keep it to that item) and confirm Slack's command
      menu lists one Hermes command.
- [x] 2.3 In Slack, send `/hermes board move <n> to ready` and a plain message asking
      for a column; confirm one write, a reply naming the previous status, and no tick
      (no session started, no other card moved).
- [x] 2.4 Ask for a comment and confirm it lands on the issue without a
      `<!-- taskboard:` marker, so the tick reads it as the owner's.
- [x] 2.5 Confirm an unclear request gets one question back instead of a guessed
      issue, and that `/hermes status` still answers Hermes itself.
- [ ] 3.1 Add the Slack surface to `docs/services/automation.md` in
      `datahub-local/datahub-local`, in a separate pull request.
- [x] 2.6 The owner ran the surface in Slack and reported every command working.
