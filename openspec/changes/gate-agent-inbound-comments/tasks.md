# Tasks

- [x] 1.1 Add `TRUSTED_USERS` and `trusted()` to `taskboard.py`.
- [x] 1.2 Gate `pending_comments`, `merge_pending` and `help_state`.
- [x] 1.3 Add `untrusted_comments` and the `ignored` field to `inbox`.
- [x] 1.4 Withhold an untrusted body in `issue`; gate `repo_of` and `last_branch`
      through `readable()`.
- [x] 1.5 Read the forwarding, session and help markers from machine comments only.
- [x] 1.5 Add `github_trusted_users` to `values/global.yaml.gotmpl` and render it
      as `GITHUB_TRUSTED_USERS` in the Hermes values.
- [x] 1.6 Update `SKILL.md` step 3 for `ignored` and `withheld`.
- [x] 2.1 Pin the gate in `tests/test_taskboard.py`: stranger, collaborator,
      blocked answer, ignored list, withheld body, untrusted claim.
- [x] 2.2 Run `pytest tests/test_taskboard.py`, `ruff check`, `helmfile template`
      in `releases/automation`.
- [x] 3.1 Add the spec delta; `openspec validate --all`.
- [x] 4.1 Restrict issue and pull request creation to collaborators and set an
      existing-users interaction limit on the public `datahub-local*` repositories
      (gh CLI, not this change).
- [ ] 4.2 Deploy the chart so `GITHUB_TRUSTED_USERS` reaches the Hermes pod.
