"""Planner 单测的跨平台可写临时目录。"""

from __future__ import annotations

import os
import json
import shutil
import stat
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_TEMP_ROOT = REPO_ROOT / ".harness" / "test-tmp" / "complex-coding-planner-tests"


class WritableTemporaryDirectory:
    """避免 Windows 私有临时目录 ACL 干扰测试文件访问。"""

    def __init__(self) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.path = TEST_TEMP_ROOT / f"case-{uuid.uuid4().hex}"
        self.path.mkdir(mode=0o777)
        self.name = str(self.path)

    def cleanup(self) -> None:
        if not self.path.exists():
            return

        def remove_readonly(function, target, _error):
            os.chmod(target, stat.S_IWRITE)
            function(target)

        shutil.rmtree(self.path, onerror=remove_readonly)


def compact_contract(*, task_id: str = "compact-task", risk: str = "medium") -> dict:
    """返回测试使用的最小合法 contract。"""

    review = "independent" if risk == "high" else "same-context"
    return {
        "task_id": task_id,
        "plan_revision": 1,
        "risk": risk,
        "scope": ["skills/example"],
        "stages": [
            {
                "id": "STG-01",
                "title": "实现核心行为",
                "depends_on": [],
                "scope": ["skills/example"],
                "risk": risk,
                "validation_ids": ["VAL-01"],
                "review": review,
            }
        ],
        "validations": [
            {
                "id": "VAL-01",
                "stage_id": "STG-01",
                "command": "python -m unittest",
                "required": True,
                "timeout_seconds": 300,
            }
        ],
        "final_review": review,
        "permissions_requested": {
            "commit": False,
            "external_write": False,
            "elevated_tool": False,
        },
    }


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_bundle(task_dir: Path, contract: dict | None = None) -> dict:
    value = contract or compact_contract()
    task_dir.mkdir(parents=True, exist_ok=True)
    write_json(task_dir / "plan-contract.json", value)
    stage_ids = [item["id"] for item in value["stages"]]
    validation_ids = [item["id"] for item in value["validations"]]
    task_dir.joinpath("execution-plan.md").write_text(
        "# Compact task\n\n"
        "## 实施阶段\n\n"
        + "\n".join(f"- {item}" for item in stage_ids)
        + "\n\n## 验证\n\n"
        + "\n".join(f"- {item}" for item in validation_ids)
        + "\n",
        encoding="utf-8",
    )
    return value
