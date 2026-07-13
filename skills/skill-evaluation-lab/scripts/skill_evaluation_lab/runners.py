"""Runner 的稳定请求、结果和调用前门禁。"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .budgets import RunBudget
from .errors import AuthorizationError, InconclusiveError, SuiteError
from .snapshots import build_tree_manifest


@dataclass(frozen=True)
class RunRequest:
    """一次 agent run 的完整、可审计输入。"""

    run_id: str
    case_id: str
    attempt: int
    prompt: str
    workspace: Path
    artifact_dir: Path
    model: str
    sandbox: str
    timeout_seconds: int
    fingerprint: str
    lab_tree_sha256: str
    approved_fingerprint: str | None
    live_authorized: bool
    network_access: bool = False
    previous_outcome: str = "not_started"
    skill_path: Path | None = None
    variant: str = "candidate"


@dataclass(frozen=True)
class RunResult:
    """Adapter 返回的中立结果；评分逻辑不属于 runner。"""

    outcome: str
    return_code: int
    final: dict[str, Any]
    trace_path: Path | None
    stderr_path: Path | None
    duration_seconds: float | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    observation: dict[str, Any] = field(default_factory=dict)


class RunnerAdapter(Protocol):
    def run(self, request: RunRequest, budget: RunBudget) -> RunResult:
        """执行一次有预算约束的 agent run。"""


def validate_live_request(request: RunRequest) -> None:
    """在任何模型调用前执行授权、fingerprint 和隔离门禁。"""
    if not request.live_authorized:
        raise AuthorizationError(
            "live run 尚未获得显式授权",
            guidance="先预览实验 fingerprint、调用数与模型，再明确授权本次有限调用",
        )
    if not request.approved_fingerprint or request.approved_fingerprint != request.fingerprint:
        raise AuthorizationError(
            "批准的 fingerprint 与当前实验不匹配",
            guidance="重新运行 dry-run 并批准新的 fingerprint",
        )
    if request.previous_outcome == "unknown":
        raise InconclusiveError(
            "上一 attempt 的结果未知，禁止隐式重试",
            guidance="先核对 trace、usage 和外部调用状态，再显式决定是否启动新 attempt",
        )
    if request.sandbox not in {"read-only", "workspace-write"}:
        raise SuiteError("runner 禁止 danger-full-access", path="$.runner.sandbox")
    if request.network_access:
        raise SuiteError("首版 case 必须关闭网络", path="$.runner.network_access")
    if request.attempt < 1:
        raise SuiteError("attempt 必须是正整数", path="$.attempt")


class FakeRunner:
    """供离线测试使用的确定性 adapter，不触发模型调用。"""

    def __init__(self, scripted: dict[str, dict[str, Any]] | None = None) -> None:
        self._scripted = scripted or {}

    def run(self, request: RunRequest, budget: RunBudget) -> RunResult:
        started_at = time.monotonic()
        budget.reserve_agent()
        value = self._scripted.get(request.case_id, {})
        skill_manifest = build_tree_manifest(request.skill_path) if request.skill_path is not None else None
        return RunResult(
            outcome=str(value.get("outcome", "passed")),
            return_code=int(value.get("return_code", 0)),
            final=dict(value.get("final", {})),
            trace_path=None,
            stderr_path=None,
            duration_seconds=max(0.0, time.monotonic() - started_at),
            usage={"input_tokens": 0, "output_tokens": 0},
            provenance={
                "adapter": "fake",
                "cli_version": "fake",
                "model": request.model,
                "sandbox": request.sandbox,
                "network_access": request.network_access,
                "fingerprint": request.fingerprint,
                "lab_tree_sha256": request.lab_tree_sha256,
                "prompt_sha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
                "case_id": request.case_id,
                "attempt": request.attempt,
                "variant": request.variant,
                **(
                    {"skill_tree_sha256": skill_manifest["tree_sha256"]}
                    if skill_manifest is not None
                    else {}
                ),
            },
            observation=dict(value.get("observation", {})),
        )
