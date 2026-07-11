# Resource Workflow

## Read Tasks

Run the doctor when configuration/authentication is uncertain or before the first live operation in an unfamiliar environment. Known reads do not require `gl_capabilities.py`.

Start with the narrowest locator. Project and namespace discovery precedes project-scoped commands. Issue analysis normally uses issue detail, notes or discussions, resource events, and related MRs. MR review normally adds commits, current diffs or diff versions, approval state, pipelines/jobs, discussions, and related issue context.

Use Project Templates API reads before an issue/MR create that names a template. Validate label, milestone, member, source branch, and target branch identities before creating a fingerprint.

## Write Tasks

1. Read the exact target and supporting metadata.
2. Prepare long text in a UTF-8 file or stdin.
3. Use explicit removal flags; do not encode an accidental empty value as intent.
4. Run the write without `--confirm`.
5. Verify operation, target, summarized body, preflight, and full fingerprint.
6. Obtain approval for that exact operation and payload.
7. Rerun with the exact `--confirm` value.
8. Read the target and retain request ID evidence.

The generic issue/MR `update` command accepts only fields present on the command line. It rejects an empty update. Full label replacement/clear cannot be combined with label deltas, and the same label cannot be added and removed together.

Top-level note replies and discussion replies are different resources. Use `gl_notes.py` for a new note on an issue/MR and `gl_discussions.py reply` for a note inside an existing thread. Only MR discussions expose guarded resolve/reopen.

## Unknown Write Outcome

POST/PUT are never automatically retried. If transport reports `outcome=unknown`, reread the target, its notes/discussions/events, or recent project activity before deciding whether the operation applied. Do not reuse the old fingerprint blindly; create a new preview only after state is understood.

## Failure Handling

- Missing environment: ask for only `SKILL_GITLAB_BASE_URL` and `SKILL_GITLAB_PAT`.
- 401: inspect PAT validity/scope with doctor without printing the PAT.
- 403/404: verify project/resource identity while preserving permission/not-found ambiguity.
- 409/412/422 or fingerprint mismatch: reread and generate a new preview.
- 429/selected 5xx on GET/HEAD: rely on bounded transport retries; do not add shell retry loops.
- Response, request, or pagination limit: narrow the query or choose explicit bounded options/output.
- Unsupported capability: stop; do not bypass the registry with a raw request.

## Live Validation

Offline fake HTTP tests are the default. Optional live reads may use the configured instance. Any live write requires new explicit authorization and exact `SKILL_GITLAB_TEST_PROJECT` matching; a previous write request or CI authorization does not authorize another GitLab write.
