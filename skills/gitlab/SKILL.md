---
name: gitlab
description: Operate GitLab through the REST API with a skill-scoped personal access token. Use when Codex needs to inspect or search GitLab projects, repositories, files, issues, comments/notes, or merge requests; create projects or merge requests; parse issue/MR comments; or reply to comments safely using SKILL_GITLAB_BASE_URL plus SKILL_GITLAB_PAT/SKILL_GITLAB_TOKEN.
---

# GitLab

Use this skill for GitLab repository, issue, note, and merge request work through the bundled `gl_*` scripts. The scripts read only skill-scoped environment variables:

- `SKILL_GITLAB_BASE_URL`
- `SKILL_GITLAB_PAT`
- `SKILL_GITLAB_TOKEN` as a same-prefix token alias

Do not use generic `GITLAB_TOKEN` by default. Never ask the user to paste a token into a command, file, log, commit message, or `.harness` artifact.

## Required First Step

Run the doctor before any GitLab operation:

```powershell
python skills\gitlab\scripts\gl_doctor.py --offline-check --pretty
```

If live access is needed and the user has authorized it, run:

```powershell
python skills\gitlab\scripts\gl_doctor.py --pretty
```

If required variables are missing, stop and ask the user to set them. The scripts print PowerShell examples without exposing token values.

## Workflow

1. Run `gl_doctor.py`.
2. Use read-only commands first to locate the project, issue, note, branch, or MR.
3. For writes, run dry-run first and inspect the redacted request preview.
4. Only add `--confirm` after the user has approved the exact target and action.
5. Record live smoke results without token values.

Detailed workflow: read `references/workflow.md`.

## Scripts

- `gl_doctor.py`: check environment variables and optional `/user` auth.
- `gl_projects.py`: list/search/get projects and guarded project creation.
- `gl_search.py`: global or project search.
- `gl_repo.py`: repository tree, file, raw file, blob, and raw blob.
- `gl_issues.py`: list/get issues, related MRs, and closed-by MRs.
- `gl_notes.py`: list/compact issue or MR notes, and guarded replies.
- `gl_mrs.py`: list/get MRs, MR notes, and guarded MR creation.

All scripts default to JSON output; pass `--pretty` for formatted JSON.

## Safety Rules

- Write commands must support dry-run and require `--confirm` for real requests.
- Prefer `--body-file` or `--stdin` for comment bodies; `--body` can leak into shell history.
- Live write smoke is only allowed in the `codex_test` test repository when the user has explicitly allowed it.
- Never run destructive operations such as delete, close, merge, approve, force push, permission changes, token management, or bulk cross-repository writes.
- If a requested GitLab operation is outside these scripts, inspect `references/api-map.md` and use the same safety pattern before extending the skill.

Security details: read `references/security.md`.

## Reference Routing

- API endpoints, scopes, pagination, and script mapping: `references/api-map.md`.
- Step-by-step task flows and examples: `references/workflow.md`.
- Token handling, dry-run, confirm, and live smoke limits: `references/security.md`.
