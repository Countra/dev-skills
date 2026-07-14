#!/usr/bin/env python3
"""验证 skill 渐进披露、公共 CLI、示例与紧凑 prepare 知识输出。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "electron-ui-verifier"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.knowledge_models import CanonicalAsset  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from electron_verifier.models import ActionSpec  # noqa: E402
from electron_verifier.retrieval import HybridRetriever  # noqa: E402


PUBLIC_CLIS = (
    "ev_action.py", "ev_artifact.py", "ev_asset_extract.py", "ev_assets.py", "ev_attach.py",
    "ev_check_env.py", "ev_console.py", "ev_detach.py", "ev_doctor.py", "ev_exceptions.py",
    "ev_export_workflow.py", "ev_finalize.py", "ev_health.py", "ev_init.py", "ev_knowledge.py",
    "ev_network.py", "ev_pending.py", "ev_persist.py", "ev_prepare.py", "ev_probe.py",
    "ev_report.py", "ev_screenshot.py", "ev_server.py", "ev_sessions.py", "ev_snapshot.py",
    "ev_suggest.py", "ev_workflow.py",
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cli_help(name: str, extra: tuple[str, ...] = ()) -> dict[str, Any]:
    command = [sys.executable, "-X", "utf8", "-B", str(SCRIPTS / name), *extra, "--help"]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=20, check=False)
    return {
        "script": name,
        "extra": list(extra),
        "returnCode": completed.returncode,
        "stdoutBytes": len(completed.stdout.encode("utf-8")),
        "stderr": completed.stderr[:500],
    }


def compact_retrieval(work_dir: Path) -> dict[str, Any]:
    state = work_dir / "state"
    KnowledgeReset(state).ensure()
    store = CanonicalStore(state)
    assets = []
    for index in range(12):
        assets.append(
            CanonicalAsset.create(
                kind="workflow",
                app_id="eval-app",
                goal=f"打开设置面板 {index}",
                aliases=[f"Open settings panel {index}"],
                payload={"workflow": {"goal": f"打开设置面板 {index}", "steps": [{"type": "snapshot"}]}},
                evidence=[{"reportDigest": f"{index % 10}" * 64}],
                created_at="2026-07-11T00:00:00Z",
            )
        )
    store.activate(assets)
    with HybridRetriever(store) as retriever:
        result = retriever.search("Please open settings panel 3", {"appId": "eval-app"})
    return {
        "decision": result["decision"],
        "candidateCount": len(result["candidates"]),
        "stdoutBytes": len(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")),
    }


def validate_assets() -> dict[str, Any]:
    checked = []
    for path in sorted((SKILL / "assets").glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("steps"), list) or not value["steps"]:
            raise ValueError(f"workflow example 无效：{path.name}")
        for action in value["steps"]:
            ActionSpec.decode(action)
        checked.append({"name": path.name, "stepCount": len(value["steps"])})
    return {"count": len(checked), "files": checked}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()
    work_dir = Path(args.work_dir).resolve()
    if ROOT not in work_dir.parents:
        raise SystemExit("--work-dir 必须位于当前仓库内")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    failures: list[str] = []
    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    references = ["server.md", "actions.md", "workflow.md", "knowledge.md", "troubleshooting.md"]
    progressive = {
        "skillLines": len(skill_text.splitlines()),
        "referencesLinked": all(f"references/{name}" in skill_text for name in references),
        "conditionalLoading": "不要在普通任务中预先加载全部 references" in skill_text,
        "coreFlow": all(item in skill_text for item in ("ev_prepare.py", "ev_finalize.py", "bundleFingerprint", "abstain")),
        "rawFallbackAbsent": "raw CDP fallback" not in skill_text and "raw WebSocket/CDP fallback" in skill_text,
    }
    if progressive["skillLines"] > 500 or not all(value for key, value in progressive.items() if key != "skillLines"):
        failures.append("SKILL progressive disclosure 契约失败")
    help_results = [cli_help(name) for name in PUBLIC_CLIS]
    help_results.extend(
        [
            cli_help("ev_knowledge.py", ("search",)),
            cli_help("ev_knowledge.py", ("compose",)),
            cli_help("ev_assets.py", ("list",)),
        ]
    )
    bad_help = [item["script"] for item in help_results if item["returnCode"] != 0 or item["stdoutBytes"] == 0]
    if bad_help:
        failures.append(f"CLI help 失败：{bad_help}")
    try:
        assets = validate_assets()
    except Exception as exc:
        assets = {"error": f"{type(exc).__name__}: {exc}"}
        failures.append("typed workflow examples 无法 decode")
    compact = compact_retrieval(work_dir / "compact")
    if compact["decision"] != "reuse" or compact["candidateCount"] > 3 or compact["stdoutBytes"] > 16 * 1024:
        failures.append("prepare knowledge 输出不满足 compact contract")
    result = {
        "ok": not failures,
        "progressiveDisclosure": progressive,
        "cliHelp": help_results,
        "assets": assets,
        "compactKnowledge": compact,
        "failures": failures,
    }
    task_dir = work_dir.parent.parent
    write_json(task_dir / "artifacts" / "validation" / "skill-evals.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
