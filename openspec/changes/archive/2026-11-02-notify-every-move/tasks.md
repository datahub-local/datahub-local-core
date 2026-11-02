# Tasks

- [x] 1.1 Add `session_url` and the base64url server key to `taskboard.py`.
- [x] 1.2 Add `slack`, `move_line`, `notify_move` and the `notify` subcommand.
- [x] 1.3 Post the line from `status`, `finish` and `sync` after a change.
- [x] 1.4 Put the session URL in the `start` comment and in `issue`.
- [x] 1.5 Set `TASKBOARD_OPENCODE_URL` in `values/hermes.yaml.gotmpl`.
- [x] 1.6 Rewrite the tick skill: 120-second dispatch wait, `needs_input` on
  dispatch, question links, full PR URLs, no manual move lines.
- [x] 1.7 Add tests for the key, the session URL, the move line, the no-change
  silence and the question links.
- [x] 1.8 Run `pytest tests/`, `helmfile template` in `releases/automation`, and
  `openspec validate --all`.
- [x] 1.9 Update the docs page in `datahub-local` to match the reporting rule.
