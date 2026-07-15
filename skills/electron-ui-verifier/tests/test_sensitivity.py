"""瞬时绑定、安全投影和视觉 mask 契约测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.evidence import PendingArtifact  # noqa: E402
from electron_verifier.sensitivity import (  # noqa: E402
    BindingContext,
    REDACTED_BOUND,
    normalize_parameter_schema,
    sanitize_url,
)


class SensitivityTests(unittest.TestCase):
    def test_parameter_schema_is_closed_and_sensitive_by_default(self) -> None:
        schema = normalize_parameter_schema({"password": {"type": "string"}})
        self.assertTrue(schema["password"]["sensitive"])
        with self.assertRaises(VerifierError) as caught:
            normalize_parameter_schema({"password": {"type": "string", "default": "secret"}})
        self.assertEqual("invalid_parameter_schema", caught.exception.code)

    def test_binding_values_are_bound_but_only_safe_projection_crosses_boundary(self) -> None:
        sentinel = "SENTINEL-binding-8d9a"
        context = BindingContext.create(
            {"password": {"type": "string", "required": True}},
            {"password": sentinel},
        )
        raw_action = {
            "type": "fill",
            "locator": {"label": "密码"},
            "value": "${password}",
            "postconditions": [
                {"type": "value", "locator": {"label": "密码"}, "expected": "${password}"}
            ],
        }
        bound, names = context.bind(raw_action)
        self.assertEqual(sentinel, bound["value"])
        self.assertEqual({"password"}, names)

        projected = context.project(
            {
                "result": sentinel,
                "message": f"输入值为 {sentinel}",
                "nested": [sentinel],
                sentinel: "key",
            }
        )
        self.assertNotIn(sentinel, str(projected))
        self.assertEqual(REDACTED_BOUND, projected["result"])
        self.assertEqual(
            [{"name": "password", "type": "string", "bound": True, "sensitive": True}],
            context.parameter_summary(names),
        )
        self.assertEqual("label", context.sensitive_mask_specs(raw_action)[0].strategy)

    def test_text_artifacts_are_scrubbed_and_unknown_binary_fails_closed(self) -> None:
        sentinel = "artifact-secret-44"
        context = BindingContext.create(
            {"token": {"type": "string"}},
            {"token": sentinel},
        )
        artifact = context.sanitize_artifact(
            PendingArtifact("application/json", f'{{"value":"{sentinel}"}}'.encode(), "event", "json")
        )
        self.assertNotIn(sentinel.encode(), artifact.data)
        with self.assertRaises(VerifierError) as caught:
            context.sanitize_artifact(PendingArtifact("application/octet-stream", b"opaque", "raw", "bin"))
        self.assertEqual("sensitive_evidence_blocked", caught.exception.code)

    def test_url_projection_removes_credentials_and_local_paths(self) -> None:
        self.assertEqual(
            "https://example.test:8443/[PATH]",
            sanitize_url("https://user:pass@example.test:8443/private/path?q=secret#fragment"),
        )
        self.assertEqual("file:///[LOCAL]", sanitize_url("file:///Users/alice/private/index.html?token=x"))
        self.assertEqual("http://[::1]:9222/[PATH]", sanitize_url("http://[::1]:9222/private?q=x"))
        self.assertEqual("[URL]", sanitize_url("https://example.test:invalid/private"))


if __name__ == "__main__":
    unittest.main()
