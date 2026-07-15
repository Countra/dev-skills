"""参数绑定的瞬时上下文、值感知脱敏和 URL 最小化。"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from .errors import VerifierError
from .evidence import PendingArtifact
from .models import LocatorSpec
from .security import redact


PLACEHOLDER = re.compile(r"^\$\{([A-Za-z][A-Za-z0-9_.-]{0,63})\}$")
PARAMETER_FIELDS = {"type", "required", "description", "sensitive"}
REDACTED_BOUND = "[REDACTED_BOUND]"


def placeholder_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = PLACEHOLDER.fullmatch(value)
    return match.group(1) if match else None


def placeholders(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            result.update(placeholders(item))
    elif isinstance(value, list):
        for item in value:
            result.update(placeholders(item))
    elif isinstance(value, str):
        name = placeholder_name(value)
        if name:
            result.add(name)
        elif "${" in value:
            raise VerifierError("invalid_placeholder", "参数占位符必须占据完整字符串")
    return result


def normalize_parameter_schema(value: Any) -> dict[str, dict[str, Any]]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise VerifierError("invalid_parameter_schema", "parameterSchema 必须是 object")
    result: dict[str, dict[str, Any]] = {}
    for name, raw in value.items():
        if not PLACEHOLDER.fullmatch(f"${{{name}}}"):
            raise VerifierError("invalid_parameter_schema", f"参数名无效：{name}")
        if not isinstance(raw, dict):
            raise VerifierError("invalid_parameter_schema", f"参数 {name} schema 必须是 object")
        unknown = sorted(set(raw) - PARAMETER_FIELDS)
        if unknown:
            raise VerifierError("invalid_parameter_schema", f"参数 {name} 包含未知字段：{unknown}")
        parameter_type = str(raw.get("type") or "string")
        if parameter_type not in {"string", "number", "integer", "boolean"}:
            raise VerifierError("invalid_parameter_schema", f"参数 {name} type 不受支持：{parameter_type}")
        result[str(name)] = {
            "type": parameter_type,
            "required": raw.get("required", True) is not False,
            "description": str(raw.get("description") or "")[:500],
            "sensitive": raw.get("sensitive", True) is not False,
        }
    return result


def _validate_binding(name: str, value: Any, schema: dict[str, Any]) -> None:
    expected = schema.get("type", "string")
    valid = {
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }[expected]
    if not valid:
        raise VerifierError("invalid_parameter_binding", f"参数 {name} 必须是 {expected}")


def sanitize_url(value: str) -> str:
    """只保留 URL 的来源信息，不持久化路径、凭据、查询或片段。"""

    try:
        parsed = urllib.parse.urlsplit(value.strip())
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        return "[URL]"
    if parsed.scheme == "file":
        return "file:///[LOCAL]"
    if parsed.scheme in {"http", "https", "app"}:
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        path_marker = "/[PATH]" if parsed.path not in {"", "/"} else "/"
        return urllib.parse.urlunsplit((parsed.scheme, f"{host}{port}", path_marker, "", ""))
    return f"{parsed.scheme}:" if parsed.scheme else "[URL]"


def safe_action_template(raw_action: Any) -> Any:
    """保留可复用动作结构，同时移除直接输入和断言内容。"""

    value = redact(raw_action)
    if not isinstance(value, dict):
        return value
    if value.get("type") in {"fill", "select", "waitText", "waitUrlContains"} and "value" in value:
        if placeholder_name(value.get("value")) is None:
            value["value"] = "[REDACTED_INPUT]"
    options = value.get("options")
    if isinstance(options, dict) and options.get("urlContains") not in (None, ""):
        if placeholder_name(options.get("urlContains")) is None:
            options["urlContains"] = "[REDACTED_INPUT]"
    postconditions = value.get("postconditions")
    if isinstance(postconditions, list):
        for assertion in postconditions:
            if (
                isinstance(assertion, dict)
                and assertion.get("type") in {"value", "text", "urlContains", "titleContains"}
                and "expected" in assertion
                and placeholder_name(assertion.get("expected")) is None
            ):
                assertion["expected"] = "[REDACTED_INPUT]"
    return value


def transient_input_values(raw_action: Any) -> list[Any]:
    """收集只允许在单次命令内存活的直接输入值。"""

    if not isinstance(raw_action, dict):
        return []
    values: list[Any] = []
    if raw_action.get("type") in {"fill", "select", "waitText", "waitUrlContains"} and placeholder_name(
        raw_action.get("value")
    ) is None:
        values.append(raw_action.get("value"))
    options = raw_action.get("options")
    if isinstance(options, dict) and placeholder_name(options.get("urlContains")) is None:
        values.append(options.get("urlContains"))
    for assertion in raw_action.get("postconditions") or []:
        if (
            isinstance(assertion, dict)
            and assertion.get("type") in {"value", "text", "urlContains", "titleContains"}
            and placeholder_name(assertion.get("expected")) is None
        ):
            values.append(assertion.get("expected"))
    return values


@dataclass(frozen=True)
class BindingContext:
    """绑定原值只存活在一次命令内，所有跨边界数据必须经安全投影。"""

    schema: dict[str, dict[str, Any]]
    _bindings: dict[str, Any] = field(repr=False)

    @classmethod
    def create(cls, schema: Any, bindings: Any) -> "BindingContext":
        normalized = normalize_parameter_schema(schema)
        if bindings in (None, {}):
            binding_map: dict[str, Any] = {}
        elif isinstance(bindings, dict):
            binding_map = dict(bindings)
        else:
            raise VerifierError("invalid_parameter_binding", "bindings 必须是 object")
        undeclared = sorted(set(binding_map) - set(normalized))
        if undeclared:
            raise VerifierError("undeclared_parameter", f"bindings 包含未声明参数：{undeclared}")
        for name, item in binding_map.items():
            _validate_binding(name, item, normalized[name])
        return cls(normalized, binding_map)

    @property
    def names(self) -> set[str]:
        return set(self._bindings)

    def with_transient_values(self, values: list[Any]) -> "BindingContext":
        combined = dict(self._bindings)
        for index, value in enumerate(values):
            if isinstance(value, (str, int, float, bool)) and value not in ("", None):
                combined[f"__transient_{index}"] = value
        return BindingContext(self.schema, combined)

    @property
    def sensitive_names(self) -> set[str]:
        return {
            name
            for name, definition in self.schema.items()
            if definition.get("sensitive", True) is not False
        }

    def bind(self, value: Any) -> tuple[Any, set[str]]:
        required = placeholders(value)
        undeclared = sorted(required - set(self.schema))
        if undeclared:
            raise VerifierError("undeclared_parameter", f"占位符未在 parameterSchema 声明：{undeclared}")
        missing = sorted(required - set(self._bindings))
        if missing:
            raise VerifierError("parameter_binding_required", f"缺少参数绑定：{missing}")

        def replace(item: Any) -> Any:
            if isinstance(item, dict):
                return {key: replace(child) for key, child in item.items()}
            if isinstance(item, list):
                return [replace(child) for child in item]
            name = placeholder_name(item)
            return self._bindings[name] if name else item

        return replace(value), required

    def project(self, value: Any) -> Any:
        """移除任何绑定原值；字符串按最长值优先替换。"""

        binding_values = list(self._bindings.values())
        if any(value == item and type(value) is type(item) for item in binding_values):
            return REDACTED_BOUND
        if isinstance(value, dict):
            return {str(self.project(str(key))): self.project(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.project(item) for item in value]
        if isinstance(value, tuple):
            return [self.project(item) for item in value]
        if isinstance(value, str):
            projected = value
            text_values = sorted(
                {item for item in binding_values if isinstance(item, str) and item},
                key=len,
                reverse=True,
            )
            for item in text_values:
                projected = projected.replace(item, REDACTED_BOUND)
            return projected
        return value

    def parameter_summary(self, used: set[str]) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "type": self.schema[name]["type"],
                "bound": name in self._bindings,
                "sensitive": self.schema[name].get("sensitive", True) is not False,
            }
            for name in sorted(used)
        ]

    def sensitive_mask_specs(self, raw_action: Any) -> list[LocatorSpec]:
        used_sensitive = placeholders(raw_action) & self.sensitive_names
        direct_sensitive = (
            isinstance(raw_action, dict)
            and raw_action.get("type") in {"fill", "select"}
            and placeholder_name(raw_action.get("value")) is None
            and raw_action.get("value") not in (None, "")
        )
        if (
            not used_sensitive
            and not direct_sensitive
            or not isinstance(raw_action, dict)
            or not isinstance(raw_action.get("locator"), dict)
        ):
            return []
        bound_locator, _ = self.bind(raw_action["locator"])
        return [LocatorSpec.decode(bound_locator)]

    def sanitize_artifact(self, artifact: PendingArtifact) -> PendingArtifact:
        safe_label = str(self.project(artifact.label))[:200]
        textual = artifact.media_type.startswith("text/") or artifact.media_type in {
            "application/json",
            "application/xml",
        }
        if textual:
            text = artifact.data.decode("utf-8", errors="replace")
            return PendingArtifact(
                artifact.media_type,
                str(self.project(text)).encode("utf-8"),
                safe_label,
                artifact.extension,
            )
        if artifact.media_type == "image/png":
            return PendingArtifact(
                artifact.media_type,
                artifact.data,
                safe_label,
                artifact.extension,
            )
        if self._bindings:
            raise VerifierError(
                "sensitive_evidence_blocked",
                f"无法证明二进制证据 {artifact.media_type} 不含绑定值",
            )
        return artifact


def bind_parameters(value: Any, bindings: Any, schema: Any) -> tuple[Any, set[str]]:
    """保留现有函数入口，但内部统一使用瞬时绑定上下文。"""

    return BindingContext.create(schema, bindings).bind(value)
