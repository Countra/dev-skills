"""Run report、summary 与 artifact 的受控读取。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .atomic_io import resolve_under
from .errors import VerifierError


def finalize_result(
    journal: dict[str, Any],
    report: dict[str, Any],
    report_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    return {
        "ok": report.get("status") == "passed",
        "runId": journal["runId"],
        "state": journal["state"],
        "report": str(report_path),
        "summary": str(summary_path),
        "pending": journal.get("pending"),
        "result": report,
    }


def get_report(state_root: Path, value: str) -> dict[str, Any]:
    path = resolve_under(state_root, Path(value), must_exist=True)
    if path.name != "report.json":
        raise VerifierError("invalid_report_path", "report path 必须指向 report.json")
    return {"ok": True, "report": str(path), "result": json.loads(path.read_text(encoding="utf-8"))}


def latest_report(runs_dir: Path, state_root: Path, session: str) -> dict[str, Any]:
    candidates = []
    for path in runs_dir.glob("*/journal.json"):
        try:
            journal = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if session not in {journal.get("sessionId"), journal.get("sessionName")} or not journal.get("report"):
            continue
        candidates.append(journal)
    if not candidates:
        raise VerifierError("report_not_found", f"session 尚无 finalized report：{session}", status=404)
    latest = max(candidates, key=lambda item: str(item.get("updatedAt") or ""))
    return get_report(state_root, str(latest["report"]))


def get_artifact(state_root: Path, value: str) -> dict[str, Any]:
    path = resolve_under(state_root, Path(value), must_exist=True)
    if not path.is_file():
        raise VerifierError("invalid_artifact_path", "artifact path 必须是文件")
    return {"ok": True, "artifact": str(path), "bytes": path.stat().st_size}
