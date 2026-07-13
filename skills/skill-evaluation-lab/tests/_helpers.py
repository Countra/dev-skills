"""Skill Evaluation Lab 测试辅助。"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = SKILL_ROOT / "scripts"
REPO_ROOT = SKILL_ROOT.parents[1]
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@contextmanager
def temporary_workspace() -> Any:
    configured = os.environ.get("SKILL_EVAL_TEST_ROOT")
    parent = (
        Path(configured).resolve()
        if configured
        else REPO_ROOT / ".harness" / "test-tmp" / "skill-evaluation-lab" / "unit"
    )
    parent.mkdir(parents=True, exist_ok=True)
    temporary = parent / f"case-{uuid.uuid4().hex}"
    temporary.mkdir()
    try:
        yield temporary
    finally:
        shutil.rmtree(temporary, onerror=_remove_readonly)


def _remove_readonly(function: Any, path: str, _error: Any) -> None:
    """清理测试创建的只读快照文件。"""
    Path(path).chmod(stat.S_IWRITE)
    function(path)


def valid_suite(root: Path) -> dict[str, Any]:
    skill = root / "candidate"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: candidate\ndescription: Test skill.\n---\n\n# Candidate\n",
        encoding="utf-8",
    )
    return {
        "suite_id": "test-suite",
        "skill_path": "candidate",
        "baseline": {"mode": "none"},
        "runner": {
            "adapter": "fake",
            "model": "fake",
            "sandbox": "workspace-write",
            "timeout_seconds": 30,
            "repetitions": 1,
            "concurrency": 1,
            "network_access": False,
        },
        "budgets": {"max_agent_runs": 4, "max_judge_runs": 1, "max_wall_seconds": 120},
        "gates": {"trigger_threshold": 0.5, "required_case_pass_rate": 1.0, "judge_required": False},
        "cases": [
            {
                "id": "trigger-case",
                "mode": "trigger",
                "split": "validation",
                "prompt": "Use the candidate skill.",
                "inputs": [],
                "should_trigger": True,
            },
            {
                "id": "behavior-case",
                "mode": "behavior",
                "split": "train",
                "prompt": "Create outputs/result.json.",
                "inputs": [],
                "assertions": [{"id": "result-exists", "type": "file_exists", "path": "outputs/result.json"}],
            },
        ],
    }
