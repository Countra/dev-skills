#!/usr/bin/env python3
"""汇总 verifier 的阶段性性能门禁。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "electron-ui-verifier" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.atomic_io import canonical_json_bytes  # noqa: E402
from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.knowledge_models import CanonicalAsset  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from electron_verifier.retrieval import HybridRetriever  # noqa: E402


INGEST_BASELINE_MS = 4480.26
INGEST_LIMIT_MS = 1500.0
QUERY_LIMIT_MS = 100.0


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


def knowledge_performance(work_dir: Path) -> tuple[dict[str, Any], list[str]]:
    state = work_dir / "knowledge-state"
    if state.exists():
        shutil.rmtree(state)
    KnowledgeReset(state).ensure()
    store = CanonicalStore(state)
    assets: list[CanonicalAsset] = []
    cases: list[tuple[str, str, str]] = []
    for index in range(308):
        app_id = f"perf-app-{index % 14}"
        goal = f"Execute operation {index}"
        alias = f"Run task code {index}"
        asset = CanonicalAsset.create(
            kind="workflow",
            app_id=app_id,
            goal=goal,
            aliases=[alias],
            payload={
                "workflow": {"schemaVersion": 1, "appId": app_id, "goal": goal, "steps": [{"type": "snapshot"}]},
                "stats": {"successCount": 5, "failureCount": 0},
            },
            evidence=[{"reportDigest": "d" * 64}],
            created_at="2026-07-11T00:00:00Z",
        )
        assets.append(asset)
        cases.append((app_id, alias, asset.asset_id))
    started = time.perf_counter()
    store.activate(assets)
    ingest_ms = (time.perf_counter() - started) * 1000
    timings: list[float] = []
    query_failures = 0
    with HybridRetriever(store) as retriever:
        for index in range(10000):
            app_id, query, expected = cases[index % len(cases)]
            query_started = time.perf_counter_ns()
            result = retriever.search(query, {"appId": app_id}, limit=3)
            timings.append((time.perf_counter_ns() - query_started) / 1_000_000)
            if result["decision"] != "reuse" or not result["candidates"] or result["candidates"][0]["assetId"] != expected:
                query_failures += 1
    timings.sort()
    p95_ms = timings[max(0, int(len(timings) * 0.95) - 1)]
    speedup = INGEST_BASELINE_MS / ingest_ms
    failures = []
    if ingest_ms > INGEST_LIMIT_MS:
        failures.append("308 asset ingestion 超过 1.5 秒")
    if speedup < 3.0:
        failures.append("308 asset ingestion 未达到基线 3 倍加速")
    if p95_ms > QUERY_LIMIT_MS:
        failures.append("10k query P95 超过 100ms")
    if query_failures:
        failures.append(f"10k query 出现 {query_failures} 次错误命中")
    return (
        {
            "assetCount": len(assets),
            "ingestMs": round(ingest_ms, 3),
            "ingestLimitMs": INGEST_LIMIT_MS,
            "baselineMs": INGEST_BASELINE_MS,
            "speedup": round(speedup, 3),
            "queryCount": len(timings),
            "queryP95Ms": round(p95_ms, 3),
            "queryLimitMs": QUERY_LIMIT_MS,
            "queryFailures": query_failures,
        },
        failures,
    )
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()
    work_dir = Path(args.work_dir).resolve()
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
