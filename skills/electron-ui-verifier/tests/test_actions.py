"""Strict locator、单次副作用和 postcondition 测试。"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.actions import execute_action  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.models import ActionSpec  # noqa: E402


class FakeLocator:
    def __init__(self, count: int = 1, fail_wait: bool = False) -> None:
        self._count = count
        self.fail_wait = fail_wait
        self.clicks: list[bool] = []
        self.value = ""

    async def count(self) -> int:
        return self._count

    def nth(self, index: int):
        return self

    async def evaluate(self, expression: str):
        return {"tag": "button", "role": "button", "name": "保存", "disabled": False}

    async def bounding_box(self):
        return {"x": 1, "y": 1, "width": 20, "height": 10}

    async def is_visible(self) -> bool:
        return True

    async def is_enabled(self, timeout=None) -> bool:
        return True

    async def is_editable(self, timeout=None) -> bool:
        return True

    async def wait_for(self, state: str, timeout: int) -> None:
        if self.fail_wait:
            raise RuntimeError("postcondition did not become visible")
        return None

    async def click(self, *, trial: bool = False, timeout: int) -> None:
        self.clicks.append(trial)

    async def fill(self, value: str, *, timeout: int) -> None:
        self.value = value

    async def input_value(self, timeout: int) -> str:
        return self.value


class FakePage:
    url = "file:///private/app/index.html"

    def __init__(self, locator: FakeLocator) -> None:
        self.locator_value = locator

    def get_by_role(self, role: str, **options):
        return self.locator_value

    def get_by_label(self, value: str, **options):
        return self.locator_value

    async def title(self) -> str:
        return "Demo"


class ActionTests(unittest.TestCase):
    def test_ambiguous_click_does_not_execute(self) -> None:
        locator = FakeLocator(count=2)
        live = SimpleNamespace(page=FakePage(locator))
        action = ActionSpec.decode(
            {
                "type": "click",
                "locator": {"role": "button", "accessibleName": "保存"},
                "postconditions": [{"type": "visible", "locator": {"role": "button", "accessibleName": "保存"}}],
            }
        )
        with self.assertRaises(VerifierError) as caught:
            asyncio.run(execute_action(live, action))
        self.assertEqual("ambiguous_locator", caught.exception.code)
        self.assertEqual([], locator.clicks)

    def test_click_trials_then_commits_exactly_once(self) -> None:
        locator = FakeLocator()
        live = SimpleNamespace(page=FakePage(locator))
        action = ActionSpec.decode(
            {
                "type": "click",
                "locator": {"role": "button", "accessibleName": "保存"},
                "postconditions": [{"type": "visible", "locator": {"role": "button", "accessibleName": "保存"}}],
            }
        )
        result = asyncio.run(execute_action(live, action))
        self.assertEqual([True, False], locator.clicks)
        self.assertEqual(1, len(result.result["postconditions"]))
        self.assertEqual("file:///[LOCAL]/index.html", result.result["preState"]["url"])

    def test_fill_uses_typed_api_and_value_assertion(self) -> None:
        locator = FakeLocator()
        live = SimpleNamespace(page=FakePage(locator))
        action = ActionSpec.decode(
            {
                "type": "fill",
                "locator": {"label": "用户名"},
                "value": "alice",
                "postconditions": [{"type": "value", "locator": {"label": "用户名"}, "expected": "alice"}],
            }
        )
        result = asyncio.run(execute_action(live, action))
        self.assertEqual("alice", locator.value)
        self.assertEqual("fill", result.result["action"])

    def test_failed_postcondition_does_not_replay_click(self) -> None:
        locator = FakeLocator(fail_wait=True)
        live = SimpleNamespace(page=FakePage(locator))
        action = ActionSpec.decode(
            {
                "type": "click",
                "locator": {"role": "button", "accessibleName": "保存"},
                "postconditions": [{"type": "visible", "locator": {"role": "button", "accessibleName": "保存"}}],
            }
        )
        with self.assertRaises(VerifierError) as caught:
            asyncio.run(execute_action(live, action))
        self.assertEqual("postcondition_error", caught.exception.code)
        self.assertEqual([True, False], locator.clicks)


if __name__ == "__main__":
    unittest.main()
