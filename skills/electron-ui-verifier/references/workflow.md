# Electron UI Verifier Workflow

## Purpose

Use this workflow to inspect and validate Electron desktop applications with reproducible evidence. The primary targets are packaged Electron `.exe` files and Electron dev apps exposing Chrome DevTools Protocol (CDP).

## Preflight

1. Read the current harness task plan and environment rules.
2. Confirm whether the app is already running.
3. Confirm the CDP endpoint, usually `http://127.0.0.1:<port>`.
4. Confirm where artifacts should be stored.
5. Check whether `process-manager` is available before starting any long-running process.

Finite commands such as `python -m py_compile`, `--help`, JSON parsing, and report checks do not use `process-manager`.

## Starting or Connecting

Prefer connecting to an app the user already started. If the agent must start a long-running Electron app, and `process-manager` is available, use it. Do not hand-roll background PowerShell, `Start-Process`, `cmd /c start`, or hidden launchers.

Packaged apps usually need a remote debugging argument:

```powershell
D:\App\App.exe --remote-debugging-port=9223
```

When the app depends on a backend service, validate backend readiness separately. If the UI displays a loading screen because the backend is unavailable, record that as environment readiness failure, not as a UI verification pass.

## Backend Selection

Use this order:

1. Playwright Electron for dev/source apps.
2. Playwright CDP for compatible packaged apps.
3. Playwright MCP if the environment explicitly requires MCP UI tooling.
4. Raw CDP fallback through `scripts/electron_verify.py`.

Always record:

- Attempted backend.
- Selected backend.
- Failure reason for each skipped or failed backend.
- CDP version, browser version, target title, target URL, and target id when available.

## Target Selection

Electron can expose multiple targets. Run probe first:

```powershell
python skills/electron-ui-verifier/scripts/electron_verify.py probe --cdp http://127.0.0.1:9223 --out .harness/tasks/<task>/artifacts/electron
```

If more than one page target exists, specify one of:

- `targetUrlContains`
- `targetTitleContains`
- `targetIndex`
- `targetType`

Do not guess. If target selection is ambiguous, stop and report candidates.

## Security

- Default to `127.0.0.1` or `localhost` endpoints.
- Remote CDP endpoints require explicit user approval.
- Do not export cookies, tokens, localStorage, request headers, or large sensitive payloads by default.
- Keep artifacts in ignored runtime directories unless the user asks to commit them.

## Evidence

Every real UI verification should produce:

- `report.json`
- `summary.md`
- At least one screenshot or an explicit reason screenshots are unavailable.
- Snapshot or extracted text relevant to the user request.

`report.json` must include `schemaVersion: 1`, backend information, target metadata, step-level statuses, artifacts, and errors.

`summary.md` must distinguish:

- `passed`
- `failed`
- `skipped`
- `not covered`

Do not claim verification passed if the app was not reached, the target was ambiguous, or all driver backends failed.
