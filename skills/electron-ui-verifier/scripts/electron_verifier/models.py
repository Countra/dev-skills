"""领域对象和严格输入解码。"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .atomic_io import canonical_json_bytes, sha256_bytes
from .errors import VerifierError


class RunState(str, Enum):
    PREPARED = "prepared"
    RUNNING = "running"
    FINALIZING = "finalizing"
    PASSED = "passed"
    FAILED = "failed"
    ABORTED = "aborted"


class StepStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


MUTATING_ACTIONS = {
    "click",
    "doubleClick",
    "fill",
    "select",
    "check",
    "uncheck",
    "press",
    "keyChord",
}

LOCATOR_KEYS = ("role", "label", "placeholder", "text", "testId", "title", "css")


@dataclass(frozen=True)
class LocatorSpec:
    strategy: str
    value: str
    accessible_name: str | None = None
    exact: bool = True
    nth: int | None = None

    @classmethod
    def decode(cls, value: Any) -> "LocatorSpec":
        if not isinstance(value, dict):
            raise VerifierError("invalid_locator", "locator 必须是 JSON object")
        present = [key for key in LOCATOR_KEYS if value.get(key) not in (None, "")]
        if len(present) != 1:
            raise VerifierError(
                "invalid_locator",
                "locator 必须且只能指定一种主定位策略",
                details={"strategies": present},
            )
        strategy = present[0]
        raw = value[strategy]
        accessible_name = None
        if strategy == "role":
            if not isinstance(raw, str) or not raw.strip():
                raise VerifierError("invalid_locator", "locator.role 必须是非空字符串")
            accessible_name = value.get("accessibleName")
            if accessible_name is not None and not isinstance(accessible_name, str):
                raise VerifierError("invalid_locator", "accessibleName 必须是字符串")
        elif not isinstance(raw, str) or not raw.strip():
            raise VerifierError("invalid_locator", f"locator.{strategy} 必须是非空字符串")
        nth = value.get("nth")
        if nth is not None and (not isinstance(nth, int) or isinstance(nth, bool) or nth < 0):
            raise VerifierError("invalid_locator", "locator.nth 必须是非负整数")
        return cls(
            strategy=strategy,
            value=raw.strip(),
            accessible_name=accessible_name.strip() if isinstance(accessible_name, str) else None,
            exact=value.get("exact", True) is not False,
            nth=nth,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {self.strategy: self.value, "exact": self.exact}
        if self.accessible_name is not None:
            result["accessibleName"] = self.accessible_name
        if self.nth is not None:
            result["nth"] = self.nth
        return result


@dataclass(frozen=True)
class AssertionSpec:
    kind: str
    locator: LocatorSpec | None = None
    expected: Any = None
    timeout_ms: int = 10_000

    @classmethod
    def decode(cls, value: Any) -> "AssertionSpec":
        if not isinstance(value, dict):
            raise VerifierError("invalid_assertion", "postcondition 必须是 JSON object")
        kind = str(value.get("type") or "").strip()
        if kind not in {"visible", "hidden", "text", "value", "count", "urlContains", "titleContains", "screenshotQuality"}:
            raise VerifierError("unsupported_assertion", f"不支持的 postcondition：{kind}")
        locator = LocatorSpec.decode(value["locator"]) if "locator" in value else None
        if kind in {"visible", "hidden", "text", "value", "count"} and locator is None:
            raise VerifierError("invalid_assertion", f"{kind} postcondition 需要 locator")
        timeout_ms = int(value.get("timeoutMs", 10_000))
        if timeout_ms < 1 or timeout_ms > 120_000:
            raise VerifierError("invalid_assertion", "postcondition timeoutMs 必须在 1..120000")
        return cls(kind=kind, locator=locator, expected=value.get("expected"), timeout_ms=timeout_ms)


@dataclass(frozen=True)
class ActionSpec:
    action_type: str
    locator: LocatorSpec | None = None
    value: Any = None
    options: dict[str, Any] = field(default_factory=dict)
    postconditions: tuple[AssertionSpec, ...] = ()

    @classmethod
    def decode(cls, value: Any) -> "ActionSpec":
        if not isinstance(value, dict):
            raise VerifierError("invalid_action", "action 必须是 JSON object")
        action_type = str(value.get("type") or "").strip()
        supported = MUTATING_ACTIONS | {
            "hover",
            "scroll",
            "snapshot",
            "screenshot",
            "waitText",
            "waitUrlContains",
            "evaluate",
            "extractText",
            "extractTable",
            "collectConsole",
            "collectExceptions",
            "collectNetwork",
        }
        if action_type not in supported:
            raise VerifierError("unsupported_action", f"不支持的 action：{action_type}")
        options = value.get("options") or {}
        if not isinstance(options, dict):
            raise VerifierError("invalid_action", "action.options 必须是 JSON object")
        locator = LocatorSpec.decode(value["locator"]) if "locator" in value else None
        locator_required = {"fill", "select", "check", "uncheck", "hover", "extractText"}
        if action_type in locator_required and locator is None:
            raise VerifierError("invalid_action", f"{action_type} action 需要 locator")
        if action_type in {"click", "doubleClick"} and locator is None:
            coordinates = options.get("coordinates")
            valid_coordinates = (
                isinstance(coordinates, dict)
                and isinstance(coordinates.get("x"), (int, float))
                and not isinstance(coordinates.get("x"), bool)
                and math.isfinite(float(coordinates.get("x")))
                and isinstance(coordinates.get("y"), (int, float))
                and not isinstance(coordinates.get("y"), bool)
                and math.isfinite(float(coordinates.get("y")))
                and float(coordinates.get("x")) >= 0
                and float(coordinates.get("y")) >= 0
            )
            if options.get("allowCoordinate") is not True or not valid_coordinates:
                raise VerifierError(
                    "coordinate_action_not_allowed",
                    f"{action_type} 无 locator 时必须显式提供 allowCoordinate 和 coordinates",
                )
        post_raw = value.get("postconditions") or []
        if not isinstance(post_raw, list):
            raise VerifierError("invalid_action", "action.postconditions 必须是数组")
        postconditions = tuple(AssertionSpec.decode(item) for item in post_raw)
        if action_type in MUTATING_ACTIONS and not postconditions and options.get("allowWithoutPostcondition") is not True:
            raise VerifierError(
                "postcondition_required",
                f"有副作用的 {action_type} action 必须提供 required postcondition",
            )
        return cls(
            action_type=action_type,
            locator=locator,
            value=value.get("value"),
            options=dict(options),
            postconditions=postconditions,
        )


@dataclass
class SessionIntent:
    session_id: str
    name: str
    cdp: str
    selector: dict[str, Any]
    app_id: str | None
    status: str = "intent"
    target_id: str | None = None
    target_url: str | None = None
    target_title: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "name": self.name,
            "cdp": self.cdp,
            "selector": self.selector,
            "appId": self.app_id,
            "status": self.status,
            "targetId": self.target_id,
            "targetUrl": self.target_url,
            "targetTitle": self.target_title,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


def canonical_digest(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)
