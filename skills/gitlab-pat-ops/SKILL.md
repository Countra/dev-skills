---
name: gitlab-pat-ops
description: Operate GitLab REST resources with this repository's PAT-based, guarded-write skill. Use when Codex needs to locate projects or namespaces; inspect repositories, commits, branches, templates, issues, merge requests, notes, discussions, diffs, pipelines, jobs, approvals, or resource events; create projects/issues/MRs; update or close/reopen issues/MRs; reply to notes/discussions; resolve MR threads; or diagnose access through SKILL_GITLAB_BASE_URL and SKILL_GITLAB_PAT.
---

# GitLab PAT Ops

Use the bundled `gl_*` scripts as composable resource commands. They share one authenticated transport, capability registry, JSON envelope, pagination budget, and guarded-write primitive. Do not bypass them with ad hoc REST calls for a capability they already cover.

## Configuration

Required environment variables:

- `SKILL_GITLAB_BASE_URL`
- `SKILL_GITLAB_PAT`

Optional variables:

- `SKILL_GITLAB_CA_BUNDLE`: absolute CA bundle path.
- `SKILL_GITLAB_ALLOW_HTTP`: explicit opt-in for non-loopback HTTP.
- `SKILL_GITLAB_TEST_PROJECT`: exact disposable project allowed only for separately authorized live-write validation.

Never ask the user to put a PAT in argv, files, logs, commit messages, or `.harness` artifacts. Do not read generic or legacy token aliases.

When configuration is absent or uncertain, run:

```powershell
python skills\gitlab-pat-ops\scripts\gl_doctor.py --offline-check --pretty
```

Use the live doctor only when identity, scope, instance version, or authentication is uncertain and live access is needed.

## Core Workflow

1. Locate the namespace and project.
2. Read the exact issue, MR, branch, commit, template, or pipeline involved.
3. Compose additional resource reads only as needed: metadata, notes, discussions, events, diffs, approvals, jobs.
4. For a write, first run the command without `--confirm`.
5. Inspect the exact target, summarized payload, preflight, and full `confirm_fingerprint`.
6. After that exact action is approved, rerun with `--confirm <full-fingerprint>`; apply rereads preflight and sends at most one request.
7. Read the resulting resource. If the response outcome is unknown, do not replay the write before this read.

Read [workflow.md](references/workflow.md) for composition patterns and [security.md](references/security.md) for failure and write boundaries.

## Capability Discovery

Do not dump capabilities on every task. Run `gl_capabilities.py` only when the resource, subcommand, scope, tier behavior, or prohibited boundary is unclear. Prefer an exact query:

```powershell
python skills\gitlab-pat-ops\scripts\gl_capabilities.py --capability discussions.mr.resolve --pretty
python skills\gitlab-pat-ops\scripts\gl_capabilities.py --resource pipelines --pretty
python skills\gitlab-pat-ops\scripts\gl_capabilities.py --prohibited --pretty
```

An exact query for a prohibited capability returns `unsupported_capability`. The registry is the only machine-readable endpoint and safety truth. Read [capability-guide.md](references/capability-guide.md) only when composing unfamiliar resources.

## Resource Commands

- Discovery: `gl_projects.py`, `gl_namespaces.py`, `gl_search.py`.
- Repository: `gl_repo.py`, `gl_commits.py`, `gl_branches.py`.
- Planning metadata: `gl_templates.py`, `gl_labels.py`, `gl_milestones.py`, `gl_members.py`.
- Work items: `gl_issues.py`, `gl_mrs.py`.
- Collaboration and history: `gl_notes.py`, `gl_discussions.py`, `gl_resource_events.py`.
- Review and CI context: `gl_mr_diffs.py`, `gl_approvals.py`, `gl_pipelines.py`.
- Diagnostics: `gl_doctor.py`; conditional registry lookup: `gl_capabilities.py`.

All commands emit `{ok, operation, data|error, meta}` JSON. Repository raw/blob bytes default to base64 inside the envelope; use `--text` only for strict UTF-8 or `--output` for atomic binary output. Existing output files are not replaced unless `--overwrite` is explicit.

## Write Boundary

Allowed writes are project/issue/MR create, issue/MR metadata update and close/reopen, top-level note reply, discussion reply, and MR discussion resolve/reopen. Metadata removal uses explicit flags such as `--clear-description`, `--unassign`, `--unassign-reviewers`, `--remove-milestone`, and `--remove-due-date`.

Delete, merge, approve, token/permission management, repository or branch mutation, CI mutation, and bulk writes are prohibited. Live writes are not routine validation and always require separate authorization plus an exact disposable target.
