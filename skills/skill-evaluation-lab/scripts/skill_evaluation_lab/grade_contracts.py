"""Grade 文档的闭合结构与跨阶段身份校验。"""

from __future__ import annotations

import re
from typing import Any

from .errors import SuiteError
from .run_contracts import validate_assertion_summary


ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ROOT_FIELDS = {
    "schema_version",
    "run_state",
    "run_status",
    "run_error",
    "suite_id",
    "run_id",
    "fingerprint",
    "source_identity",
    "lab_identity",
    "grader_identity",
    "gates",
    "records",
    "judge",
}
RECORD_FIELDS = {
    "record_key",
    "case_id",
    "mode",
    "split",
    "variant",
    "repetition",
    "pairing",
    "deterministic",
    "usage",
    "provenance",
    "duration_seconds",
    "trigger",
    "human_feedback",
}
PAIRING_FIELDS = {
    "pair_key",
    "prompt_sha256",
    "inputs",
    "model",
    "sandbox",
    "timeout_seconds",
    "network_access",
    "skill_snapshot",
}
PROVENANCE_FIELDS = {
    "adapter",
    "cli_version",
    "model",
    "sandbox",
    "permission_profile",
    "network_access",
    "fingerprint",
    "lab_tree_sha256",
    "prompt_sha256",
    "case_id",
    "attempt",
    "variant",
    "skill_tree_sha256",
    "trace",
}
PROVENANCE_REQUIRED = {
    "adapter",
    "cli_version",
    "model",
    "sandbox",
    "network_access",
    "fingerprint",
    "lab_tree_sha256",
    "prompt_sha256",
    "case_id",
    "attempt",
    "variant",
}
TOKEN_FIELDS = {
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
}
MAX_RECORDS = 256


