---
name: electron-ui-verifier
description: Verify Electron desktop application UI workflows with screenshots, DOM/text/table extraction, Chrome DevTools Protocol probing, Playwright or MCP when available, and structured evidence reports. Use when Codex needs to inspect a packaged Electron exe or Electron dev app, click through UI flows, collect screenshots, validate visible content, analyze task lists/toolboxes, or produce reproducible GUI verification artifacts.
---

# Electron UI Verifier

Use this skill to verify Electron desktop UI behavior and produce auditable artifacts. Prefer it over one-off scripts when the task involves packaged `.exe` apps, `--remote-debugging-port`, Playwright/MCP attach, screenshots, UI text extraction, table extraction, or repeatable desktop workflow checks.

## Required Workflow

1. Read `references/workflow.md` before starting, connecting to, or validating an Electron app.
2. Start packaged Electron GUI apps with the normal terminal command requested by the user, or connect to an app the user already started. Do not use `process-manager` for the Electron GUI app itself.
3. Probe the target first with `scripts/electron_verify.py probe`. Do not click or type until the probe identifies a single target or the workflow specifies target selection.
4. Run validation with a workflow JSON or a narrow one-shot command. Store artifacts under the current harness task `artifacts/` directory or another ignored runtime directory.
5. Report the backend used, fallback decisions, screenshots, extracted content, and uncovered scope. Do not claim real UI verification passed without artifacts.

## Driver Order

Use the highest reliable backend available for the current app:

1. Playwright Electron for dev/source Electron apps.
2. Playwright CDP for compatible packaged apps.
3. Playwright MCP when the environment requires MCP-based UI verification.
4. Raw CDP fallback through `electron_verify.py` for older Electron or Playwright/MCP attach failures.

Record every fallback reason in `report.json` and the harness validation evidence.

## Hard Rules

- Use absolute paths for executable paths, working directories, workflow files, and output directories.
- Packaged Electron GUI apps are a special case: launch them directly in a normal terminal or ask the user to launch them when elevation is required. `process-manager` is not used for the GUI app.
- Non-GUI companion services, such as backend APIs, dev servers, workers, or watchers, still follow the workspace harness/process-manager rules when they must keep running.
- Default to local CDP endpoints only. Remote endpoints require explicit user approval and must be recorded.
- Do not guess when multiple Electron targets exist. Provide target selection or stop with the candidate list.
- Do not export cookies, tokens, localStorage, request headers, or large sensitive text unless the user explicitly asks.
- Do not use Spectron for new verification work.
- Treat Windows native dialogs, UAC prompts, tray menus, and non-Electron windows as out of scope for v1 unless separately approved.

## Resources

- `scripts/electron_verify.py`: CLI runner for probe, workflow execution, screenshots, extraction, and reports.
- `references/workflow.md`: planning, backend selection, Electron GUI launch rules, and evidence rules.
- `references/actions.md`: workflow JSON actions and examples.
- `references/troubleshooting.md`: common failures and recovery rules.
- `assets/workflow.example.json`: minimal workflow template.
