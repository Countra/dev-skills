"""提供知识库性能评测的共享夹具与门禁。"""

from __future__ import annotations

import shutil
import statistics
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "electron-ui-verifier" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.knowledge_models import CanonicalAsset  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from electron_verifier.retrieval import HybridRetriever  # noqa: E402
from knowledge_fixtures import action_asset, runtime_context  # noqa: E402


INGEST_BASELINE_MS = 4480.26
INGEST_LIMIT_MS = 1500.0
INGEST_COLD_LIMIT_MS = 3000.0
INGEST_SAMPLE_COUNT = 3
QUERY_LIMIT_MS = 100.0


def knowledge_performance(work_dir: Path) -> tuple[dict[str, Any], list[str]]:
    """测量真实规模知识库的摄取与查询性能。"""
    assets: list[CanonicalAsset] = []
    cases: list[tuple[str, str, str]] = []
    for index in range(308):
        app_id = f"perf-app-{index % 14}"
        goal = f"Execute operation {index}"
        alias = f"Run task code {index}"
        asset = action_asset(app_id, goal, [alias], success_count=5, evidence_digest="d" * 64)
        assets.append(asset)
        cases.append((app_id, alias, asset.asset_id))

    ingest_samples: list[float] = []
    states: list[Path] = []
    store: CanonicalStore | None = None
    for sample in range(INGEST_SAMPLE_COUNT):
        state = work_dir / f"knowledge-state-{sample + 1}"
        if state.exists():
            shutil.rmtree(state)
        KnowledgeReset(state).ensure()
        current_store = CanonicalStore(state)
        started = time.perf_counter()
        current_store.activate(assets)
        ingest_samples.append((time.perf_counter() - started) * 1000)
        states.append(state)
        store = current_store

    if store is None:
        raise RuntimeError("知识性能基准未生成可查询状态")
    for stale_state in states[:-1]:
        shutil.rmtree(stale_state)

    ingest_ms = statistics.median(ingest_samples)
    cold_ingest_ms = max(ingest_samples)
    timings: list[float] = []
    query_failures = 0
    with HybridRetriever(store) as retriever:
        for index in range(10000):
            app_id, query, expected = cases[index % len(cases)]
            query_started = time.perf_counter_ns()
            result = retriever.search(query, runtime_context(app_id), limit=3)
            timings.append((time.perf_counter_ns() - query_started) / 1_000_000)
            if (
                result["decision"] != "reuse"
                or not result["candidates"]
                or result["candidates"][0]["assetId"] != expected
            ):
                query_failures += 1

    timings.sort()
    p95_ms = timings[max(0, int(len(timings) * 0.95) - 1)]
    speedup = INGEST_BASELINE_MS / ingest_ms
    failures = []
    if ingest_ms > INGEST_LIMIT_MS:
        failures.append("308 asset ingestion 中位数超过 1.5 秒")
    if cold_ingest_ms > INGEST_COLD_LIMIT_MS:
        failures.append("308 asset cold ingestion 超过 3 秒")
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
            "ingestSamplesMs": [round(value, 3) for value in ingest_samples],
            "ingestLimitMs": INGEST_LIMIT_MS,
            "ingestColdLimitMs": INGEST_COLD_LIMIT_MS,
            "baselineMs": INGEST_BASELINE_MS,
            "speedup": round(speedup, 3),
            "queryCount": len(timings),
            "queryP95Ms": round(p95_ms, 3),
            "queryLimitMs": QUERY_LIMIT_MS,
            "queryFailures": query_failures,
        },
        failures,
    )