def _object(
    value: Any,
    path: str,
    fields: set[str],
    required: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SuiteError("必须是 JSON object", path=path)
    unknown = sorted(set(value) - fields)
    if unknown:
        raise SuiteError(f"存在未知字段：{unknown[0]}", path=f"{path}.{unknown[0]}")
    missing = sorted((required if required is not None else fields) - set(value))
    if missing:
        raise SuiteError(f"缺少必需字段：{missing[0]}", path=f"{path}.{missing[0]}")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SuiteError("必须是非空字符串", path=path)
    return value


def _sha256(value: Any, path: str) -> str:
    raw = _string(value, path)
    if not SHA256_PATTERN.fullmatch(raw):
        raise SuiteError("必须是小写 SHA-256", path=path)
    return raw


def _identity(value: Any, path: str) -> dict[str, Any]:
    item = _object(value, path, {"tree_sha256", "file_count"})
    _sha256(item["tree_sha256"], f"{path}.tree_sha256")
    count = item["file_count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise SuiteError("file_count 必须是正整数", path=f"{path}.file_count")
    return item


def _validate_error(value: Any, path: str, *, required: bool) -> None:
    if not required:
        if value is not None:
            raise SuiteError("completed grade 不允许 run_error", path=path)
        return
    item = _object(
        value,
        path,
        {"code", "message", "outcome", "path", "guidance"},
        {"code", "message", "outcome"},
    )
    for name in ("code", "message", "outcome"):
        _string(item[name], f"{path}.{name}")
    for name in ("path", "guidance"):
        if name in item and not isinstance(item[name], str):
            raise SuiteError("run_error 可选字段必须是字符串", path=f"{path}.{name}")


def _validate_gates(value: Any) -> dict[str, Any]:
    item = _object(
        value,
        "$.gates",
        {"trigger_threshold", "required_case_pass_rate", "judge_required"},
    )
    for name in ("trigger_threshold", "required_case_pass_rate"):
        threshold = item[name]
        if (
            not isinstance(threshold, (int, float))
            or isinstance(threshold, bool)
            or not 0 <= threshold <= 1
        ):
            raise SuiteError("gate threshold 必须在 0 到 1", path=f"$.gates.{name}")
    if not isinstance(item["judge_required"], bool):
        raise SuiteError("judge_required 必须是 boolean", path="$.gates.judge_required")
    return item


def _validate_judge(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SuiteError("judge 必须是 JSON object", path="$.judge")
    if value == {"status": "disabled", "authority": "none"}:
        return value
    item = _object(
        value,
        "$.judge",
        {"status", "authority", "calibrated", "translated_winners", "mean_confidence"},
    )
    if item["status"] not in {"candidate", "baseline", "tie", "inconclusive"}:
        raise SuiteError("judge status 无效", path="$.judge.status")
    if item["authority"] not in {"decision", "advisory"} or not isinstance(item["calibrated"], bool):
        raise SuiteError("judge authority/calibrated 无效", path="$.judge")
    winners = item["translated_winners"]
    if not isinstance(winners, list) or len(winners) != 2 or any(
        winner not in {"candidate", "baseline", "tie"} for winner in winners
    ):
        raise SuiteError("judge translated_winners 无效", path="$.judge.translated_winners")
    confidence = item["mean_confidence"]
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0 <= confidence <= 1
    ):
        raise SuiteError("judge mean_confidence 必须在 0 到 1", path="$.judge.mean_confidence")
    resolved_status = winners[0] if winners[0] == winners[1] else "inconclusive"
    expected_authority = "decision" if item["calibrated"] and resolved_status != "inconclusive" else "advisory"
    if item["status"] != resolved_status or item["authority"] != expected_authority:
        raise SuiteError("judge 结论与 swap/calibration 不一致", path="$.judge")
    return item


def _validate_record(
    value: Any,
    path: str,
    *,
    fingerprint: str,
    lab_tree_sha256: str,
    source_identity: dict[str, Any],
) -> None:
    item = _object(value, path, RECORD_FIELDS)
    case_id = _string(item["case_id"], f"{path}.case_id")
    if not ID_PATTERN.fullmatch(case_id):
        raise SuiteError("case_id 格式无效", path=f"{path}.case_id")
    if item["mode"] not in {"trigger", "behavior"} or item["split"] not in {
        "train",
        "validation",
        "holdout",
    }:
        raise SuiteError("mode 或 split 无效", path=path)
    if item["variant"] not in ({"candidate"} if item["mode"] == "trigger" else {"candidate", "baseline"}):
        raise SuiteError("variant 无效", path=f"{path}.variant")
    repetition = item["repetition"]
    if not isinstance(repetition, int) or isinstance(repetition, bool) or not 1 <= repetition <= 20:
        raise SuiteError("repetition 必须在 1 到 20", path=f"{path}.repetition")
    expected_key = f"{case_id}:{repetition}:{item['variant']}"
    if item["record_key"] != expected_key:
        raise SuiteError("record_key 与 case/repetition/variant 不一致", path=f"{path}.record_key")

    pairing = _object(item["pairing"], f"{path}.pairing", PAIRING_FIELDS)
    if pairing["pair_key"] != f"{case_id}:{repetition}":
        raise SuiteError("pair_key 与 case/repetition 不一致", path=f"{path}.pairing.pair_key")
    _sha256(pairing["prompt_sha256"], f"{path}.pairing.prompt_sha256")
    if (
        not isinstance(pairing["inputs"], list)
        or not all(isinstance(raw, str) for raw in pairing["inputs"])
        or not isinstance(pairing["timeout_seconds"], int)
        or isinstance(pairing["timeout_seconds"], bool)
        or pairing["timeout_seconds"] < 1
    ):
        raise SuiteError("pairing inputs/timeout 无效", path=f"{path}.pairing")
    _string(pairing["model"], f"{path}.pairing.model")
    if pairing["sandbox"] not in {"read-only", "workspace-write"} or pairing["network_access"] is not False:
        raise SuiteError("pairing sandbox/network 无效", path=f"{path}.pairing")
    if pairing["skill_snapshot"] not in {"candidate", "baseline", "none"}:
        raise SuiteError("pairing skill_snapshot 无效", path=f"{path}.pairing.skill_snapshot")

    deterministic = _object(
        item["deterministic"],
        f"{path}.deterministic",
        {"status", "passed", "failure_type", "assertions"},
    )
    if deterministic["status"] not in {"PASS", "FAIL"} or not isinstance(
        deterministic["passed"], bool
    ):
        raise SuiteError("deterministic status/passed 无效", path=f"{path}.deterministic")
    if (deterministic["status"] == "PASS") != deterministic["passed"]:
        raise SuiteError("deterministic status 与 passed 不一致", path=f"{path}.deterministic")
    failure_type = deterministic["failure_type"]
    if deterministic["passed"] and failure_type is not None:
        raise SuiteError("通过记录不允许 failure_type", path=f"{path}.deterministic.failure_type")
    if not deterministic["passed"] and (not isinstance(failure_type, str) or not failure_type):
        raise SuiteError("失败记录必须包含 failure_type", path=f"{path}.deterministic.failure_type")
    validate_assertion_summary(
        deterministic["assertions"],
        path=f"{path}.deterministic.assertions",
        mode=item["mode"],
    )

    usage = _object(item["usage"], f"{path}.usage", TOKEN_FIELDS, set())
    for name, count in usage.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise SuiteError("token count 必须是非负整数", path=f"{path}.usage.{name}")
    provenance = _object(
        item["provenance"],
        f"{path}.provenance",
        PROVENANCE_FIELDS,
        PROVENANCE_REQUIRED,
    )
    if provenance["fingerprint"] != fingerprint or provenance["lab_tree_sha256"] != lab_tree_sha256:
        raise SuiteError("grade record provenance identity 不一致", path=f"{path}.provenance")
    if provenance["adapter"] not in {"fake", "codex-cli"}:
        raise SuiteError("grade record adapter 无效", path=f"{path}.provenance.adapter")
    for name in ("cli_version", "model", "sandbox", "case_id", "variant"):
        _string(provenance[name], f"{path}.provenance.{name}")
    if provenance["network_access"] is not False:
        raise SuiteError("grade record network_access 必须为 false", path=f"{path}.provenance.network_access")
    if "permission_profile" in provenance:
        _string(provenance["permission_profile"], f"{path}.provenance.permission_profile")
    if "trace" in provenance and not isinstance(provenance["trace"], dict):
        raise SuiteError("grade record trace 必须是 object", path=f"{path}.provenance.trace")
    for name in ("prompt_sha256", "fingerprint", "lab_tree_sha256"):
        _sha256(provenance[name], f"{path}.provenance.{name}")
    if "skill_tree_sha256" in provenance:
        _sha256(provenance["skill_tree_sha256"], f"{path}.provenance.skill_tree_sha256")
    if provenance["case_id"] != case_id or provenance["variant"] != item["variant"]:
        raise SuiteError("grade record provenance case/variant 不一致", path=f"{path}.provenance")
    if provenance["attempt"] != repetition:
        raise SuiteError("grade record provenance attempt 不一致", path=f"{path}.provenance.attempt")
    if (
        provenance["model"] != pairing["model"]
        or provenance["sandbox"] != pairing["sandbox"]
        or provenance["prompt_sha256"] != pairing["prompt_sha256"]
    ):
        raise SuiteError("grade record provenance 执行条件不一致", path=f"{path}.provenance")
    source_variant = "candidate" if item["mode"] == "trigger" else pairing["skill_snapshot"]
    source = source_identity.get(source_variant)
    expected_skill_hash = source.get("tree_sha256") if isinstance(source, dict) else None
    if provenance.get("skill_tree_sha256") != expected_skill_hash:
        raise SuiteError("grade record skill identity 不一致", path=f"{path}.provenance.skill_tree_sha256")
    if item["duration_seconds"] is not None and (
        not isinstance(item["duration_seconds"], (int, float))
        or isinstance(item["duration_seconds"], bool)
        or item["duration_seconds"] < 0
    ):
        raise SuiteError("duration_seconds 必须是非负数或 null", path=f"{path}.duration_seconds")
    trigger = item["trigger"]
    if item["mode"] == "trigger":
        trigger = _object(trigger, f"{path}.trigger", {"expected", "observed"})
        if not isinstance(trigger["expected"], bool) or not isinstance(trigger["observed"], bool):
            raise SuiteError("trigger truth 必须是 boolean", path=f"{path}.trigger")
    elif trigger is not None:
        raise SuiteError("behavior grade record 不允许 trigger", path=f"{path}.trigger")
    feedback = item["human_feedback"]
    if feedback is not None:
        feedback = _object(feedback, f"{path}.human_feedback", {"record_key", "label", "notes"})
        if feedback["record_key"] != expected_key or feedback["label"] not in {
            "pass",
            "fail",
            "inconclusive",
        }:
            raise SuiteError("human feedback 与 record 不一致", path=f"{path}.human_feedback")
        if not isinstance(feedback["notes"], str):
            raise SuiteError("human feedback notes 必须是字符串", path=f"{path}.human_feedback.notes")


def validate_grade_document(value: Any) -> dict[str, Any]:
    """校验 se_grade 输出，防止 malformed grade 被报告层解释。"""
    grade = _object(value, "$", ROOT_FIELDS)
    if isinstance(grade["schema_version"], bool) or grade["schema_version"] != 1:
        raise SuiteError("schema_version 必须为 1", path="$.schema_version")
    suite_id = _string(grade["suite_id"], "$.suite_id")
    run_id = _string(grade["run_id"], "$.run_id")
    if not ID_PATTERN.fullmatch(suite_id) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise SuiteError("suite_id 或 run_id 格式无效", path="$")
    fingerprint = _sha256(grade["fingerprint"], "$.fingerprint")
    if grade["run_state"] not in {"completed", "failed"}:
        raise SuiteError("run_state 无效", path="$.run_state")
    expected_statuses = {"PASS", "FAIL"} if grade["run_state"] == "completed" else {"ERROR"}
    if grade["run_status"] not in expected_statuses:
        raise SuiteError("run_state 与 run_status 不一致", path="$.run_status")
    _validate_error(grade["run_error"], "$.run_error", required=grade["run_state"] == "failed")
    lab_identity = _identity(grade["lab_identity"], "$.lab_identity")
    _identity(grade["grader_identity"], "$.grader_identity")
    source = _object(grade["source_identity"], "$.source_identity", {"candidate", "baseline"})
    _identity(source["candidate"], "$.source_identity.candidate")
    if source["baseline"] != "none":
        _identity(source["baseline"], "$.source_identity.baseline")
    _validate_gates(grade["gates"])
    records = grade["records"]
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise SuiteError(f"records 必须是至多 {MAX_RECORDS} 项的数组", path="$.records")
    if grade["run_state"] == "completed" and not records:
        raise SuiteError("completed grade 必须包含 records", path="$.records")
    record_keys: set[str] = set()
    behavior_groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for index, record in enumerate(records):
        _validate_record(
            record,
            f"$.records[{index}]",
            fingerprint=fingerprint,
            lab_tree_sha256=lab_identity["tree_sha256"],
            source_identity=source,
        )
        key = record["record_key"]
        if key in record_keys:
            raise SuiteError("grade record_key 重复", path=f"$.records[{index}].record_key")
        record_keys.add(key)
        if record["mode"] == "behavior":
            pair_key = (record["case_id"], record["repetition"])
            behavior_groups.setdefault(pair_key, []).append(record)
    if grade["run_state"] == "completed":
        for pair in behavior_groups.values():
            if len(pair) != 2 or {record["variant"] for record in pair} != {"candidate", "baseline"}:
                raise SuiteError("completed grade 的 behavior pair 不完整", path="$.records")
            expected_order = ["candidate", "baseline"] if pair[0]["repetition"] % 2 else ["baseline", "candidate"]
            if [record["variant"] for record in pair] != expected_order:
                raise SuiteError("behavior pair 顺序未按 repetition 交替", path="$.records")
            left = {name: value for name, value in pair[0]["pairing"].items() if name != "skill_snapshot"}
            right = {name: value for name, value in pair[1]["pairing"].items() if name != "skill_snapshot"}
            if left != right:
                raise SuiteError("behavior pair 执行条件不一致", path="$.records")
    _validate_judge(grade["judge"])
    return grade
