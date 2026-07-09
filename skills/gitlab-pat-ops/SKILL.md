---
name: gitlab-pat-ops
description: Operate GitLab through the REST API with this repository's PAT-based GitLab operations skill. Use when Codex needs to inspect or search GitLab projects, repositories, files, labels, milestones, members, branches, issue templates, issues, comments/notes, or merge requests; create projects/issues/merge requests; update issue descriptions; close or reopen issues/MRs with guarded dry-run; parse issue/MR comments; reply to comments safely; or inspect the maintained capability boundary using SKILL_GITLAB_BASE_URL plus SKILL_GITLAB_PAT/SKILL_GITLAB_TOKEN.
---

# GitLab PAT Ops

Use this skill for GitLab repository, issue, note, and merge request work through the bundled `gl_*` scripts. The scripts read only skill-scoped environment variables:

- `SKILL_GITLAB_BASE_URL`
- `SKILL_GITLAB_PAT`
- `SKILL_GITLAB_TOKEN` as a same-prefix token alias

Do not use generic `GITLAB_TOKEN` by default. Never ask the user to paste a token into a command, file, log, commit message, or `.harness` artifact.

## Required First Step

Run the doctor before any live GitLab operation:

```powershell
python skills\gitlab-pat-ops\scripts\gl_doctor.py --offline-check --pretty
```

If live access is needed and the user has authorized it, run:

```powershell
python skills\gitlab-pat-ops\scripts\gl_doctor.py --pretty
```

If required variables are missing, stop and ask the user to set them. The scripts print PowerShell examples without exposing token values.

Only inspect the maintained capability boundary when the requested operation, safety status, scope requirement, or supported/unsupported boundary is unclear:

```powershell
python skills\gitlab-pat-ops\scripts\gl_capabilities.py --pretty
```

## Workflow

1. Run `gl_doctor.py`.
2. Use read-only commands first to locate the project, labels, milestones, members, branches, templates, issue, note, or MR.
3. For writes, run dry-run first and inspect the redacted request preview.
4. Only add `--confirm` after the user has approved the exact target and action.
5. If the operation's support status or safety boundary is uncertain, run `gl_capabilities.py`.
6. Record live smoke results without token values.

Detailed workflow: read `references/workflow.md`.

## Scripts

- `gl_capabilities.py`: print the current supported, guarded, and prohibited capability boundary when it is unclear.
- `gl_doctor.py`: check environment variables and optional `/user` auth.
- `gl_projects.py`: list/search/get projects and guarded project creation.
- `gl_search.py`: global or project search.
- `gl_repo.py`: repository tree, file, raw file, blob, and raw blob.
- `gl_labels.py`: list/get project labels for issue metadata selection.
- `gl_milestones.py`: list/get project milestones and milestone issues/MRs.
- `gl_members.py`: list/get project members for assignee/reviewer discovery.
- `gl_branches.py`: list/get project branches for MR preparation.
- `gl_issue_templates.py`: list/get project repository issue templates under `.gitlab/issue_templates`.
- `gl_issues.py`: list/get issues, related MRs, closed-by MRs, guarded issue creation, guarded issue description update, and guarded issue close/reopen.
- `gl_notes.py`: list/compact issue or MR notes, and guarded replies.
- `gl_mrs.py`: list/get MRs, MR notes, guarded MR creation, and guarded MR close/reopen.

All scripts default to JSON output; pass `--pretty` for formatted JSON.

## Safety Rules

- Write commands must support dry-run and require `--confirm` for real requests.
- Prefer `--body-file` or `--stdin` for comment bodies; `--body` can leak into shell history.
- Issue creation checks existing labels by default; use `--allow-new-labels` only when intentionally allowing GitLab to create missing labels.
- Issue description updates are supported as guarded full-field replacements: read the target issue first, use `--description-file` or `--stdin` for long content, dry-run first, then `--confirm` only after the exact target and replacement description are approved. Empty descriptions require `--allow-empty-description`.
- Live write smoke is only allowed in the `codex_test` test repository when the user has explicitly allowed it.
- Never run destructive operations such as delete, merge, approve, force push, permission changes, token management, or bulk cross-repository writes.
- Issue/MR close/reopen are supported only as guarded state changes: dry-run first, then `--confirm` only after the exact target is approved.
- If a requested GitLab operation is outside these scripts, inspect `gl_capabilities.py` and `references/api-map.md`, then use the same safety pattern before extending the skill.
- When adding or removing a capability, update `gl_capabilities.py`, `references/api-map.md`, `references/security.md`, eval prompts, and tests together.

Security details: read `references/security.md`.

## Reference Routing

- API endpoints, scopes, pagination, and script mapping: `references/api-map.md`.
- Step-by-step task flows and examples: `references/workflow.md`.
- Token handling, dry-run, confirm, and live smoke limits: `references/security.md`.
- Machine-readable capability boundary for uncertain cases: run `scripts/gl_capabilities.py`.
