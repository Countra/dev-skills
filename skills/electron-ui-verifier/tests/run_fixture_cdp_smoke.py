#!/usr/bin/env python3
"""通过复制安装和公共 CLI/HTTP 验证 Playwright CDP 完整工作流。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from public_contract_support import (
    HOST_PYTHON_ENV,
    ROOT,
    ManagedVerifier,
    guarded_harness_path,
    operation_id,
    operation_state,
    python_command,
    select_service_python,
    wait_operation,
    write_json,
)


APP_ID = "public-fixture-app"
APP_VERSION = "1.0.0"
SCREEN_DIGEST = "public-fixture-main"
PRE_STATE = "fixture-ready"
SESSION = "public-fixture"
TITLE = "Verifier Public Fixture"
FIXTURE_HTML = """
<!doctype html>
<html>
  <head>
    <title>Verifier Public Fixture</title>
    <style>
      body { font-family: sans-serif; margin: 32px; background: #f4f7fb; color: #17202a; }
      main { width: 520px; padding: 24px; background: white; border: 1px solid #8da2b8; }
      label, input, button, output { display: block; margin-top: 12px; }
      input { width: 300px; padding: 8px; }
      button { padding: 8px 16px; background: #1261a0; color: white; border: 0; }
      output { min-height: 24px; color: #146b3a; }
    </style>
  </head>
  <body>
    <main>
      <h1>Public contract fixture</h1>
      <label for="fixture-name">Name</label>
      <input id="fixture-name" aria-label="Name" value="">
      <button aria-label="Save" onclick="saveFixture()">Save</button>
      <output data-testid="status" aria-live="polite"></output>
    </main>
    <script>
      function saveFixture() {
        document.querySelector('[data-testid=status]').textContent = 'Saved';
      }
    </script>
  </body>
</html>
"""


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


async def wait_cdp(endpoint: str) -> None:
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"{endpoint}/json/version", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            await asyncio.sleep(0.05)
    raise RuntimeError("fixture CDP endpoint 未就绪")


def prepare_run(
    managed: ManagedVerifier,
    parameter_schema: Path,
    *,
    goal: str,
    alias: str,
) -> dict[str, Any]:
    return managed.cli(
        "ev_prepare.py",
        "--session",
        SESSION,
        "--app-id",
        APP_ID,
        "--app-version",
        APP_VERSION,
        "--screen-digest",
        SCREEN_DIGEST,
        "--pre-state",
        PRE_STATE,
        "--max-risk",
        "low",
        "--goal",
        goal,
        "--alias",
        alias,
        "--parameter-schema",
        str(parameter_schema),
    )


def submit_action(
    managed: ManagedVerifier,
    run_id: str,
    action: Path,
    *,
    bindings: Path | None = None,
) -> dict[str, Any]:
    arguments = ["--run-id", run_id, "--action", str(action), "--deadline-ms", "60000"]
    if bindings is not None:
        arguments.extend(("--bindings", str(bindings)))
    submitted = managed.cli("ev_action.py", *arguments)
    waited = wait_operation(managed, submitted, timeout_seconds=60)
    return {
        "submitted": submitted,
        "observed": waited["observed"],
        "completed": waited["completed"],
    }


def prepare_files(work_dir: Path) -> dict[str, Path]:
    data_dir = work_dir / "fixture-data"
    paths = {
        "schema": data_dir / "parameter-schema.json",
        "bindingsFirst": data_dir / "bindings-first.json",
        "bindingsReuse": data_dir / "bindings-reuse.json",
        "fill": data_dir / "fill-name.json",
        "save": data_dir / "save-name.json",
        "screenshot": data_dir / "screenshot.json",
        "cancel": data_dir / "cancel.json",
    }
    write_json(
        paths["schema"],
        {
            "name": {"type": "string", "required": True},
            "savedStatus": {"type": "string", "required": True},
        },
    )
    write_json(paths["bindingsFirst"], {"name": "fixture-alpha", "savedStatus": "Saved"})
    write_json(paths["bindingsReuse"], {"name": "fixture-beta", "savedStatus": "Saved"})
    write_json(
        paths["fill"],
        {
            "id": "fill-name",
            "type": "fill",
            "locator": {"label": "Name"},
            "value": "${name}",
            "options": {"label": "Fill fixture name"},
            "postconditions": [
                {"type": "value", "locator": {"label": "Name"}, "expected": "${name}"}
            ],
        },
    )
    write_json(
        paths["save"],
        {
            "id": "save-name",
            "type": "click",
            "locator": {"role": "button", "accessibleName": "Save"},
            "options": {"label": "Save fixture name"},
            "postconditions": [
                {
                    "type": "text",
                    "locator": {"testId": "status"},
                    "expected": "${savedStatus}",
                }
            ],
        },
    )
    write_json(paths["screenshot"], {"id": "capture-state", "type": "screenshot", "options": {"label": "fixture-state"}})
    write_json(
        paths["cancel"],
        {
            "id": "wait-for-never",
            "type": "waitText",
            "value": "This text never appears",
            "options": {"timeoutMs": 30000},
        },
    )
    return paths


async def run_contract(work_dir: Path) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    managed = ManagedVerifier(work_dir)
    fixture_playwright = None
    context = None
    attached = False
    checks: dict[str, Any] = {}
    failures: list[str] = []
    try:
        lifecycle = managed.start()
        checks["sessionRenew"] = managed.renew_session()
        fixture_playwright = await async_playwright().start()
        port = free_port()
        endpoint = f"http://127.0.0.1:{port}"
        context = await fixture_playwright.chromium.launch_persistent_context(
            str(work_dir / "browser-profile"),
            headless=True,
            args=[f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.set_content(FIXTURE_HTML)
        await wait_cdp(endpoint)

        probe = managed.cli(
            "ev_probe.py",
            "--cdp",
            endpoint,
            "--target-title-contains",
            TITLE,
        )
        target = next((item for item in probe.get("targets", []) if item.get("title") == TITLE), None)
        if not isinstance(target, dict):
            raise RuntimeError("公共 probe 未发现 fixture target")
        attach = managed.http_json(
            "POST",
            "/sessions/attach",
            {
                "name": SESSION,
                "cdp": endpoint,
                "targetId": target["targetId"],
                "appId": APP_ID,
            },
        )
        attached = attach.get("ok") is True
        files = prepare_files(work_dir)

        prepared = prepare_run(
            managed,
            files["schema"],
            goal="Fill and save fixture name",
            alias="Save fixture profile",
        )
        run_id = str(prepared["runId"])
        fill = submit_action(managed, run_id, files["fill"], bindings=files["bindingsFirst"])
        save = submit_action(managed, run_id, files["save"], bindings=files["bindingsFirst"])
        screenshot = submit_action(managed, run_id, files["screenshot"])
        finalized = managed.cli("ev_finalize.py", "--run-id", run_id)
        pending = managed.cli("ev_pending.py", "--run-id", run_id)
        approved = managed.cli(
            "ev_persist.py",
            "approve",
            "--run-id",
            run_id,
            "--fingerprint",
            str(pending["bundleFingerprint"]),
            "--note",
            "Approve isolated public fixture assets",
        )
        action_by_goal = {
            str(item.get("goal")): str(item["assetId"])
            for item in approved.get("actionAssets", [])
            if isinstance(item, dict) and item.get("assetId")
        }
        action_ids = [action_by_goal.get("fill-name", ""), action_by_goal.get("save-name", "")]
        workflow_asset = approved.get("workflowAsset")
        if not isinstance(workflow_asset, dict) or not workflow_asset.get("assetId"):
            raise RuntimeError("公共 approve 响应缺少 workflowAsset")
        workflow_id = str(workflow_asset["assetId"])
        search = managed.cli(
            "ev_knowledge.py",
            "search",
            "--app-id",
            APP_ID,
            "--app-version",
            APP_VERSION,
            "--screen-digest",
            SCREEN_DIGEST,
            "--pre-state",
            PRE_STATE,
            "--max-risk",
            "low",
            "--query",
            "fill-name",
            "--kind",
            "action",
        )
        composition = managed.cli(
            "ev_knowledge.py",
            "compose",
            "--app-id",
            APP_ID,
            "--app-version",
            APP_VERSION,
            "--screen-digest",
            SCREEN_DIGEST,
            "--pre-state",
            PRE_STATE,
            "--max-risk",
            "low",
            "--subgoal",
            "fill-name",
            "--subgoal",
            "save-name",
            "--bindings",
            str(files["bindingsReuse"]),
        )
        listing = managed.cli("ev_assets.py", "list", "--app-id", APP_ID, "--limit", "10")
        metadata = managed.cli("ev_assets.py", "get", "--asset-id", workflow_id)

        reuse_prepared = prepare_run(
            managed,
            files["schema"],
            goal="Fill and save fixture name",
            alias="Reuse fixture workflow",
        )
        reuse_run = str(reuse_prepared["runId"])
        reused = managed.cli(
            "ev_workflow.py",
            "--run-id",
            reuse_run,
            "--workflow-id",
            workflow_id,
            "--bindings",
            str(files["bindingsReuse"]),
            "--wait-seconds",
            "60",
            timeout=90,
        )
        reuse_final = managed.cli("ev_finalize.py", "--run-id", reuse_run)

        cancel_prepared = managed.cli("ev_prepare.py", "--session", SESSION)
        cancel_run = str(cancel_prepared["runId"])
        cancel_submit = managed.cli(
            "ev_action.py",
            "--run-id",
            cancel_run,
            "--action",
            str(files["cancel"]),
            "--deadline-ms",
            "60000",
        )
        cancel_id = operation_id(cancel_submit)
        cancelled = managed.cli(
            "ev_operation.py",
            "cancel",
            "--operation-id",
            cancel_id,
            expected_codes=(0, 2),
        )
        detached = managed.cli("ev_detach.py", "--session", SESSION)
        attached = False
        detached_again = managed.cli("ev_detach.py", "--session", SESSION)

        production_journal = (
            managed.workspace / ".harness" / "electron-ui-verifier" / "runs" / run_id / "journal.json"
        ).read_text(encoding="utf-8")
        reuse_journal = (
            managed.workspace / ".harness" / "electron-ui-verifier" / "runs" / reuse_run / "journal.json"
        ).read_text(encoding="utf-8")
        report = finalized.get("result", {})
        artifacts = report.get("artifacts", []) if isinstance(report, dict) else []
        screenshot_artifact = next(
            (item for item in artifacts if isinstance(item, dict) and item.get("mediaType") == "image/png"),
            {},
        )
        screenshot_quality = screenshot_artifact.get("quality", {})
        gates = {
            "copyInstall": lifecycle.get("initialized", {}).get("installCheck", {}).get("ok") is True,
            "processManagerReady": lifecycle.get("ready", {}).get("ready") is True,
            "publicProbe": bool(target.get("targetId")),
            "httpAttach": attach.get("ok") is True,
            "operationPoll": operation_state(fill["observed"]) in {"queued", "running", "succeeded"},
            "mutationsSucceeded": all(
                operation_state(item["completed"]) == "succeeded" for item in (fill, save, screenshot)
            ),
            "pageMutated": await page.get_by_label("Name").input_value() == "fixture-beta"
            and await page.get_by_test_id("status").inner_text() == "Saved",
            "finalized": finalized.get("state") == "passed",
            "visualEvidence": screenshot_artifact.get("bytes", 0) > 0
            and screenshot_quality.get("pixelVariation", 0) > 1,
            "pendingGraph": len(action_ids) == 2 and bool(workflow_id),
            "approved": approved.get("ok") is True,
            "searchReuse": search.get("decision") == "reuse"
            and search.get("candidates", [{}])[0].get("assetId") == action_ids[0],
            "composeIds": composition.get("assetIds") == action_ids,
            "assetRead": len(listing.get("assets", [])) == 3 and metadata.get("asset", {}).get("assetId") == workflow_id,
            "workflowReuse": operation_state(reused) == "succeeded" and reuse_final.get("state") == "passed",
            "bindingMinimized": "fixture-alpha" not in production_journal and "fixture-beta" not in reuse_journal,
            "cancelled": operation_state(cancelled) == "cancelled",
            "detachIdempotent": detached.get("detached") is True and detached_again.get("alreadyDetached") is True,
        }
        failures.extend(name for name, passed in gates.items() if not passed)
        checks.update(
            {
                "platform": sys.platform,
                "backend": "playwright-cdp",
                "gates": gates,
                "runIds": {"production": run_id, "reuse": reuse_run, "cancel": cancel_run},
                "operationIds": {
                    "fill": operation_id(fill["submitted"]),
                    "save": operation_id(save["submitted"]),
                    "screenshot": operation_id(screenshot["submitted"]),
                    "cancel": cancel_id,
                },
                "assets": {"actions": action_ids, "workflow": workflow_id},
                "report": {
                    "stepCount": report.get("summary", {}).get("stepCount"),
                    "artifactCount": report.get("summary", {}).get("artifactCount"),
                    "screenshotQuality": screenshot_artifact.get("quality"),
                },
                "retrieval": {"search": search, "composition": composition},
                "cancelState": operation_state(cancelled),
            }
        )
    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
    finally:
        if attached:
            try:
                managed.cli("ev_detach.py", "--session", SESSION)
            except Exception as exc:
                failures.append(f"detach cleanup 失败：{exc}")
        if context is not None:
            try:
                await context.close()
            except Exception as exc:
                failures.append(f"fixture browser close 失败：{exc}")
        if fixture_playwright is not None:
            try:
                await fixture_playwright.stop()
            except Exception as exc:
                failures.append(f"fixture Playwright stop 失败：{exc}")
        cleanup, cleanup_failures = managed.stop()
        checks["cleanup"] = cleanup
        failures.extend(cleanup_failures)
    cleanup = checks.get("cleanup", {})
    session_close = cleanup.get("sessionClose", {})
    cleanup_ok = (
        session_close.get("cleanup", {}).get("cleanupVerified") is True
        and session_close.get("cleanup", {}).get("ownerEmpty") is True
        and session_close.get("idleStop", {}).get("cleanup", {}).get("ownersEmpty") is True
        and cleanup.get("installImmutable", {}).get("unchanged") is True
    )
    if not cleanup_ok:
        failures.append("公共 fixture cleanup/install immutability 未闭环")
    return {"ok": not failures, "checks": checks, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--runtime-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    work_dir = guarded_harness_path(args.work_dir, "--work-dir")
    output = guarded_harness_path(args.output, "--output")
    selected_python = select_service_python(work_dir)
    if not args.runtime_child and selected_python != Path(sys.executable).resolve():
        environment = os.environ.copy()
        environment[HOST_PYTHON_ENV] = str(Path(sys.executable).resolve())
        completed = subprocess.run(
            python_command(
                selected_python,
                Path(__file__).resolve(),
                "--work-dir",
                str(work_dir),
                "--output",
                str(output),
                "--runtime-child",
            ),
            cwd=ROOT,
            env=environment,
            check=False,
        )
        return completed.returncode
    result = asyncio.run(run_contract(work_dir))
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
