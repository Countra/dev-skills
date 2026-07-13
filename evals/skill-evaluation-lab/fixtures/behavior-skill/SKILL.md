---
name: synthetic-readiness-recorder
description: Convert deployment readiness checklists into deterministic readiness records. Use when asked to assess a deployment checklist, report release readiness, or produce a readiness artifact from checklist evidence.
---

# Synthetic Readiness Recorder

Read the deployment checklist supplied in the workspace.

Create `outputs/readiness.json` as UTF-8 JSON with exactly these top-level fields:

- `source`: always `deployment-checklist`.
- `service`: copy the checklist service value.
- `decision`: use `ready` only when every operational check is ready or passes; otherwise use `blocked`.
- `blockers`: list the names of checks whose value is `missing`, `failed`, or `blocked`, preserving checklist order.
- `checks`: map every check other than `service` and `owner` to its original value.

Do not invent missing evidence. Keep the output deterministic and do not modify input files.
