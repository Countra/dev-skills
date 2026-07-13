"""实验矩阵、硬预算与预览 fingerprint。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .contracts import SuiteDocument, resolve_source
from .errors import SuiteError
from .snapshots import build_tree_manifest


LAB_ROOT = Path(__file__).resolve().parents[2]


def _skill_identity(path: Path) -> dict[str, Any]:
    manifest = build_tree_manifest(path)
    return {
        "path": str(path),
        "tree_sha256": manifest["tree_sha256"],
        "file_count": len(manifest["files"]),
    }


def implementation_identity() -> dict[str, Any]:
    """返回当前评测器实现树身份，用于授权与证据绑定。"""
    return _skill_identity(LAB_ROOT)


@dataclass
class RunBudget:
    """在启动外部调用前强制执行的 agent、judge 和总墙钟预算。"""

    max_agent_runs: int
    max_judge_runs: int
    max_wall_seconds: int
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)
    agent_runs: int = 0
    judge_runs: int = 0
    _started_at: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._started_at = self.clock()

    def remaining_seconds(self) -> float:
        return max(0.0, self.max_wall_seconds - (self.clock() - self._started_at))

    def ensure_time(self) -> None:
        if self.remaining_seconds() <= 0:
            raise SuiteError("实验已达到总墙钟预算", path="$.budgets.max_wall_seconds")

    def reserve_agent(self) -> None:
        self.ensure_time()
        if self.agent_runs >= self.max_agent_runs:
            raise SuiteError("实验已达到 agent run 预算", path="$.budgets.max_agent_runs")
        self.agent_runs += 1

    def reserve_judge(self) -> None:
        self.ensure_time()
        if self.judge_runs >= self.max_judge_runs:
            raise SuiteError("实验已达到 judge run 预算", path="$.budgets.max_judge_runs")
        self.judge_runs += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "agent_runs": self.agent_runs,
            "judge_runs": self.judge_runs,
            "remaining_seconds": round(self.remaining_seconds(), 3),
        }


def build_experiment_plan(suite: SuiteDocument) -> dict[str, Any]:
    runner = suite.data["runner"]
    matrix: list[dict[str, Any]] = []
    for case in suite.cases:
        repetitions = int(case.get("repetitions", runner["repetitions"]))
        for repetition in range(1, repetitions + 1):
            if case["mode"] == "trigger":
                variants = ["candidate"]
            else:
                variants = ["candidate", "baseline"] if repetition % 2 else ["baseline", "candidate"]
            for variant in variants:
                matrix.append(
                    {
                        "case_id": case["id"],
                        "mode": case["mode"],
                        "split": case["split"],
                        "repetition": repetition,
                        "variant": variant,
                    }
                )
    budgets = suite.data["budgets"]
    if len(matrix) > budgets["max_agent_runs"]:
        raise SuiteError(
            f"实验需要 {len(matrix)} 次 agent run，超过上限 {budgets['max_agent_runs']}",
            path="$.budgets.max_agent_runs",
        )
    root = suite.root
    candidate = resolve_source(root, suite.data["skill_path"], "$.skill_path")
    baseline = suite.data["baseline"]
    source_identity: dict[str, Any] = {"candidate": _skill_identity(candidate), "baseline": baseline["mode"]}
    if baseline["mode"] == "snapshot":
        source_identity["baseline"] = _skill_identity(resolve_source(root, baseline["path"], "$.baseline.path"))
    canonical_sources = {
        key: (
            {field: value for field, value in identity.items() if field != "path"}
            if isinstance(identity, dict)
            else identity
        )
        for key, identity in source_identity.items()
    }
    lab_identity = implementation_identity()
    canonical = {
        "suite": suite.data,
        "sources": canonical_sources,
        "lab": {field: value for field, value in lab_identity.items() if field != "path"},
        "matrix": matrix,
        "max_wall_seconds": budgets["max_wall_seconds"],
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "suite_id": suite.suite_id,
        "fingerprint": fingerprint,
        "runner": runner["adapter"],
        "agent_run_count": len(matrix),
        "judge_run_limit": budgets["max_judge_runs"],
        "max_wall_seconds": budgets["max_wall_seconds"],
        "execution_order": "serial-paired-alternating",
        "requested_concurrency": runner["concurrency"],
        "effective_concurrency": 1,
        "lab_identity": lab_identity,
        "source_identity": source_identity,
        "matrix": matrix,
    }
