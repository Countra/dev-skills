#!/usr/bin/env python3
"""验证 Process Manager 消费者契约按职责独立检查。"""

from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from run_static_checks import check_process_consumers


PLANNER = "skills/complex-coding-planner/SKILL.md"
EXECUTOR_SKILL = "skills/complex-coding-executor/SKILL.md"
EXECUTOR_SAFETY = (
    "skills/complex-coding-executor/references/execution-safety.md"
)
EXECUTOR_WORKFLOW = (
    "skills/complex-coding-executor/references/execution-workflow.md"
)
ELECTRON_SKILL = "skills/electron-ui-verifier/SKILL.md"
ELECTRON_SERVER = "skills/electron-ui-verifier/references/server.md"
ELECTRON_TROUBLESHOOTING = (
    "skills/electron-ui-verifier/references/troubleshooting.md"
)
ELECTRON_SUPPORT = (
    "skills/electron-ui-verifier/tests/public_contract_support.py"
)
ELECTRON_SMOKE = (
    "skills/electron-ui-verifier/tests/run_process_manager_smoke.py"
)
TEMP_ROOT = (
    Path(__file__).resolve().parents[2]
    / ".harness"
    / "test-tmp"
    / "process-manager-consumer-contract"
)


class ProcessConsumerContractTest(unittest.TestCase):
    def setUp(self) -> None:
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.root = TEMP_ROOT / f"case-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self._write_defaults()

    def _write(self, relative_path: str, text: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_defaults(self) -> None:
        self._write(
            PLANNER,
            "长期进程由 process-manager 托管并规划 readiness 和 cleanup。\n"
            "有限命令只设置 deadline，不进入 Process Manager。\n",
        )
        self._write(EXECUTOR_SKILL, "长期进程使用 process-manager。\n")
        self._write(
            EXECUTOR_SAFETY,
            "有限命令不进入 Process Manager。\n"
            "pm_manager.py ensure 后运行 pm_session.py open，随后使用 "
            "pm_start.py --session-id。\n"
            "finally 运行 pm_session.py close --stop-manager-if-idle，确认 "
            "owner-empty。\n"
            "恢复先运行 pm_manager.py status，再按 recommendedAction 处理，"
            "不自动提权。\n",
        )
        self._write(EXECUTOR_WORKFLOW, "恢复时核对长期进程所有权。\n")
        self._write(ELECTRON_SKILL, "verifier service 使用 process-manager。\n")
        self._write(
            ELECTRON_SERVER,
            "pm_manager.py ensure；pm_session.py open；使用 --session-id 启动；"
            "最后 pm_session.py close --stop-manager-if-idle。\n",
        )
        self._write(
            ELECTRON_TROUBLESHOOTING,
            "按 recommendedAction 恢复；外层错误不得猜成 ACL 问题或自动提权。\n",
        )
        self._write(
            ELECTRON_SUPPORT,
            'call("pm_manager.py", "ensure")\n'
            'call("pm_session.py", "open", "--session-id", session_id)\n'
            'call("pm_session.py", "close", "--stop-manager-if-idle")\n',
        )
        self._write(
            ELECTRON_SMOKE,
            "try:\n"
            "    run_service()\n"
            "finally:\n"
            "    assert cleanupVerified\n"
            "    assert ownerEmpty\n",
        )

    def _check(self) -> tuple[list[str], dict]:
        failures: list[str] = []
        result = check_process_consumers(failures, self.root)
        return failures, result

    def test_current_contract_passes_by_group(self) -> None:
        failures, result = self._check()

        self.assertEqual(failures, [])
        self.assertEqual(result["file_count"], 9)
        self.assertEqual(
            set(result["groups"]),
            {"planner", "executor", "electron-docs", "electron-runtime"},
        )

    def test_other_groups_cannot_mask_planner_requirement(self) -> None:
        self._write(
            PLANNER,
            "长期进程由 process-manager 托管并规划 cleanup。\n"
            "有限命令只设置 deadline，不进入 Process Manager。\n",
        )
        self._write(EXECUTOR_WORKFLOW, "Executor 明确包含 readiness。\n")

        failures, result = self._check()

        self.assertEqual(
            result["groups"]["planner"]["missing"],
            ["planner:long-running-process-ownership"],
        )
        self.assertEqual(result["groups"]["executor"]["missing"], [])
        self.assertTrue(any("planner:long-running-process-ownership" in item for item in failures))

    def test_executor_recovery_and_privilege_are_independent(self) -> None:
        path = self.root / EXECUTOR_SAFETY
        text = path.read_text(encoding="utf-8")
        text = text.replace("recommendedAction", "next action")
        text = text.replace("不自动提权", "不改变权限")
        path.write_text(text, encoding="utf-8")

        _, result = self._check()

        self.assertEqual(
            result["groups"]["executor"]["missing"],
            ["executor:status-recovery", "executor:privilege-boundary"],
        )
        self.assertEqual(result["groups"]["planner"]["missing"], [])

    def test_electron_runtime_requires_session_binding(self) -> None:
        path = self.root / ELECTRON_SUPPORT
        text = path.read_text(encoding="utf-8").replace("--session-id", "--lease")
        path.write_text(text, encoding="utf-8")

        _, result = self._check()

        self.assertEqual(result["groups"]["electron-docs"]["missing"], [])
        self.assertEqual(
            result["groups"]["electron-runtime"]["missing"],
            ["electron-runtime:session-binding"],
        )

    def test_missing_current_file_reports_group_and_path(self) -> None:
        (self.root / PLANNER).unlink()

        failures, result = self._check()

        self.assertEqual(
            result["groups"]["planner"]["missing_files"],
            [PLANNER],
        )
        self.assertTrue(any("consumer planner 读取失败" in item for item in failures))

    def test_legacy_entry_is_scoped_to_owning_group(self) -> None:
        path = self.root / EXECUTOR_WORKFLOW
        path.write_text("恢复时调用 pm_health.py。\n", encoding="utf-8")

        _, result = self._check()

        self.assertEqual(
            result["groups"]["executor"]["forbidden"],
            ["executor:pm_health.py"],
        )
        self.assertEqual(result["groups"]["planner"]["forbidden"], [])


if __name__ == "__main__":
    unittest.main()
