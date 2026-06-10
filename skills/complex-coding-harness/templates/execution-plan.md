# Execution Plan

## Problem

Goal:

Non-goals:

Acceptance:

Constraints:

Open uncertainties:

## Context

Local code:

- 

Local docs:

- 

External sources:

- 

User constraints:

- 

## Options

### Option A: Minimal Change

- How:
- Pros:
- Cons:
- Risks:
- Validation:
- Rollback:

### Option B: Structured Change

- How:
- Pros:
- Cons:
- Risks:
- Validation:
- Rollback:

## Decision

Chosen option:

Why:

Impact:

Reversibility:

Change conditions:

## Implementation Plan

### Stage 1: <stage-name>

Goal:

- 

How:

- 

Why:

- 

Where:

- Files/modules:
- APIs/configs:
- Tests/docs:

References:

- 

Validation:

- 

Risks and rollback:

- 

## Environment

Workspace environment source:

- `.harness/environment.md`

This task uses:

- 

Temporary overrides:

- 

## Git Context

Main branch:

-

Task type:

-

Working branch:

-

Branch action:

- create / reuse / already-on-branch / not-applicable

Sync source:

-

Last sync:

-

Branch occupancy:

- `git log <main>..HEAD`:
- `git diff <main>...HEAD --name-only`:
- Existing commits belong to this task:

Commit policy:

-

Branch closure:

- Merged to main branch:
- If not merged, code remains on:
- User confirmation needed before merge:

Branch safety:

- 切换前已检查工作区：
- 不自动 stash：
- 不自动 rebase：
- 不自动 reset：

Hotfix interruption:

- 从 `harness/feature` 切换到 `harness/fix` 前，先询问是否要把 feature 合并进主分支：
- 决策：

Open issues:

-

## Tooling

| Tool | Purpose | Stage | Status | Risk | Alternative | User confirmation |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

## Validation

Required:

- 

Executed:

- Command/tool:
- Result:
- Evidence:
- Covers:
- Not covered:

Optional:

- 

Artifacts:

- Screenshot:
- Log:
- Trace:
- Report:

Not covered:

- 

If unable to run:

- 

## Documentation

Required updates:

- 

Changelog plan:

- 

## Questions And Overrides

| ID | Blocking | Status | Question | Decision | Applied to |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## Readiness Gate

| Check | Status | Evidence |
| --- | --- | --- |
| Goal and acceptance clear | pending |  |
| Context collected | pending |  |
| Options compared | pending |  |
| Decision recorded | pending |  |
| Implementation stages detailed | pending |  |
| Environment confirmed | pending |  |
| Git context confirmed | pending |  |
| Tooling confirmed | pending |  |
| Validation confirmed | pending |  |
| Final delivery evidence planned | pending |  |
| Documentation updates confirmed | pending |  |
| Risks identified | pending |  |
| Blocking questions closed | pending |  |

Readiness result:

- `pending`

## Plan Approval

Status:

- `not_requested`

Approval record:

- 

Commit policy:

- `not_authorized`

## Implementation Progress

| Stage | Status | Summary | Validation | Evidence | Next action |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## Code Review

| Stage | Finding | Severity | Resolution |
| --- | --- | --- | --- |
|  |  |  |  |

## Commit Log

| Stage | Repository | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |
