"""Locator、action 与安全策略契约测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.models import ActionSpec, LocatorSpec  # noqa: E402
from electron_verifier.security import (  # noqa: E402
    normalize_loopback_endpoint,
    redact,
    token_matches,
    validate_loopback_websocket,
)


class ContractTests(unittest.TestCase):
    def test_locator_requires_one_strategy(self) -> None:
        self.assertEqual("button", LocatorSpec.decode({"role": "button", "accessibleName": "保存"}).value)
        with self.assertRaisesRegex(VerifierError, "只能指定一种"):
            LocatorSpec.decode({"role": "button", "text": "保存"})

    def test_mutating_action_requires_postcondition(self) -> None:
        with self.assertRaisesRegex(VerifierError, "postcondition"):
            ActionSpec.decode({"type": "click", "locator": {"text": "保存"}})
        action = ActionSpec.decode(
            {
                "type": "click",
                "locator": {"role": "button", "accessibleName": "保存"},
                "postconditions": [
                    {"type": "visible", "locator": {"text": "保存成功"}}
                ],
            }
        )
        self.assertEqual("click", action.action_type)

    def test_removed_mutation_bypasses_and_unknown_fields_are_rejected(self) -> None:
        base = {
            "type": "click",
            "locator": {"text": "保存"},
            "postconditions": [{"type": "visible", "locator": {"text": "完成"}}],
        }
        for field in ("allowWithoutPostcondition", "confirmRisk"):
            with self.subTest(field=field), self.assertRaises(VerifierError) as caught:
                ActionSpec.decode({**base, field: True})
            self.assertEqual("invalid_action", caught.exception.code)
        for field in ("allowWithoutPostcondition", "confirmRisk", "allowCoordinate"):
            with self.subTest(option=field), self.assertRaises(VerifierError) as caught:
                ActionSpec.decode({**base, "options": {field: True}})
            self.assertEqual("invalid_action", caught.exception.code)

    def test_loopback_endpoint_is_literal_and_normalized(self) -> None:
        self.assertEqual("http://127.0.0.1:9222", normalize_loopback_endpoint("http://127.0.0.1:9222/"))
        self.assertEqual("http://[::1]:9222", normalize_loopback_endpoint("http://[::1]:9222"))
        for value in ("http://localhost:9222", "http://10.0.0.2:9222", "ws://127.0.0.1:9222"):
            with self.subTest(value=value), self.assertRaises(VerifierError):
                normalize_loopback_endpoint(value)

    def test_token_comparison_and_redaction(self) -> None:
        self.assertTrue(token_matches("secret", "Bearer secret"))
        self.assertFalse(token_matches("secret", "Bearer other"))
        self.assertEqual(
            {"Authorization": "[REDACTED]", "nested": {"password": "[REDACTED]", "value": "ok"}},
            redact({"Authorization": "Bearer value", "nested": {"password": "x", "value": "ok"}}),
        )

    def test_public_error_envelope_removes_paths_urls_and_secret_fields(self) -> None:
        error = VerifierError(
            "fixture_error",
            "读取 D:\\private\\profile\\state.json 失败，来源 https://user:pass@example.test/private?q=x",
            details={"path": "/Users/alice/private/state.json", "credential": "secret-value"},
        ).envelope()
        serialized = str(error)
        for forbidden in ("D:\\private", "/Users/alice", "user:pass", "secret-value", "?q=x"):
            self.assertNotIn(forbidden, serialized)

    def test_discovered_websocket_cannot_escape_loopback(self) -> None:
        self.assertEqual(
            "ws://127.0.0.1:9222/devtools/browser/id",
            validate_loopback_websocket("ws://127.0.0.1:9222/devtools/browser/id"),
        )
        for value in (
            "ws://10.0.0.2:9222/devtools/browser/id",
            "ws://localhost:9222/devtools/browser/id",
            "ws://127.0.0.1:9222/socket",
            "ws://127.0.0.1:9222/devtools/browser/id?token=x",
        ):
            with self.subTest(value=value), self.assertRaises(VerifierError):
                validate_loopback_websocket(value)


if __name__ == "__main__":
    unittest.main()
