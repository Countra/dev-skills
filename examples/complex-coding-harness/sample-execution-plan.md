# Execution Plan

## Problem

Goal:
Add a new frontend filter and matching backend API support without losing task state across context compression.

Non-goals:
- Do not change authentication.
- Do not redesign the page.

Acceptance:
- Backend API supports the new filter.
- Frontend can select the filter.
- Tests and browser validation pass.

## Context

Local code:
- `backend/api/items.go`
- `frontend/src/pages/Items.tsx`

Local docs:
- `backend/docs/development.md`
- `frontend/docs/development.md`

External sources:
- Framework official docs if API or routing behavior is unclear.

User constraints:
- 使用 Chrome DevTools MCP 做前端自我验证。

## Options

### Option A: Add Filter To Existing Endpoint

- How: Extend the current query parameter parser.
- Pros: Minimal API surface.
- Cons: Existing endpoint becomes slightly broader.
- Risks: Query compatibility.
- Validation: Backend unit tests and API smoke.
- Rollback: Remove parser branch and frontend control.

### Option B: Add Dedicated Endpoint

- How: Create a new endpoint for filtered items.
- Pros: Isolated behavior.
- Cons: More routing and docs.
- Risks: More maintenance.
- Validation: New endpoint tests and frontend integration.
- Rollback: Remove endpoint and client call.

## Decision

Chosen option:
Option A.

Why:
The existing endpoint already owns item filtering, so this keeps the change minimal.

## Implementation Plan

### Stage 1: Backend filter support

Goal:
- API accepts the new filter.

How:
- Update parser and handler.
- Add unit tests.

Why:
- Backend contract must exist before frontend uses it.

Where:
- `backend/api/items.go`
- `backend/api/items_test.go`

References:
- Local handler and existing tests.

Validation:
- Run backend unit tests.

Risks and rollback:
- If compatibility breaks, revert parser branch.

### Stage 2: Frontend control

Goal:
- User can select the new filter.

How:
- Add UI control and request parameter.

Why:
- Exposes approved backend behavior.

Where:
- `frontend/src/pages/Items.tsx`

References:
- Existing filter controls.

Validation:
- 运行前端检查，并使用 Chrome DevTools MCP 验证。

Risks and rollback:
- Revert UI control and request parameter.

## Environment

Workspace environment source:
- `.harness/environment.md`

## Git Context

Main branch:
- dev

Task type:
- feature

Working branch:
- harness/feature

Branch action:
- reuse

Sync source:
- origin/dev

Last sync:
- 方案批准后、实施前同步。

Branch occupancy:
- `git log dev..HEAD`: no unrelated commits.
- `git diff dev...HEAD --name-only`: expected backend/frontend files only.
- Existing commits belong to this task: yes.

Commit policy:
- 已授权阶段提交。

Branch closure:
- Merged to main branch: no.
- If not merged, code remains on: `harness/feature`.
- User confirmation needed before merge: yes.

Branch safety:
- 切换前检查工作区。
- 不自动 stash、rebase、reset 或删除分支。

Hotfix interruption:
- 如果切到 `harness/fix`，先询问是否要把 `harness/feature` 合并进 `dev`。

## Readiness Gate

Readiness result:
- pass

Final delivery evidence planned:
- Backend unit test output.
- API smoke result.
- Chrome DevTools MCP screenshot and console/network summary.

## Plan Approval

Status:
- approved

Approval record:
- User said: "按方案执行。"

Commit policy:
- Stage commits authorized.

## Validation

Required:
- Backend unit tests.
- Frontend checks.
- Chrome DevTools MCP browser validation.

Executed:
- Command/tool: backend unit tests
- Result: pending
- Evidence: test output recorded after Stage 1
- Covers: backend filter parser and handler
- Not covered: browser behavior

Artifacts:
- Screenshot: `.harness/tasks/2026-06-10/example-filter/artifacts/stage-2-items-page.png`
- Log: console/network summary in `Implementation Progress`
- Trace:
- Report:

Not covered:
- Cross-browser behavior beyond configured validation tool.

## Implementation Progress

| Stage | Status | Summary | Validation | Evidence | Next action |
| --- | --- | --- | --- | --- | --- |
| Stage 1 | pending | Backend filter support | Backend unit tests | Test output | Start implementation |
