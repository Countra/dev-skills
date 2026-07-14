#!/usr/bin/env python3
"""汇总 verifier 的阶段性性能门禁。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = (ROOT / ".harness").resolve()
SCRIPTS = ROOT / "skills" / "electron-ui-verifier" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.atomic_io import canonical_json_bytes  # noqa: E402
from performance_support import knowledge_performance  # noqa: E402


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_throughput() -> dict[str, Any]:
    value = {
        "runId": "00000000-0000-0000-0000-000000000000",
        "steps": [{"id": f"step-{index}", "status": "passed", "durationMs": index} for index in range(200)],
    }
    started = time.perf_counter()
    iterations = 1000
    size = 0
    for _ in range(iterations):
        size = len(canonical_json_bytes(value))
    elapsed = time.perf_counter() - started
    return {
        "iterations": iterations,
        "documentBytes": size,
        "elapsedMs": round(elapsed * 1000, 3),
        "documentsPerSecond": round(iterations / elapsed, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()
    work_dir = Path(args.work_dir).resolve()
    if work_dir == HARNESS_ROOT or HARNESS_ROOT not in work_dir.parents:
        raise SystemExit("--work-dir 必须位于当前仓库 .harness 的隔离子目录")
    task_dir = work_dir.parent.parent
    termous_path = task_dir / "artifacts" / "validation" / "termous-smoke.json"
    failures: list[str] = []
    termous: dict[str, Any] = {"available": False}
    if termous_path.exists():
        evidence = json.loads(termous_path.read_text(encoding="utf-8"))
        driver = evidence.get("checks", {}).get("driver", {})
        screenshots = driver.get("screenshots", {})
        run = driver.get("run", {})
        termous = {
            "available": True,
            "successCount": screenshots.get("successCount"),
            "p95Ms": screenshots.get("p95Ms"),
            "limitMs": 2000,
            "qualityVerified": screenshots.get("qualityVerified"),
            "runStepCount": run.get("stepCount"),
            "runArtifactCount": run.get("artifactCount"),
            "reportIdempotent": run.get("reportIdempotent"),
            "pending": run.get("pending"),
        }
        if screenshots.get("successCount") != 10:
            failures.append("Termous screenshot successCount 不为 10")
        if float(screenshots.get("p95Ms", 999999)) > 2000:
            failures.append("Termous screenshot P95 超过 2 秒")
        if screenshots.get("qualityVerified") is not True:
            failures.append("Termous screenshot quality 未全部验证")
        if run.get("reportIdempotent") is not True or run.get("pending") is not None:
            failures.append("Termous read-only run finalize/pending 契约未闭环")
    else:
        failures.append("缺少 Termous 性能证据")
    knowledge, knowledge_failures = knowledge_performance(work_dir)
    failures.extend(knowledge_failures)
    result = {
        "ok": not failures,
        "termousScreenshot": termous,
        "knowledge": knowledge,
        "canonicalSerialization": canonical_throughput(),
        "failures": failures,
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    write_json(task_dir / "artifacts" / "validation" / "performance.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
