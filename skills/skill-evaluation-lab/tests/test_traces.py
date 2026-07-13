"""Codex JSONL 和 structured final 解析测试。"""

from __future__ import annotations

import json
import unittest

from _helpers import temporary_workspace
from skill_evaluation_lab.errors import ExecutionError, UnsupportedError
from skill_evaluation_lab.traces import load_structured_final, parse_jsonl_trace, require_supported_trace


class TraceTests(unittest.TestCase):
    def test_summarizes_known_and_unknown_events(self) -> None:
        with temporary_workspace() as root:
            path = root / "trace.jsonl"
            events = [
                {"type": "thread.started", "thread_id": "thread-1"},
                {"type": "future.event", "value": 1},
                {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 3}},
            ]
            path.write_text("".join(json.dumps(item) + "\n" for item in events), encoding="utf-8")
            summary = parse_jsonl_trace(path)
            self.assertEqual(summary["event_count"], 3)
            self.assertEqual(summary["unknown_event_types"], ["future.event"])
            self.assertEqual(summary["usage"]["input_tokens"], 10)
            with self.assertRaisesRegex(UnsupportedError, "未知事件"):
                require_supported_trace(summary, return_code=0)

    def test_success_requires_one_completed_turn(self) -> None:
        with self.assertRaisesRegex(ExecutionError, "turn.completed"):
            require_supported_trace(
                {
                    "event_count": 2,
                    "event_types": {"thread.started": 1, "turn.started": 1},
                    "unknown_event_types": [],
                },
                return_code=0,
            )
        require_supported_trace(
            {
                "event_count": 1,
                "event_types": {"turn.failed": 1},
                "unknown_event_types": [],
            },
            return_code=1,
        )

    def test_rejects_invalid_jsonl_without_guessing(self) -> None:
        with temporary_workspace() as root:
            path = root / "trace.jsonl"
            path.write_text("not-json\n", encoding="utf-8")
            with self.assertRaisesRegex(ExecutionError, "合法 JSON"):
                parse_jsonl_trace(path)

    def test_loads_bounded_structured_final(self) -> None:
        with temporary_workspace() as root:
            path = root / "final.json"
            path.write_text('{"activation_receipt": null, "response": "ok"}\n', encoding="utf-8")
            self.assertEqual(load_structured_final(path)["response"], "ok")


if __name__ == "__main__":
    unittest.main()
