# Workflow Actions

Workflow files are JSON documents consumed by `scripts/electron_verify.py run`.

## Shape

```json
{
  "app": {
    "cdp": "http://127.0.0.1:9223"
  },
  "targetUrlContains": "index.html",
  "readiness": [
    {"waitText": "案件", "timeoutMs": 30000}
  ],
  "steps": [
    {"id": "home", "snapshot": true},
    {"id": "open-first", "clickText": "查看"},
    {"id": "result", "screenshot": "result.png"}
  ]
}
```

Use absolute paths for file-like values. Relative screenshot names are allowed only inside the chosen output directory.

## Target Fields

- `targetUrlContains`: choose a page whose URL contains the value.
- `targetTitleContains`: choose a page whose title contains the value.
- `targetIndex`: choose by zero-based index after filtering page targets.
- `targetType`: defaults to `page`.

If no target rule is provided and multiple targets exist, the runner stops.

## Readiness Actions

- `waitText`: wait until visible document text contains a string.
- `waitUrlContains`: wait until the current target URL contains a string.
- `timeoutMs`: timeout for that readiness check.

Readiness checks should prove the UI is usable, not just that the process is alive.

## Step Actions

- `snapshot: true`: save DOM text, title, URL, and basic element candidates.
- `screenshot: "name.png"`: capture a PNG screenshot.
- `clickText: "文本"`: click the first matching visible text candidate.
- `clickText: {"text": "文本", "index": 1}`: click a specific match.
- `clickXY: {"x": 100, "y": 200}`: coordinate fallback.
- `fillText`: set a value on an input selected by text or selector.
- `pressKey`: send a keyboard key.
- `extractText`: extract text into report fields.
- `extractTable`: extract visible table/list rows.
- `evaluate`: optional explicit JavaScript action; use only when necessary.

Any step can set `continueOnFailure: true` when the step is useful evidence but not required for the business assertion. If such a step fails, the runner records it as `skipped`, adds the reason to `notCovered`, and keeps the workflow status based on the required steps. Use this mainly for flaky screenshot capture or secondary visual evidence, not for readiness, navigation, or core assertions.

## Selector Preference

Prefer stable selectors or exact text when available:

1. CSS selector supplied by workflow.
2. Exact text.
3. Text contains.
4. Coordinate fallback.

When a match is ambiguous, record candidates and stop unless the workflow specifies `index`.

## Reports

Each step should produce a step record:

```json
{
  "id": "result",
  "action": "screenshot",
  "status": "passed",
  "backend": "raw-cdp",
  "artifacts": ["result.png"],
  "error": null
}
```

Step status values:

- `passed`
- `failed`
- `skipped`

Unexecuted business coverage belongs in top-level `notCovered`.
