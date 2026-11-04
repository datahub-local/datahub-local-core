# Tasks

- [x] 1.1 Add `referenced_pulls` and `pull <n>`; sort open first, then number
      descending.
- [x] 1.2 `pull_of` prefers a referencing pull request and falls back to the
      branch.
- [x] 1.3 `inbox` reads comments from every referencing pull request, with the
      branch of `current` in its output.
- [x] 1.4 Make `BRANCH_RE` and `CLAIM_REPO_RE` case-insensitive.
- [x] 1.5 Update `taskboard-loop/SKILL.md` step 5 to use `pull <n>` and to find a
      second-cycle pull request by its `Refs` line.
- [x] 2.1 Pin the case-insensitive branch, the referencing lookup, the second
      cycle (#99 shape), comments from both pull requests, and the `pull` output.
- [x] 2.2 Run `python3 -m pytest tests/test_taskboard.py`; run `helmfile template`
      in `releases/automation`.
- [x] 3.1 Add the spec delta and run `openspec validate --all`.
- [x] 4.1 Read #99 through the new helper from the Hermes pod: `current` is #55,
      open, on `fix/99-pi-writer-auth-secret`.
