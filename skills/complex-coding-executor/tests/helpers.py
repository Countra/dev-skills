"""Executor 单测的跨平台可写临时目录。"""

from __future__ import annotations

import json
import os
import shutil
import stat
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_TEMP_ROOT = REPO_ROOT / ".harness" / "test-tmp" / "complex-coding-executor-tests"


class WritableTemporaryDirectory:
    """避免 Windows 私有临时目录 ACL 干扰测试子进程。"""

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

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.cleanup()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def compact_contract(
    *,
    task_id: str = "executor-task",
    risk: str = "medium",
    two_stages: bool = False,
) -> dict:
    review = "independent" if risk == "high" else "same-context"
    stages = [
        {
            "id": "STG-01",
            "title": "实现核心行为",
            "depends_on": [],
            "scope": ["skills/example"],
            "risk": risk,
            "validation_ids": ["VAL-01"],
            "review": review,
        }
    ]
    validations = [
        {
            "id": "VAL-01",
            "stage_id": "STG-01",
            "command": "python -m unittest",
            "required": True,
            "timeout_seconds": 300,
        }
    ]
    final_validation_ids: list[str] = []
    if two_stages:
        stages.append(
            {
                "id": "STG-02",
                "title": "完成集成",
                "depends_on": ["STG-01"],
                "scope": ["skills/example"],
                "risk": "medium",
                "validation_ids": ["VAL-02"],
                "review": "same-context",
            }
        )
        validations.append(
            {
                "id": "VAL-02",
                "stage_id": "STG-02",
                "command": "python -m unittest integration",
                "required": True,
                "timeout_seconds": 300,
            }
        )
        validations.append(
            {
                "id": "VAL-FINAL",
                "stage_id": "final",
                "command": "python -m unittest integration",
                "required": True,
                "timeout_seconds": 300,
            }
        )
        final_validation_ids.append("VAL-FINAL")
    return {
        "task_id": task_id,
        "plan_revision": 1,
        "risk": risk,
        "scope": ["skills/example"],
        "stages": stages,
        "validations": validations,
        "final_validation_ids": final_validation_ids,
        "final_review": review,
        "permissions_requested": {
            "commit": False,
            "external_write": False,
            "elevated_tool": False,
        },
    }


def write_workspace_bundle(workspace: Path, contract: dict | None = None) -> Path:
    value = contract or compact_contract()
    task_dir = workspace / ".harness" / "tasks" / "2026-07-22" / "feature" / value["task_id"]
    task_dir.mkdir(parents=True, exist_ok=True)
    write_json(task_dir / "plan-contract.json", value)
    ids = [item["id"] for item in value["stages"]] + [
        item["id"] for item in value["validations"]
    ]
    task_dir.joinpath("execution-plan.md").write_text(
        "# Executor task\n\n" + "\n".join(f"- {item}" for item in ids) + "\n",
        encoding="utf-8",
    )
    write_json(
        workspace / ".harness" / "active-task.json",
        {
            "task_id": value["task_id"],
            "task_dir": task_dir.relative_to(workspace).as_posix(),
            "updated_at": "2026-07-22T00:00:00+00:00",
        },
    )
    return task_dir
