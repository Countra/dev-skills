"""Skill Evaluation Lab 当前协议的测试辅助。"""

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
    """清理测试创建的只读文件。"""
    Path(path).chmod(stat.S_IWRITE)
    function(path)


def write_skill(
    workspace: Path,
    name: str = "candidate-skill",
    *,
    description: str = "用于测试静态契约和明确触发边界的示例 Skill。",
    body: str = "# Candidate Skill\n\n按步骤检查输入，并返回可验证的结果。\n",
) -> Path:
    source = workspace / "skills" / name
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}",
        encoding="utf-8",
    )
    (source / "scripts").mkdir()
    (source / "scripts" / "check.py").write_text(
        '"""测试用只读检查。"""\n\nfrom pathlib import Path\n\n\ndef inspect(path: Path) -> bool:\n'
        "    return path.is_file()\n",
        encoding="utf-8",
    )
    (source / "tests").mkdir()
    (source / "tests" / "test_check.py").write_text("# 测试占位由外部测试驱动。\n", encoding="utf-8")
    (workspace / "evals" / name).mkdir(parents=True)
    workflow = workspace / ".github" / "workflows" / f"{name}.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(f"name: {name}\n", encoding="utf-8")
    return source


def valid_suite(
    *,
    candidate: str = "skills/candidate-skill",
    baseline: str | None = None,
) -> dict[str, Any]:
    variants = ["candidate"] + (["baseline"] if baseline else [])
    return {
        "schema_version": 1,
        "suite_id": "contract-suite",
        "candidate": candidate,
        "baseline": baseline,
        "decision_question": "该 Skill 的触发边界和工作流是否足够清晰？",
        "observation_policy": {
            "required_variants": variants,
            "require_independent_session": True,
        },
        "cases": [
            {
                "id": "positive-case",
                "kind": "trigger-positive",
                "prompt": "请使用该 Skill 评估一个 Skill。",
                "expected_observation": "应触发并遵循完整评估工作流。",
                "inputs": [],
            },
            {
                "id": "near-miss-case",
                "kind": "trigger-near-miss",
                "prompt": "请运行普通项目单元测试。",
                "expected_observation": "不应仅因普通测试任务而触发。",
                "inputs": [],
            },
            {
                "id": "behavior-case",
                "kind": "behavior",
                "prompt": "请静态审查给定 Skill 并说明证据边界。",
                "expected_observation": "应区分静态事实、语义判断和未观察行为。",
                "inputs": [],
            },
        ],
    }


def valid_semantic_review(evaluation_id: str, tree_sha256: str) -> dict[str, Any]:
    from skill_evaluation_lab.contracts import SEMANTIC_DIMENSIONS

    return {
        "schema_version": 1,
        "evaluation_id": evaluation_id,
        "candidate_tree_sha256": tree_sha256,
        "dimensions": [
            {
                "dimension": dimension,
                "status": "pass",
                "summary": f"{dimension} 已依据静态 source 完成审查。",
                "evidence": [{"path": "SKILL.md", "detail": "工作流包含可检查的边界。"}],
            }
            for dimension in SEMANTIC_DIMENSIONS
        ],
        "assumptions": [],
        "limitations": ["未导入用户独立会话观察，不能声明真实触发率。"],
        "observation_decision": "not_requested",
    }
