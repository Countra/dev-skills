#!/usr/bin/env python3
"""跨平台启动隔离 Chromium fixture 并验证 Playwright CDP lifecycle。"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "electron-ui-verifier" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.driver import PlaywrightCdpDriver  # noqa: E402
from electron_verifier.runs import RunService  # noqa: E402
from electron_verifier.sessions import SessionManager  # noqa: E402


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


async def smoke(work_dir: Path) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    port = free_port()
    endpoint = f"http://127.0.0.1:{port}"
    fixture_playwright = await async_playwright().start()
    context = None
    driver = PlaywrightCdpDriver(work_dir / "driver-artifacts")
    try:
        context = await fixture_playwright.chromium.launch_persistent_context(
            str(work_dir / "profile"),
            headless=True,
            args=[f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.set_content(
            "<title>Verifier Fixture</title><main><h1>Ready</h1>"
            "<button aria-label='Save'>Save</button><div style='width:320px;height:180px;background:#1473e6'></div></main>"
        )
        await wait_cdp(endpoint)
        await driver.start()
        probe = await driver.probe(endpoint, {"targetTitleContains": "Verifier Fixture"})
        targets = probe.get("targets", [])
        selected = next((item for item in targets if item.get("title") == "Verifier Fixture"), None)
        if selected is None:
            raise RuntimeError("fixture target 未被 probe 发现")
        runtime = work_dir / "runtime"
        config = SimpleNamespace(state_root=runtime, runs_dir=runtime / "runs", pending_dir=runtime / "pending")
        sessions = SessionManager(runtime / "sessions.json", driver)
        await sessions.load()
        runs = RunService(config, sessions)
        prepared = await runs.prepare(
            {
                "session": "fixture",
                "cdp": endpoint,
                "appId": "fixture-app",
                "goal": "采集 fixture 语义与视觉证据",
                "targetId": selected["targetId"],
            }
        )
        for action in (
            {"id": "snapshot", "type": "snapshot"},
            {"id": "screenshot", "type": "screenshot", "options": {"label": "fixture"}},
        ):
            result = await runs.append_action(prepared["runId"], action)
            if result.get("ok") is not True:
                raise RuntimeError(f"fixture action 失败：{result}")
        finalized = await runs.finalize(prepared["runId"])
        report = finalized["result"]
        screenshot = next(item for item in report["artifacts"] if item.get("mediaType") == "image/png")
        detached = await sessions.detach("fixture")
        return {
            "ok": finalized.get("state") == "passed",
            "platform": sys.platform,
            "backend": "playwright-cdp",
            "targetCount": len(targets),
            "stepCount": report.get("summary", {}).get("stepCount"),
            "artifactCount": report.get("summary", {}).get("artifactCount"),
            "screenshotQuality": screenshot.get("quality"),
            "pending": finalized.get("pending"),
            "detached": detached.get("detached"),
        }
    finally:
        try:
            await driver.stop()
        finally:
            try:
                if context is not None:
                    await context.close()
            finally:
                await fixture_playwright.stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = asyncio.run(smoke(Path(args.work_dir).resolve()))
    write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
