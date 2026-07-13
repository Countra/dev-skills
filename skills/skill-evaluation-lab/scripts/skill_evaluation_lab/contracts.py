"""Suite closed contract、路径和引用校验。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import SuiteError


ROOT_FIELDS = {"suite_id", "skill_path", "baseline", "runner", "budgets", "gates", "cases"}
BASELINE_FIELDS = {"mode", "path"}
RUNNER_FIELDS = {
    "adapter",
    "model",
    "sandbox",
    "timeout_seconds",
    "repetitions",
    "concurrency",
    "network_access",
}
BUDGET_FIELDS = {"max_agent_runs", "max_judge_runs", "max_wall_seconds"}
GATE_FIELDS = {"trigger_threshold", "required_case_pass_rate", "judge_required"}
CASE_FIELDS = {
    "id",
    "mode",
    "split",
    "prompt",
    "inputs",
    "should_trigger",
    "assertions",
    "trusted_verifier",
    "repetitions",
}
ASSERTION_FIELDS = {
    "id",
    "type",
    "path",
    "value",
    "pattern",
    "argv",
    "cwd",
    "timeout_seconds",
    "allow",
    "deny",
}
ASSERTION_TYPES = {
    "file_exists",
    "file_absent",
    "path_changed",
    "path_unchanged",
    "text_contains",
    "text_excludes",
    "regex_matches",
    "json_valid",
    "json_field_equals",
    "diff_allows_only",
    "diff_excludes",
    "verifier_command",
}
ASSERTION_FIELDS_BY_TYPE = {
    "file_exists": {"id", "type", "path"},
    "file_absent": {"id", "type", "path"},
    "path_changed": {"id", "type", "path"},
    "path_unchanged": {"id", "type", "path"},
    "text_contains": {"id", "type", "path", "value"},
    "text_excludes": {"id", "type", "path", "value"},
    "regex_matches": {"id", "type", "path", "pattern"},
    "json_valid": {"id", "type", "path"},
    "json_field_equals": {"id", "type", "path", "value"},
    "diff_allows_only": {"id", "type", "allow"},
    "diff_excludes": {"id", "type", "deny"},
    "verifier_command": {"id", "type", "argv", "cwd", "timeout_seconds"},
}
CASE_FIELDS_BY_MODE = {
    "trigger": {"id", "mode", "split", "prompt", "inputs", "should_trigger", "repetitions"},
    "behavior": {"id", "mode", "split", "prompt", "inputs", "assertions", "trusted_verifier", "repetitions"},
}
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
WINDOWS_ABSOLUTE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")
MAX_SUITE_BYTES = 4 * 1024 * 1024
MAX_CASES = 128
MAX_INPUTS_PER_CASE = 64
MAX_ASSERTIONS_PER_CASE = 64
MAX_PATTERN_ITEMS = 128
MAX_VERIFIER_ARGS = 32
MAX_REPETITIONS = 20
MAX_TIMEOUT_SECONDS = 3600
MAX_AGENT_RUNS = 256
MAX_JUDGE_RUNS = 32
MAX_WALL_SECONDS = 86400


@dataclass(frozen=True)
class SuiteDocument:
    """经过完整校验的 suite 与来源位置。"""

    path: Path
    root: Path
    data: dict[str, Any]

    @property
    def suite_id(self) -> str:
        return str(self.data["suite_id"])

    @property
    def cases(self) -> list[dict[str, Any]]:
        return list(self.data["cases"])


def _error(path: str, message: str, guidance: str | None = None) -> SuiteError:
    return SuiteError(message, path=path, guidance=guidance)


def _closed(value: Any, path: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(path, "必须是 JSON object")
    unknown = sorted(set(value) - fields)
    if unknown:
        raise _error(f"{path}.{unknown[0]}", "存在未知字段", "删除字段或更新当前唯一契约")
    return value


def _required(value: dict[str, Any], path: str, fields: set[str]) -> None:
    missing = sorted(fields - set(value))
    if missing:
        raise _error(f"{path}.{missing[0]}", "缺少必需字段")


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(path, "必须是非空字符串")
    return value


def _relative_path(value: Any, path: str) -> str:
    raw = _string(value, path)
    candidate = Path(raw)
    portable_parts = re.split(r"[\\/]", raw)
    if (
        candidate.is_absolute()
        or raw.startswith(("/", "\\"))
        or WINDOWS_ABSOLUTE_PATTERN.match(raw)
        or ".." in portable_parts
    ):
        raise _error(path, "必须是工作区内且不能包含 .. 的相对路径")
    return raw


def _positive_int(value: Any, path: str, *, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise _error(path, "必须是正整数")
    if maximum is not None and value > maximum:
        raise _error(path, f"不能超过实现上限 {maximum}")
    return value


def _ratio(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
        raise _error(path, "必须是 0 到 1 之间的数值")
    return float(value)


def resolve_inside(root: Path, raw: str, path: str, *, must_exist: bool = True) -> Path:
    candidate = Path(raw)
    portable_parts = re.split(r"[\\/]", raw)
    if (
        candidate.is_absolute()
        or raw.startswith(("/", "\\"))
        or WINDOWS_ABSOLUTE_PATTERN.match(raw)
        or ".." in portable_parts
    ):
        raise _error(path, "路径必须是 suite 目录内且不能包含 ..")
    unresolved = root / candidate
    is_junction = getattr(unresolved, "is_junction", None)
    if unresolved.is_symlink() or bool(is_junction and is_junction()):
        raise _error(path, "路径不能是符号链接或 junction")
    resolved = unresolved.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise _error(path, "路径逃逸 suite 目录") from exc
    if must_exist and not resolved.exists():
        raise _error(path, f"路径不存在：{raw}")
    return resolved


def resolve_source(root: Path, raw: str, path: str) -> Path:
    """解析显式 source 路径；source 可位于 suite 外，但后续只能复制为只读快照。"""
    candidate = Path(raw).expanduser()
    unresolved = candidate if candidate.is_absolute() else root / candidate
    is_junction = getattr(unresolved, "is_junction", None)
    if unresolved.is_symlink() or bool(is_junction and is_junction()):
        raise _error(path, "source 路径不能是符号链接或 junction")
    resolved = unresolved.resolve()
    if not resolved.exists():
        raise _error(path, f"source 路径不存在：{raw}")
    return resolved


def _validate_assertion(value: Any, path: str) -> dict[str, Any]:
    item = _closed(value, path, ASSERTION_FIELDS)
    _required(item, path, {"id", "type"})
    assertion_id = _string(item["id"], f"{path}.id")
    if not ID_PATTERN.fullmatch(assertion_id):
        raise _error(f"{path}.id", "assertion id 只能使用小写字母、数字和连字符")
    assertion_type = _string(item["type"], f"{path}.type")
    if assertion_type not in ASSERTION_TYPES:
        raise _error(f"{path}.type", f"未知 assertion type：{assertion_type}")
    unknown = sorted(set(item) - ASSERTION_FIELDS_BY_TYPE[assertion_type])
    if unknown:
        raise _error(
            f"{path}.{unknown[0]}",
            f"{assertion_type} assertion 不允许该字段",
            "删除与当前 assertion type 无关的字段",
        )
    path_types = ASSERTION_TYPES - {"diff_allows_only", "diff_excludes", "verifier_command"}
    if assertion_type in path_types:
        _relative_path(item.get("path"), f"{path}.path")
    if assertion_type in {"text_contains", "text_excludes"}:
        _string(item.get("value"), f"{path}.value")
    if assertion_type == "json_field_equals":
        specification = item.get("value")
        if not isinstance(specification, dict) or set(specification) != {"field", "equals"}:
            raise _error(f"{path}.value", "必须且仅能包含 field 与 equals")
        _string(specification["field"], f"{path}.value.field")
    if assertion_type == "regex_matches":
        pattern = _string(item.get("pattern"), f"{path}.pattern")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise _error(f"{path}.pattern", f"正则表达式无效：{exc}") from exc
    if assertion_type in {"diff_allows_only", "diff_excludes"}:
        field = "allow" if assertion_type == "diff_allows_only" else "deny"
        values = item.get(field)
        if not isinstance(values, list) or not values or not all(isinstance(v, str) and v for v in values):
            raise _error(f"{path}.{field}", "必须是非空字符串数组")
        if len(values) > MAX_PATTERN_ITEMS:
            raise _error(f"{path}.{field}", f"最多允许 {MAX_PATTERN_ITEMS} 项")
        for index, raw in enumerate(values):
            _relative_path(raw, f"{path}.{field}[{index}]")
    if assertion_type == "verifier_command":
        argv = item.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(v, str) and v for v in argv):
            raise _error(f"{path}.argv", "verifier argv 必须是非空字符串数组")
        if len(argv) > MAX_VERIFIER_ARGS:
            raise _error(f"{path}.argv", f"最多允许 {MAX_VERIFIER_ARGS} 项")
        _positive_int(
            item.get("timeout_seconds", 30),
            f"{path}.timeout_seconds",
            maximum=MAX_TIMEOUT_SECONDS,
        )
        if "cwd" in item:
            _relative_path(item["cwd"], f"{path}.cwd")
    return item


def _validate_case(value: Any, path: str, root: Path) -> dict[str, Any]:
    item = _closed(value, path, CASE_FIELDS)
    _required(item, path, {"id", "mode", "split", "prompt", "inputs"})
    case_id = _string(item["id"], f"{path}.id")
    if not ID_PATTERN.fullmatch(case_id):
        raise _error(f"{path}.id", "case id 只能使用小写字母、数字和连字符")
    mode = _string(item["mode"], f"{path}.mode")
    if mode not in {"trigger", "behavior"}:
        raise _error(f"{path}.mode", "mode 必须是 trigger 或 behavior")
    unknown = sorted(set(item) - CASE_FIELDS_BY_MODE[mode])
    if unknown:
        raise _error(
            f"{path}.{unknown[0]}",
            f"{mode} case 不允许该字段",
            "删除与当前 case mode 无关的字段",
        )
    if item["split"] not in {"train", "validation", "holdout"}:
        raise _error(f"{path}.split", "split 必须是 train、validation 或 holdout")
    _string(item["prompt"], f"{path}.prompt")
    inputs = item["inputs"]
    if not isinstance(inputs, list) or not all(isinstance(v, str) and v for v in inputs):
        raise _error(f"{path}.inputs", "inputs 必须是字符串数组")
    if len(inputs) > MAX_INPUTS_PER_CASE:
        raise _error(f"{path}.inputs", f"最多允许 {MAX_INPUTS_PER_CASE} 项")
    for index, raw in enumerate(inputs):
        resolve_inside(root, raw, f"{path}.inputs[{index}]")
    if "repetitions" in item:
        _positive_int(item["repetitions"], f"{path}.repetitions", maximum=MAX_REPETITIONS)
    assertions = item.get("assertions", [])
    if not isinstance(assertions, list):
        raise _error(f"{path}.assertions", "assertions 必须是数组")
    if len(assertions) > MAX_ASSERTIONS_PER_CASE:
        raise _error(f"{path}.assertions", f"最多允许 {MAX_ASSERTIONS_PER_CASE} 项")
    assertion_ids: set[str] = set()
    has_verifier = False
    for index, assertion in enumerate(assertions):
        parsed = _validate_assertion(assertion, f"{path}.assertions[{index}]")
        if parsed["id"] in assertion_ids:
            raise _error(f"{path}.assertions[{index}].id", "assertion id 重复")
        assertion_ids.add(parsed["id"])
        has_verifier = has_verifier or parsed["type"] == "verifier_command"
    if mode == "trigger":
        if not isinstance(item.get("should_trigger"), bool):
            raise _error(f"{path}.should_trigger", "trigger case 必须声明 boolean should_trigger")
    elif not assertions and not item.get("trusted_verifier"):
        raise _error(path, "behavior case 至少需要 assertion 或 trusted_verifier")
    if "trusted_verifier" in item and not isinstance(item["trusted_verifier"], bool):
        raise _error(f"{path}.trusted_verifier", "trusted_verifier 必须是 boolean")
    if has_verifier and item.get("trusted_verifier") is not True:
        raise _error(f"{path}.trusted_verifier", "verifier_command 必须显式声明 trusted_verifier=true")
    if item.get("trusted_verifier") is True and not has_verifier:
        raise _error(f"{path}.assertions", "trusted_verifier=true 必须提供 verifier_command assertion")
    return item


def validate_suite(value: Any, *, path: Path) -> SuiteDocument:
    root_value = _closed(value, "$", ROOT_FIELDS)
    _required(root_value, "$", ROOT_FIELDS)
    suite_id = _string(root_value["suite_id"], "$.suite_id")
    if not ID_PATTERN.fullmatch(suite_id):
        raise _error("$.suite_id", "suite_id 只能使用小写字母、数字和连字符")
    root = path.resolve().parent
    skill_path = resolve_source(root, _string(root_value["skill_path"], "$.skill_path"), "$.skill_path")
    if not skill_path.is_dir() or not (skill_path / "SKILL.md").is_file():
        raise _error("$.skill_path", "skill_path 必须指向包含 SKILL.md 的目录")

    baseline = _closed(root_value["baseline"], "$.baseline", BASELINE_FIELDS)
    _required(baseline, "$.baseline", {"mode"})
    if baseline["mode"] not in {"none", "snapshot"}:
        raise _error("$.baseline.mode", "baseline mode 必须是 none 或 snapshot")
    if baseline["mode"] == "snapshot":
        baseline_path = resolve_source(root, _string(baseline.get("path"), "$.baseline.path"), "$.baseline.path")
        if not (baseline_path / "SKILL.md").is_file():
            raise _error("$.baseline.path", "baseline path 必须包含 SKILL.md")
        if baseline_path == skill_path:
            raise _error("$.baseline.path", "baseline 不能与 candidate 指向同一目录")
    elif "path" in baseline:
        raise _error("$.baseline.path", "none baseline 不允许 path")

    runner = _closed(root_value["runner"], "$.runner", RUNNER_FIELDS)
    _required(runner, "$.runner", RUNNER_FIELDS)
    if runner["adapter"] not in {"fake", "codex-cli"}:
        raise _error("$.runner.adapter", "adapter 必须是 fake 或 codex-cli")
    _string(runner["model"], "$.runner.model")
    if runner["sandbox"] not in {"read-only", "workspace-write"}:
        raise _error("$.runner.sandbox", "不允许 danger-full-access")
    _positive_int(
        runner["timeout_seconds"],
        "$.runner.timeout_seconds",
        maximum=MAX_TIMEOUT_SECONDS,
    )
    _positive_int(runner["repetitions"], "$.runner.repetitions", maximum=MAX_REPETITIONS)
    _positive_int(runner["concurrency"], "$.runner.concurrency")
    if runner["concurrency"] > 4:
        raise _error("$.runner.concurrency", "首版最大并发为 4")
    if runner["network_access"] is not False:
        raise _error("$.runner.network_access", "首版 case 必须关闭网络")

    budgets = _closed(root_value["budgets"], "$.budgets", BUDGET_FIELDS)
    _required(budgets, "$.budgets", BUDGET_FIELDS)
    budget_limits = {
        "max_agent_runs": MAX_AGENT_RUNS,
        "max_judge_runs": MAX_JUDGE_RUNS,
        "max_wall_seconds": MAX_WALL_SECONDS,
    }
    for field, maximum in budget_limits.items():
        _positive_int(budgets[field], f"$.budgets.{field}", maximum=maximum)

    gates = _closed(root_value["gates"], "$.gates", GATE_FIELDS)
    _required(gates, "$.gates", GATE_FIELDS)
    _ratio(gates["trigger_threshold"], "$.gates.trigger_threshold")
    _ratio(gates["required_case_pass_rate"], "$.gates.required_case_pass_rate")
    if not isinstance(gates["judge_required"], bool):
        raise _error("$.gates.judge_required", "judge_required 必须是 boolean")

    cases = root_value["cases"]
    if not isinstance(cases, list) or not cases:
        raise _error("$.cases", "cases 必须是非空数组")
    if len(cases) > MAX_CASES:
        raise _error("$.cases", f"最多允许 {MAX_CASES} 项")
    case_ids: set[str] = set()
    for index, case in enumerate(cases):
        parsed = _validate_case(case, f"$.cases[{index}]", root)
        if parsed["id"] in case_ids:
            raise _error(f"$.cases[{index}].id", "case id 重复")
        case_ids.add(parsed["id"])
    return SuiteDocument(path=path.resolve(), root=root, data=root_value)


def load_suite(path: Path) -> SuiteDocument:
    try:
        if path.stat().st_size > MAX_SUITE_BYTES:
            raise SuiteError(f"suite 超过 {MAX_SUITE_BYTES} bytes", path="$")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SuiteError(f"suite 不存在：{path}", path="$") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SuiteError(f"无法解析 suite：{exc}", path="$") from exc
    return validate_suite(value, path=path)
