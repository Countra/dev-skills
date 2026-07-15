#!/usr/bin/env python3
"""验证敏感值投影、视觉 mask 与 mutation 风险授权边界。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "electron-ui-verifier" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.actions import ActionExecution, execute_action  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.evidence import PendingArtifact  # noqa: E402
from electron_verifier.models import ActionSpec, LocatorSpec  # noqa: E402
from electron_verifier.runs import RunService  # noqa: E402
from electron_verifier.sensitivity import sanitize_url  # noqa: E402


SENTINEL = "EV-SENTINEL-4f39c881"


class FakeSessions:
    def __init__(self) -> None:
        self.driver = SimpleNamespace(live=lambda session_id: SimpleNamespace(page=object()))

    async def status(self, value: str) -> dict[str, Any]:
        return {
            "ok": True,
            "connected": True,
            "session": {
                "sessionId": "security-session",
                "name": "security",
                "status": "connected",
                "targetTitle": "Security Fixture",
            },
        }

    def intent(self, value: str) -> Any:
        return SimpleNamespace(
            session_id="security-session",
            target_id="security-target",
            app_id="security-fixture",
        )


class FakeLocator:
    def __init__(self, count: int = 1) -> None:
        self._count = count

    async def count(self) -> int:
        return self._count


class FakePage:
    url = "file:///private/security-fixture/index.html?credential=hidden#fragment"

    def __init__(self, locator: FakeLocator) -> None:
        self.locator = locator
        self.mask_counts: list[int] = []

    def get_by_label(self, value: str, **options: Any) -> FakeLocator:
        return self.locator

    async def title(self) -> str:
        return "Security Fixture"

    async def screenshot(self, *, timeout: int, mask: list[FakeLocator]) -> bytes:
        self.mask_counts.append(len(mask))
        return b"masked-screenshot"


def service_config(root: Path) -> Any:
    return SimpleNamespace(state_root=root, runs_dir=root / "runs", pending_dir=root / "pending")


def serialized(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def scan_for_sentinel(root: Path) -> list[str]:
    leaks = []
    for path in root.rglob("*"):
        if path.is_file() and SENTINEL.encode() in path.read_bytes():
            leaks.append(str(path.relative_to(root)))
    return leaks


async def sentinel_scenario(root: Path) -> dict[str, Any]:
    service = RunService(service_config(root), FakeSessions())
    prepared = await service.prepare(
        {
            "session": "security",
            "appId": "security-fixture",
            "parameterSchema": {"credential": {"type": "string"}},
        }
    )
    action = {
        "type": "fill",
        "locator": {"label": "凭据"},
        "value": "${credential}",
        "postconditions": [
            {"type": "value", "locator": {"label": "凭据"}, "expected": "${credential}"}
        ],
    }

    async def successful_execute(live: Any, decoded: ActionSpec) -> ActionExecution:
        if decoded.value != SENTINEL:
            raise AssertionError("绑定值未到达瞬时执行边界")
        return ActionExecution(
            result={"action": "fill", "echo": SENTINEL, "postconditions": [{"passed": True}]},
            artifacts=[
                PendingArtifact(
                    "application/json",
                    serialized({"echo": SENTINEL}).encode("utf-8"),
                    f"artifact-{SENTINEL}",
                    "json",
                )
            ],
        )

    with mock.patch("electron_verifier.runs.execute_action", side_effect=successful_execute):
        success = await service.append_action(
            prepared["runId"],
            action,
            bindings={"credential": SENTINEL},
        )

    async def failing_execute(live: Any, decoded: ActionSpec) -> ActionExecution:
        raise VerifierError("fixture_failure", f"失败值：{SENTINEL}", details={"echo": SENTINEL})

    with mock.patch("electron_verifier.runs.execute_action", side_effect=failing_execute):
        failure = await service.append_action(
            prepared["runId"],
            action,
            bindings={"credential": SENTINEL},
        )
    response_leak = SENTINEL in serialized({"success": success, "failure": failure})
    return {
        "responseLeak": response_leak,
        "persistedLeaks": scan_for_sentinel(root),
        "successState": success["step"]["status"],
        "failureState": failure["step"]["status"],
    }


async def mask_scenario() -> dict[str, Any]:
    action = ActionSpec.decode({"type": "screenshot"})
    mask = LocatorSpec.decode({"label": "凭据"})
    page = FakePage(FakeLocator())
    result = await execute_action(SimpleNamespace(page=page), action, sensitive_masks=(mask,))

    blocked_code = None
    missing_page = FakePage(FakeLocator(count=0))
    try:
        await execute_action(SimpleNamespace(page=missing_page), action, sensitive_masks=(mask,))
    except VerifierError as exc:
        blocked_code = exc.code
    return {
        "maskedLocatorCount": result.result.get("maskedLocatorCount"),
        "maskCalls": page.mask_counts,
        "missingMaskCode": blocked_code,
        "failedArtifactCount": len(missing_page.mask_counts),
    }


async def risk_scenario(root: Path) -> dict[str, Any]:
    service = RunService(service_config(root), FakeSessions())
    prepared = await service.prepare({"session": "security", "appId": "security-fixture"})
    action = {
        "type": "click",
        "locator": {"role": "button", "accessibleName": "删除", "nth": 0},
        "postconditions": [{"type": "hidden", "locator": {"text": "待删除"}}],
    }
    mutation_count = 0

    async def mutate(live: Any, decoded: ActionSpec) -> ActionExecution:
        nonlocal mutation_count
        mutation_count += 1
        return ActionExecution(
            result={"action": "click", "postconditions": [{"passed": True}]},
            risks=[{"code": "explicit_nth", "learnable": False, "nth": 0}],
        )

    missing_code = None
    replay_code = None
    with mock.patch("electron_verifier.runs.execute_action", side_effect=mutate):
        try:
            await service.append_action(prepared["runId"], action)
        except VerifierError as exc:
            missing_code = exc.code
        preview = service.preview_risk(prepared["runId"], action)
        receipt = service.approve_risk(preview["previewId"], preview["fingerprint"], "确认安全回归动作")
        await service.append_action(
            prepared["runId"],
            action,
            risk_receipt=receipt["receiptId"],
        )
        try:
            await service.append_action(
                prepared["runId"],
                action,
                risk_receipt=receipt["receiptId"],
            )
        except VerifierError as exc:
            replay_code = exc.code
    return {
        "missingReceiptCode": missing_code,
        "replayedReceiptCode": replay_code,
        "mutationCount": mutation_count,
    }


def contract_scenario() -> dict[str, Any]:
    errors: dict[str, str | None] = {}
    cases = {
        "missingPostcondition": {"type": "click", "locator": {"text": "保存"}},
        "selfSignedAction": {
            "type": "click",
            "locator": {"text": "保存"},
            "confirmRisk": True,
            "postconditions": [{"type": "visible", "locator": {"text": "完成"}}],
        },
        "selfSignedOption": {
            "type": "click",
            "locator": {"text": "保存"},
            "options": {"allowWithoutPostcondition": True},
            "postconditions": [{"type": "visible", "locator": {"text": "完成"}}],
        },
    }
    for name, action in cases.items():
        try:
            ActionSpec.decode(action)
        except VerifierError as exc:
            errors[name] = exc.code
        else:
            errors[name] = None
    return errors


def evaluate(checks: dict[str, Any]) -> list[str]:
    failures = []
    sentinel = checks["sentinel"]
    if sentinel["responseLeak"] or sentinel["persistedLeaks"]:
        failures.append("sentinel 出现在响应或持久文件")
    if sentinel["successState"] != "passed" or sentinel["failureState"] != "failed":
        failures.append("sentinel 成功/失败链路状态不完整")
    mask = checks["mask"]
    if mask != {
        "maskedLocatorCount": 1,
        "maskCalls": [1],
        "missingMaskCode": "sensitive_evidence_blocked",
        "failedArtifactCount": 0,
    }:
        failures.append("screenshot mask 或 fail-closed 契约失败")
    risk = checks["risk"]
    if risk != {
        "missingReceiptCode": "risk_authorization_required",
        "replayedReceiptCode": "risk_authorization_consumed",
        "mutationCount": 1,
    }:
        failures.append("risk receipt 未把 mutation 次数限制为一次")
    if checks["contract"] != {
        "missingPostcondition": "postcondition_required",
        "selfSignedAction": "invalid_action",
        "selfSignedOption": "invalid_action",
    }:
        failures.append("postcondition 或自签旁路仍可通过")
    if checks["urls"] != {
        "remote": "https://example.test/[PATH]",
        "local": "file:///[LOCAL]",
    }:
        failures.append("URL 安全投影保留了敏感路径")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 electron-ui-verifier 安全边界回归")
    parser.add_argument("--work-dir", type=Path, required=True, help="隔离测试状态根")
    parser.add_argument("--output", type=Path, required=True, help="JSON 证据输出路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenario_root = args.work_dir.resolve() / str(uuid.uuid4())
    scenario_root.mkdir(parents=True, exist_ok=False)
    checks = {
        "sentinel": asyncio.run(sentinel_scenario(scenario_root / "sentinel")),
        "mask": asyncio.run(mask_scenario()),
        "risk": asyncio.run(risk_scenario(scenario_root / "risk")),
        "contract": contract_scenario(),
        "urls": {
            "remote": sanitize_url("https://user:pass@example.test/private?q=secret#fragment"),
            "local": sanitize_url("file:///Users/private/secret.txt?q=secret"),
        },
    }
    failures = evaluate(checks)
    result = {"ok": not failures, "failures": failures, "checks": checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
