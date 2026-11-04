# Tasks

- [x] 1.1 Add `full_repo` and `repo_of` to `taskboard.py`; fall back to the claim
      comment when `## Repo` names no repository.
- [x] 1.2 Add `GitHub.pull_comments` reading `/issues/<n>/comments` and
      `/pulls/<n>/comments`; merge both into `inbox` through `merge_pending`, with
      id deduplication.
- [x] 1.3 Route `pr` and `review` through `full_repo`.
- [x] 1.4 Update `SKILL.md` step 3 to name conversation and inline review comments,
      and note that `pr` accepts a bare repository name.
- [x] 2.1 Pin `repo_of` (section, claim, neither), id deduplication and the two
      collections in `tests/test_taskboard.py`.
- [x] 2.2 Run `python3 -m pytest tests/test_taskboard.py`; run
      `helmfile template` in `releases/automation`.
- [x] 3.1 Update `openspec/specs/taskboard-loop/spec.md`; `openspec validate --all`.
- [x] 4.1 Forward `datahub-local-ai#53`'s missed owner comment to
      `ses_e61d7b831ffePwyJ7DgS3nv4aL` once deployed.
