# Troubleshooting

## CDP Endpoint Unreachable

Check that the app was started with `--remote-debugging-port=<port>` and that the port is listening on `127.0.0.1`.

For the Electron GUI app itself, start it with the normal terminal command or ask the user to start it; do not use `process-manager`. Use `process-manager` only for non-GUI companion services such as backend APIs, dev servers, workers, or watchers. If the user started the GUI app manually, do not kill or restart it without permission.

## Playwright Attach Fails

Older Electron builds can expose CDP but reject Playwright browser context operations. Record the Playwright error and fall back to raw CDP. This is not a UI failure unless raw CDP also fails to validate the requested workflow.

## Playwright MCP Fails

MCP may connect but fail on snapshot or browser context setup. Record the failed tool call and use `electron_verify.py` raw CDP fallback.

## Multiple Targets

If probe shows multiple page targets, add `targetUrlContains`, `targetTitleContains`, or `targetIndex` to the workflow. Do not guess which window is the product UI.

## Backend Loading Screen

If the UI remains on loading text such as "正在启动", inspect whether the app backend is ready. Record this as environment readiness failure when the product UI never becomes available.

## Native Dialogs

System file dialogs, UAC prompts, tray menus, and non-Electron windows are out of scope for v1. Ask for a separate native Windows automation plan before using Appium or WinAppDriver.

## Screenshots Are Blank

Check target selection, window visibility, device scale, and whether the page has rendered. The runner should record screenshot size; if possible, verify non-empty pixels before claiming visual evidence.

## Sensitive Data

Do not dump cookies, tokens, localStorage, request headers, or broad page data unless explicitly requested. Keep artifacts ignored by default.
