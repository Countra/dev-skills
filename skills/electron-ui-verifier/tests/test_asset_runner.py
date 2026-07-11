"""Canonical asset 到 typed action/workflow 的 adapter 测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from ev_asset_runner import load_workflow_asset  # noqa: E402
from ev_common import EVError  # noqa: E402


class AssetRunnerTests(unittest.TestCase):
    def test_workflow_keeps_placeholders_and_injects_parameter_schema(self) -> None:
        asset = {
            "status": "approved",
            "assetId": "workflow-" + "a" * 40,
            "kind": "workflow",
            "appId": "demo",
            "goal": "填写名称",
            "payload": {
                "workflow": {
                    "goal": "填写名称",
                    "steps": [
                        {
                            "type": "fill",
                            "locator": {"label": "名称"},
                            "value": "${name}",
                            "postconditions": [{"type": "value", "locator": {"label": "名称"}, "expected": "${name}"}],
                        }
                    ],
                },
                "parameterSchema": {"name": {"type": "string", "required": True}},
            },
        }
        with mock.patch("ev_asset_runner.request_json", return_value={"ok": True, "asset": asset}):
            workflow, _, usage = load_workflow_asset(object(), asset["assetId"])
        self.assertEqual("${name}", workflow["steps"][0]["value"])
        self.assertIn("name", workflow["parameterSchema"])
        self.assertEqual(["name"], usage["requiredParams"])
        self.assertEqual({"name": {"type": "string", "required": True}}, usage["parameterSchema"])

    def test_kind_mismatch_fails_closed(self) -> None:
        asset = {
            "status": "approved",
            "assetId": "action-" + "b" * 40,
            "kind": "action",
            "appId": "demo",
            "goal": "保存",
            "payload": {"action": {"type": "snapshot"}},
        }
        with mock.patch("ev_asset_runner.request_json", return_value={"ok": True, "asset": asset}):
            with self.assertRaises(EVError):
                load_workflow_asset(object(), asset["assetId"])


if __name__ == "__main__":
    unittest.main()
