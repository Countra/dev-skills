"""当前唯一数据协议的闭合校验器。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .errors import ContractError
from .paths import hash_document
from .static_contract import validate_static_evidence

SCHEMA_VERSION = 1
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CHECK_STATUSES = {"pass", "warn", "fail", "not_applicable"}
CASE_KINDS = {"trigger-positive", "trigger-near-miss", "behavior"}
OBSERVATION_STATUSES = {"pass", "fail", "inconclusive"}
OBSERVATION_DECISIONS = {"not_requested", "requested", "provided"}
SEMANTIC_DIMENSIONS = (
    "invocation_boundary",
    "workflow_completeness",
    "information_architecture",
    "tool_contract",
    "safety_and_permissions",
    "verification_and_delivery",
    "scope_and_composability",
)


def _error(message: str, path: str, *, code: str = "CONTRACT_INVALID") -> ContractError:
    return ContractError(message, code=code, path=path)


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error("必须是 object", path)
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error("必须是 array", path)
    return value


def _string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise _error("必须是非空字符串", path)
    return value


def _closed(
    value: dict[str, Any],
    path: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing:
        raise _error(f"缺少字段：{', '.join(missing)}", path)
    if unknown:
        raise _error(f"存在未知字段：{', '.join(unknown)}", path)


def _identifier(value: Any, path: str) -> str:
    text = _string(value, path)
    if not IDENTIFIER.fullmatch(text):
        raise _error("标识符格式无效", path)
    return text


def _sha256(value: Any, path: str) -> str:
    text = _string(value, path)
    if not SHA256.fullmatch(text):
        raise _error("必须是小写 SHA-256", path)
    return text


def _relative(value: Any, path: str) -> str:
    text = _string(value, path)
    candidate = Path(text)
    normalized = text.replace("\\", "/")
    if (
        candidate.is_absolute()
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or ".." in normalized.split("/")
    ):
        raise _error("必须是无父目录跳转的相对路径", path)
    return text


def _string_array(value: Any, path: str, *, allow_empty: bool = True) -> list[str]:
    items = _array(value, path)
    if not allow_empty and not items:
        raise _error("数组不能为空", path)
    return [_string(item, f"{path}[{index}]") for index, item in enumerate(items)]


def load_json_document(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > 1_048_576:
            raise _error("JSON 文档超过 1 MiB 上限", "$")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise _error("JSON 文档不存在", "$", code="CONTRACT_FILE_MISSING") from exc
    except UnicodeDecodeError as exc:
        raise _error("JSON 文档不是有效 UTF-8", "$") from exc
    except json.JSONDecodeError as exc:
        raise _error(f"JSON 语法无效：{exc.msg}", f"$:{exc.lineno}:{exc.colno}") from exc
    return _object(value, "$")


def validate_suite(value: dict[str, Any]) -> dict[str, Any]:
    _closed(
        value,
        "$",
        required={
            "schema_version",
            "suite_id",
            "candidate",
            "baseline",
            "decision_question",
            "observation_policy",
            "cases",
        },
    )
    if value["schema_version"] != SCHEMA_VERSION:
        raise _error("schema_version 必须为 1", "$.schema_version")
    _identifier(value["suite_id"], "$.suite_id")
    _relative(value["candidate"], "$.candidate")
    if value["baseline"] is not None:
        _relative(value["baseline"], "$.baseline")
        if value["baseline"] == value["candidate"]:
            raise _error("baseline 不能与 candidate 相同", "$.baseline")
    _string(value["decision_question"], "$.decision_question")

    policy = _object(value["observation_policy"], "$.observation_policy")
    _closed(policy, "$.observation_policy", required={"required_variants", "require_independent_session"})
    variants = _string_array(policy["required_variants"], "$.observation_policy.required_variants", allow_empty=False)
    allowed_variants = {"candidate"} | ({"baseline"} if value["baseline"] else set())
    if len(set(variants)) != len(variants) or not set(variants) <= allowed_variants:
        raise _error("required_variants 包含重复或不可用 variant", "$.observation_policy.required_variants")
    if "candidate" not in variants:
        raise _error("required_variants 必须包含 candidate", "$.observation_policy.required_variants")
    if policy["require_independent_session"] is not True:
        raise _error("人工观察必须要求独立会话", "$.observation_policy.require_independent_session")

    cases = _array(value["cases"], "$.cases")
    if not cases:
        raise _error("cases 不能为空", "$.cases")
    case_ids: set[str] = set()
    kinds: set[str] = set()
    for index, raw_case in enumerate(cases):
        path = f"$.cases[{index}]"
        case = _object(raw_case, path)
        _closed(case, path, required={"id", "kind", "prompt", "expected_observation", "inputs"})
        case_id = _identifier(case["id"], f"{path}.id")
        if case_id in case_ids:
            raise _error("case id 重复", f"{path}.id")
        case_ids.add(case_id)
        kind = _string(case["kind"], f"{path}.kind")
        if kind not in CASE_KINDS:
            raise _error("case kind 不受支持", f"{path}.kind")
        kinds.add(kind)
        _string(case["prompt"], f"{path}.prompt")
        _string(case["expected_observation"], f"{path}.expected_observation")
        inputs = _array(case["inputs"], f"{path}.inputs")
        seen_inputs: set[str] = set()
        for input_index, item in enumerate(inputs):
            input_path = _relative(item, f"{path}.inputs[{input_index}]")
            if input_path in seen_inputs:
                raise _error("input 路径重复", f"{path}.inputs[{input_index}]")
            seen_inputs.add(input_path)
    if kinds != CASE_KINDS:
        missing = ", ".join(sorted(CASE_KINDS - kinds))
        raise _error(f"缺少必要 case kind：{missing}", "$.cases")
    return value


def load_suite(path: Path) -> dict[str, Any]:
    return validate_suite(load_json_document(path))


def validate_semantic_review(value: dict[str, Any]) -> dict[str, Any]:
    _closed(
        value,
        "$",
        required={
            "schema_version",
            "evaluation_id",
            "candidate_tree_sha256",
            "dimensions",
            "assumptions",
            "limitations",
            "observation_decision",
        },
    )
    if value["schema_version"] != SCHEMA_VERSION:
        raise _error("schema_version 必须为 1", "$.schema_version")
    _identifier(value["evaluation_id"], "$.evaluation_id")
    _sha256(value["candidate_tree_sha256"], "$.candidate_tree_sha256")
    _string_array(value["assumptions"], "$.assumptions")
    _string_array(value["limitations"], "$.limitations", allow_empty=False)
    if value["observation_decision"] not in OBSERVATION_DECISIONS:
        raise _error("observation_decision 无效", "$.observation_decision")

    dimensions = _array(value["dimensions"], "$.dimensions")
    seen: set[str] = set()
    for index, raw_dimension in enumerate(dimensions):
        path = f"$.dimensions[{index}]"
        dimension = _object(raw_dimension, path)
        _closed(
            dimension,
            path,
            required={"dimension", "status", "summary", "evidence"},
            optional={"recommendation"},
        )
        name = _string(dimension["dimension"], f"{path}.dimension")
        if name not in SEMANTIC_DIMENSIONS or name in seen:
            raise _error("dimension 未知或重复", f"{path}.dimension")
        seen.add(name)
        status = _string(dimension["status"], f"{path}.status")
        if status not in CHECK_STATUSES:
            raise _error("status 无效", f"{path}.status")
        _string(dimension["summary"], f"{path}.summary")
        evidence = _array(dimension["evidence"], f"{path}.evidence")
        if not evidence:
            raise _error("每个维度至少需要一条 evidence", f"{path}.evidence")
        for evidence_index, raw_evidence in enumerate(evidence):
            evidence_path = f"{path}.evidence[{evidence_index}]"
            item = _object(raw_evidence, evidence_path)
            _closed(item, evidence_path, required={"path", "detail"})
            _relative(item["path"], f"{evidence_path}.path")
            _string(item["detail"], f"{evidence_path}.detail")
        if status in {"warn", "fail"}:
            _string(dimension.get("recommendation"), f"{path}.recommendation")
    if seen != set(SEMANTIC_DIMENSIONS):
        missing = ", ".join(sorted(set(SEMANTIC_DIMENSIONS) - seen))
        raise _error(f"缺少语义审查维度：{missing}", "$.dimensions")
    return value


def load_semantic_review(path: Path) -> dict[str, Any]:
    return validate_semantic_review(load_json_document(path))


def validate_observation_bundle(value: dict[str, Any]) -> dict[str, Any]:
    _closed(value, "$", required={"schema_version", "packet_fingerprint", "declared_by", "sessions"})
    if value["schema_version"] != SCHEMA_VERSION:
        raise _error("schema_version 必须为 1", "$.schema_version")
    _sha256(value["packet_fingerprint"], "$.packet_fingerprint")
    if value["declared_by"] != "user":
        raise _error("declared_by 必须明确为 user", "$.declared_by")
    sessions = _array(value["sessions"], "$.sessions")
    seen: set[tuple[str, str]] = set()
    for index, raw_session in enumerate(sessions):
        path = f"$.sessions[{index}]"
        session = _object(raw_session, path)
        _closed(
            session,
            path,
            required={"case_id", "variant", "session_ref", "status", "notes", "artifacts"},
        )
        variant = _string(session["variant"], f"{path}.variant")
        if variant not in {"candidate", "baseline"}:
            raise _error("observation variant 无效", f"{path}.variant")
        key = (
            _identifier(session["case_id"], f"{path}.case_id"),
            variant,
        )
        if key in seen:
            raise _error("同一 case/variant observation 重复", path)
        seen.add(key)
        _string(session["session_ref"], f"{path}.session_ref")
        if session["status"] not in OBSERVATION_STATUSES:
            raise _error("observation status 无效", f"{path}.status")
        _string(session["notes"], f"{path}.notes", allow_empty=True)
        for artifact_index, raw_artifact in enumerate(_array(session["artifacts"], f"{path}.artifacts")):
            artifact_path = f"{path}.artifacts[{artifact_index}]"
            artifact = _object(raw_artifact, artifact_path)
            _closed(artifact, artifact_path, required={"path"}, optional={"sha256"})
            _relative(artifact["path"], f"{artifact_path}.path")
            if "sha256" in artifact:
                _sha256(artifact["sha256"], f"{artifact_path}.sha256")
    return value


def load_observation_bundle(path: Path) -> dict[str, Any]:
    return validate_observation_bundle(load_json_document(path))


def _source_binding(value: Any, path: str) -> dict[str, Any]:
    source = _object(value, path)
    _closed(source, path, required={"path", "tree_sha256", "file_count", "total_bytes"})
    _relative(source["path"], f"{path}.path")
    _sha256(source["tree_sha256"], f"{path}.tree_sha256")
    for field in ("file_count", "total_bytes"):
        if not isinstance(source[field], int) or isinstance(source[field], bool) or source[field] < 0:
            raise _error("必须是非负整数", f"{path}.{field}")
    return source


def validate_packet(value: dict[str, Any]) -> dict[str, Any]:
    _closed(
        value,
        "$",
        required={
            "schema_version", "packet_id", "suite_id", "generated_at",
            "execution_mode", "sources", "cases", "packet_fingerprint",
        },
    )
    if value["schema_version"] != SCHEMA_VERSION:
        raise _error("schema_version 必须为 1", "$.schema_version")
    _identifier(value["packet_id"], "$.packet_id")
    _identifier(value["suite_id"], "$.suite_id")
    _string(value["generated_at"], "$.generated_at")
    if value["execution_mode"] != "user_operated_independent_session":
        raise _error("packet 只能声明用户独立会话模式", "$.execution_mode")
    sources = _object(value["sources"], "$.sources")
    _closed(sources, "$.sources", required={"candidate", "baseline"})
    _source_binding(sources["candidate"], "$.sources.candidate")
    if sources["baseline"] is not None:
        _source_binding(sources["baseline"], "$.sources.baseline")

    cases = _array(value["cases"], "$.cases")
    if len(cases) < len(CASE_KINDS):
        raise _error("packet 至少需要三类 case", "$.cases")
    seen: set[tuple[str, str]] = set()
    variant_kinds: dict[str, set[str]] = {}
    for index, raw_case in enumerate(cases):
        path = f"$.cases[{index}]"
        case = _object(raw_case, path)
        _closed(
            case,
            path,
            required={
                "case_id",
                "kind",
                "variant",
                "prompt",
                "expected_observation",
                "inputs",
                "case_fingerprint",
            },
        )
        variant = _string(case["variant"], f"{path}.variant")
        if variant not in {"candidate", "baseline"}:
            raise _error("packet variant 无效", f"{path}.variant")
        if variant == "baseline" and sources["baseline"] is None:
            raise _error("packet 未绑定 baseline source", f"{path}.variant")
        key = (
            _identifier(case["case_id"], f"{path}.case_id"),
            variant,
        )
        if key in seen:
            raise _error("packet case/variant 重复", path)
        seen.add(key)
        if case["kind"] not in CASE_KINDS:
            raise _error("packet case kind 无效", f"{path}.kind")
        variant_kinds.setdefault(variant, set()).add(case["kind"])
        _string(case["prompt"], f"{path}.prompt")
        _string(case["expected_observation"], f"{path}.expected_observation")
        input_paths: set[str] = set()
        for input_index, raw_input in enumerate(_array(case["inputs"], f"{path}.inputs")):
            input_path = f"{path}.inputs[{input_index}]"
            item = _object(raw_input, input_path)
            _closed(item, input_path, required={"path", "size", "sha256"})
            relative = _relative(item["path"], f"{input_path}.path")
            if relative in input_paths:
                raise _error("packet input 路径重复", f"{input_path}.path")
            input_paths.add(relative)
            _sha256(item["sha256"], f"{input_path}.sha256")
            if not isinstance(item["size"], int) or isinstance(item["size"], bool) or item["size"] < 0:
                raise _error("size 必须是非负整数", f"{input_path}.size")
        case_fingerprint = _sha256(case["case_fingerprint"], f"{path}.case_fingerprint")
        case_payload = {key: item for key, item in case.items() if key != "case_fingerprint"}
        if hash_document(case_payload) != case_fingerprint:
            raise _error("case fingerprint 与内容不一致", f"{path}.case_fingerprint")
    if "candidate" not in variant_kinds:
        raise _error("packet cases 必须包含 candidate variant", "$.cases")
    for variant, kinds in variant_kinds.items():
        if kinds != CASE_KINDS:
            missing = ", ".join(sorted(CASE_KINDS - kinds))
            raise _error(f"{variant} 缺少 case kind：{missing}", "$.cases")
    fingerprint = _sha256(value["packet_fingerprint"], "$.packet_fingerprint")
    payload = {key: item for key, item in value.items() if key != "packet_fingerprint"}
    if hash_document(payload) != fingerprint:
        raise _error("packet fingerprint 与内容不一致", "$.packet_fingerprint")
    return value


def load_packet(path: Path) -> dict[str, Any]:
    return validate_packet(load_json_document(path))


def validate_imported_observation(value: dict[str, Any]) -> dict[str, Any]:
    _closed(
        value,
        "$",
        required={
            "schema_version", "generated_at", "packet_fingerprint", "candidate_tree_sha256",
            "baseline_tree_sha256", "coverage", "sessions", "provenance",
        },
    )
    if value["schema_version"] != SCHEMA_VERSION:
        raise _error("schema_version 必须为 1", "$.schema_version")
    _sha256(value["packet_fingerprint"], "$.packet_fingerprint")
    _sha256(value["candidate_tree_sha256"], "$.candidate_tree_sha256")
    if value["baseline_tree_sha256"] is not None:
        _sha256(value["baseline_tree_sha256"], "$.baseline_tree_sha256")
    coverage = _object(value["coverage"], "$.coverage")
    _closed(coverage, "$.coverage", required={"expected", "observed", "missing", "status"})
    coverage_values: dict[str, list[str]] = {}
    for field in ("expected", "observed", "missing"):
        values = _string_array(
            coverage[field],
            f"$.coverage.{field}",
            allow_empty=field != "expected",
        )
        if len(values) != len(set(values)):
            raise _error("coverage 条目不能重复", f"$.coverage.{field}")
        coverage_values[field] = values
    if coverage["status"] not in {"complete", "partial"}:
        raise _error("coverage status 无效", "$.coverage.status")
    expected = set(coverage_values["expected"])
    observed = set(coverage_values["observed"])
    missing = set(coverage_values["missing"])
    if observed & missing or expected != observed | missing:
        raise _error("coverage expected/observed/missing 集合不一致", "$.coverage")
    if coverage["status"] != ("partial" if missing else "complete"):
        raise _error("coverage status 与 missing 集合不一致", "$.coverage.status")

    session_keys: set[str] = set()
    for index, raw_session in enumerate(_array(value["sessions"], "$.sessions")):
        path = f"$.sessions[{index}]"
        session = _object(raw_session, path)
        _closed(
            session,
            path,
            required={
                "case_id",
                "variant",
                "case_fingerprint",
                "session_ref",
                "status",
                "notes",
                "artifacts",
            },
        )
        case_id = _identifier(session["case_id"], f"{path}.case_id")
        variant = _string(session["variant"], f"{path}.variant")
        if variant not in {"candidate", "baseline"}:
            raise _error("variant 无效", f"{path}.variant")
        session_key = f"{case_id}::{variant}"
        if session_key in session_keys:
            raise _error("imported session 重复", path)
        session_keys.add(session_key)
        _sha256(session["case_fingerprint"], f"{path}.case_fingerprint")
        _string(session["session_ref"], f"{path}.session_ref")
        if session["status"] not in OBSERVATION_STATUSES:
            raise _error("session status 无效", f"{path}.status")
        _string(session["notes"], f"{path}.notes", allow_empty=True)
        for artifact_index, raw_artifact in enumerate(_array(session["artifacts"], f"{path}.artifacts")):
            artifact_path = f"{path}.artifacts[{artifact_index}]"
            artifact = _object(raw_artifact, artifact_path)
            _closed(artifact, artifact_path, required={"path", "size", "sha256"})
            _relative(artifact["path"], f"{artifact_path}.path")
            _sha256(artifact["sha256"], f"{artifact_path}.sha256")
            if (
                not isinstance(artifact["size"], int)
                or isinstance(artifact["size"], bool)
                or artifact["size"] < 0
            ):
                raise _error("artifact size 必须是非负整数", f"{artifact_path}.size")
    if session_keys != observed:
        raise _error("sessions 与 coverage.observed 不一致", "$.sessions")
    provenance = _object(value["provenance"], "$.provenance")
    _closed(
        provenance,
        "$.provenance",
        required={"declared_by", "import_mode", "agent_calls", "network_calls"},
    )
    if provenance != {
        "declared_by": "user",
        "import_mode": "validation_only",
        "agent_calls": 0,
        "network_calls": 0,
    }:
        raise _error("provenance 必须声明纯校验导入", "$.provenance")
    return value


def load_imported_observation(path: Path) -> dict[str, Any]:
    return validate_imported_observation(load_json_document(path))
