"""确定性评分、人工反馈与盲化 swap judge 协议。"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .budgets import implementation_identity
from .errors import ExecutionError, SuiteError
from .run_contracts import validate_run_manifest


MAX_GRADE_INPUT_BYTES = 16 * 1024 * 1024
MAX_GRADE_RECORDS = 256
JUDGE_FIELDS = {"task_id", "winner", "confidence", "rationale"}
HUMAN_FIELDS = {"record_key", "label", "notes"}
GATE_FIELDS = {"trigger_threshold", "required_case_pass_rate", "judge_required"}
VARIANT_MARKER = re.compile(r"(?i)(?<![a-z0-9])(candidate|baseline)(?![a-z0-9])")


def load_json_object(path: Path, *, max_bytes: int = MAX_GRADE_INPUT_BYTES) -> dict[str, Any]:
    """有界读取 grader 输入，拒绝非 object 根。"""
    try:
        if path.stat().st_size > max_bytes:
            raise ExecutionError(f"评分输入超过 {max_bytes} bytes")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ExecutionError(f"评分输入不存在：{path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExecutionError(f"无法读取评分输入：{exc}") from exc
    if not isinstance(value, dict):
        raise SuiteError("评分输入根必须是 JSON object", path="$")
    return value


def _record_key(record: dict[str, Any]) -> str:
    return f"{record.get('case_id')}:{record.get('repetition')}:{record.get('variant')}"


def _assertion_count(counts: dict[str, Any], name: str) -> int | None:
    value = counts.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def grade_record(record: dict[str, Any]) -> dict[str, Any]:
    """机械解释单条 run record，不使用回答文本猜测成功。"""
    runner = record.get("runner") if isinstance(record.get("runner"), dict) else {}
    assertions = record.get("assertions") if isinstance(record.get("assertions"), dict) else None
    trigger = (
        {"expected": record.get("expected_trigger"), "observed": record.get("observed_trigger")}
        if record.get("mode") == "trigger"
        else None
    )
    if runner.get("outcome") != "passed":
        passed, failure = False, "runner_failure"
    elif record.get("mode") == "trigger":
        if not isinstance(trigger["expected"], bool) or not isinstance(trigger["observed"], bool):
            passed, failure = False, "invalid_trigger_evidence"
        else:
            passed = trigger["expected"] == trigger["observed"]
            failure = None if passed else "trigger_mismatch"
    elif assertions is None:
        passed, failure = False, "missing_assertion_evidence"
    else:
        counts = assertions.get("counts") if isinstance(assertions.get("counts"), dict) else {}
        normalized_counts = {name: _assertion_count(counts, name) for name in ("PASS", "FAIL", "ERROR")}
        results = assertions.get("results")
        if any(value is None for value in normalized_counts.values()):
            passed, failure = False, "invalid_assertion_evidence"
        elif not isinstance(results, list) or not all(
            isinstance(item, dict) and item.get("status") in {"PASS", "FAIL", "ERROR"}
            for item in results
        ):
            passed, failure = False, "invalid_assertion_evidence"
        elif Counter(item["status"] for item in results) != Counter(normalized_counts):
            passed, failure = False, "invalid_assertion_evidence"
        elif assertions.get("status") != (
            "ERROR" if normalized_counts["ERROR"] else "FAIL" if normalized_counts["FAIL"] else "PASS"
        ):
            passed, failure = False, "inconsistent_assertion_summary"
        elif normalized_counts["ERROR"] > 0:
            passed, failure = False, "assertion_error"
        elif normalized_counts["FAIL"] > 0:
            passed, failure = False, "requirement_failure"
        else:
            passed, failure = assertions.get("status") == "PASS", None
            if not passed:
                failure = "inconsistent_assertion_summary"
    return {
        "record_key": _record_key(record),
        "case_id": record.get("case_id"),
        "mode": record.get("mode"),
        "split": record.get("split"),
        "variant": record.get("variant"),
        "repetition": record.get("repetition"),
        "pairing": record.get("pairing", {}),
        "deterministic": {
            "status": "PASS" if passed else "FAIL",
            "passed": passed,
            "failure_type": failure,
            "assertions": assertions,
        },
        "usage": runner.get("usage", {}),
        "provenance": runner.get("provenance", {}),
        "duration_seconds": runner.get("duration_seconds"),
        "trigger": trigger,
    }


def _human_feedback(value: Any) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise SuiteError("human feedback 必须是数组", path="$.human_feedback")
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(value):
        path = f"$.human_feedback[{index}]"
        if not isinstance(item, dict) or set(item) - HUMAN_FIELDS:
            raise SuiteError("human feedback 字段无效", path=path)
        if set(item) != HUMAN_FIELDS or item["label"] not in {"pass", "fail", "inconclusive"}:
            raise SuiteError("human feedback 必须包含 record_key/label/notes", path=path)
        if not isinstance(item["record_key"], str) or not item["record_key"]:
            raise SuiteError("human feedback record_key 必须是非空字符串", path=f"{path}.record_key")
        if not isinstance(item["notes"], str):
            raise SuiteError("human feedback notes 必须是字符串", path=f"{path}.notes")
        key = str(item["record_key"])
        if key in result:
            raise SuiteError("human feedback record_key 重复", path=f"{path}.record_key")
        result[key] = dict(item)
    return result


def grade_manifest(
    manifest: dict[str, Any],
    *,
    human_feedback: Any = None,
    judge_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = validate_run_manifest(manifest)
    fingerprint = manifest.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise SuiteError("run manifest 缺少非空 fingerprint", path="$.fingerprint")
    records = manifest.get("records")
    if not isinstance(records, list):
        raise SuiteError("run manifest 缺少 records 数组", path="$.records")
    if len(records) > MAX_GRADE_RECORDS:
        raise SuiteError(f"run manifest records 不能超过 {MAX_GRADE_RECORDS} 项", path="$.records")
    gates = manifest.get("gates")
    if not isinstance(gates, dict) or set(gates) != GATE_FIELDS:
        raise SuiteError("run manifest gates 必须使用闭合字段", path="$.gates")
    for field in ("trigger_threshold", "required_case_pass_rate"):
        value = gates[field]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
            raise SuiteError("gate threshold 必须在 0 到 1", path=f"$.gates.{field}")
    if not isinstance(gates["judge_required"], bool):
        raise SuiteError("judge_required 必须是 boolean", path="$.gates.judge_required")
    lab_identity = manifest.get("lab_identity")
    if not isinstance(lab_identity, dict) or set(lab_identity) != {"tree_sha256", "file_count"}:
        raise SuiteError("run manifest lab_identity 必须使用闭合字段", path="$.lab_identity")
    lab_tree_sha256 = lab_identity.get("tree_sha256")
    if not isinstance(lab_tree_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", lab_tree_sha256):
        raise SuiteError("lab tree_sha256 必须是 SHA-256", path="$.lab_identity.tree_sha256")
    if (
        not isinstance(lab_identity.get("file_count"), int)
        or isinstance(lab_identity["file_count"], bool)
        or lab_identity["file_count"] < 1
    ):
        raise SuiteError("lab file_count 必须是正整数", path="$.lab_identity.file_count")
    humans = _human_feedback(human_feedback)
    graded = []
    record_keys: set[str] = set()
    for raw in records:
        if not isinstance(raw, dict):
            raise SuiteError("run record 必须是 object", path="$.records")
        item = grade_record(raw)
        if item["record_key"] in record_keys:
            raise SuiteError(f"run record key 重复：{item['record_key']}", path="$.records")
        record_keys.add(item["record_key"])
        if item["provenance"].get("fingerprint") != fingerprint:
            raise SuiteError(
                f"run record fingerprint 与 manifest 不一致：{item['record_key']}",
                path="$.records",
            )
        if item["provenance"].get("lab_tree_sha256") != lab_tree_sha256:
            raise SuiteError(
                f"run record lab identity 与 manifest 不一致：{item['record_key']}",
                path="$.records",
            )
        item["human_feedback"] = humans.get(item["record_key"])
        graded.append(item)
    unknown_feedback = sorted(set(humans) - {item["record_key"] for item in graded})
    if unknown_feedback:
        raise SuiteError(f"human feedback 引用了未知 record：{unknown_feedback[0]}", path="$.human_feedback")
    grader_identity = implementation_identity()
    return {
        "schema_version": 1,
        "suite_id": manifest.get("suite_id"),
        "run_id": manifest.get("run_id"),
        "fingerprint": fingerprint,
        "source_identity": manifest.get("source_identity", {}),
        "lab_identity": dict(lab_identity),
        "grader_identity": {
            "tree_sha256": grader_identity["tree_sha256"],
            "file_count": grader_identity["file_count"],
        },
        "gates": dict(gates),
        "records": graded,
        "judge": judge_result if judge_result is not None else {"status": "disabled", "authority": "none"},
    }


def _deidentify(value: Any) -> Any:
    """移除常见 variant 标识，避免 judge 从路径或标签识别身份。"""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            neutral_key = VARIANT_MARKER.sub("variant", str(key))
            if neutral_key in result:
                raise SuiteError("judge 去标识后发生字段冲突", path="$.judge.outputs")
            result[neutral_key] = _deidentify(item)
        return result
    if isinstance(value, list):
        return [_deidentify(item) for item in value]
    if isinstance(value, str):
        return VARIANT_MARKER.sub("variant", value)
    return value


def build_blind_swap_tasks(
    *,
    pair_id: str,
    candidate_output: Any,
    baseline_output: Any,
    rubric: str,
    seed: int,
) -> dict[str, Any]:
    """生成两份去标识 A/B 任务；映射必须与 public task 分开保存。"""
    rng = random.Random(seed)
    neutral_pair_id = VARIANT_MARKER.sub("variant", pair_id)
    first_a = "candidate" if rng.randrange(2) == 0 else "baseline"
    first_mapping = {"A": first_a, "B": "baseline" if first_a == "candidate" else "candidate"}
    second_mapping = {"A": first_mapping["B"], "B": first_mapping["A"]}
    outputs = {"candidate": _deidentify(candidate_output), "baseline": _deidentify(baseline_output)}
    public_tasks = []
    private_mappings: dict[str, dict[str, str]] = {}
    for suffix, mapping in (("forward", first_mapping), ("swap", second_mapping)):
        task_id = f"{neutral_pair_id}-{suffix}"
        public_tasks.append(
            {
                "protocol_version": 1,
                "task_id": task_id,
                "instruction": "仅依据 rubric 比较 Output A 与 Output B；返回 winner=A、B 或 tie。",
                "rubric": _deidentify(rubric),
                "outputs": {"A": outputs[mapping["A"]], "B": outputs[mapping["B"]]},
            }
        )
        private_mappings[task_id] = mapping
    return {"public_tasks": public_tasks, "private_mappings": private_mappings}


def _parse_judgment(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != JUDGE_FIELDS:
        raise SuiteError("judge result 必须使用闭合字段", path=path)
    if value["winner"] not in {"A", "B", "tie"}:
        raise SuiteError("judge winner 必须是 A、B 或 tie", path=f"{path}.winner")
    if not isinstance(value["task_id"], str) or not value["task_id"]:
        raise SuiteError("judge task_id 必须是非空字符串", path=f"{path}.task_id")
    confidence = value["confidence"]
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        raise SuiteError("judge confidence 必须在 0 到 1", path=f"{path}.confidence")
    if not isinstance(value["rationale"], str) or not value["rationale"].strip():
        raise SuiteError("judge rationale 必须是非空字符串", path=f"{path}.rationale")
    return dict(value)


def resolve_blind_swap(
    judgments: list[dict[str, Any]],
    private_mappings: dict[str, dict[str, str]],
    *,
    calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """解盲两次判断；方向冲突永远是 inconclusive。"""
    if not isinstance(judgments, list) or not isinstance(private_mappings, dict):
        raise SuiteError("blind swap judgment 与映射类型无效", path="$.judge")
    if len(judgments) != 2 or len(private_mappings) != 2:
        raise SuiteError("blind swap 必须恰好包含两次 judgment 与映射", path="$.judge")
    translated: list[str] = []
    confidences: list[float] = []
    task_ids: set[str] = set()
    for index, raw in enumerate(judgments):
        item = _parse_judgment(raw, f"$.judge[{index}]")
        task_id = item["task_id"]
        if task_id in task_ids:
            raise SuiteError("blind swap judgment task_id 重复", path=f"$.judge[{index}].task_id")
        task_ids.add(task_id)
        mapping = private_mappings.get(task_id)
        if not mapping or set(mapping) != {"A", "B"} or set(mapping.values()) != {"candidate", "baseline"}:
            raise SuiteError("judge task_id 缺少有效 private mapping", path=f"$.judge[{index}].task_id")
        translated.append("tie" if item["winner"] == "tie" else mapping[item["winner"]])
        confidences.append(float(item["confidence"]))
    if task_ids != set(private_mappings):
        raise SuiteError("blind swap judgment 与 private mapping 不完全对应", path="$.judge")

    calibrated = False
    if calibration is not None:
        if not isinstance(calibration, dict) or set(calibration) != {"sample_count", "agreement_rate"}:
            raise SuiteError("calibration 必须包含 sample_count 与 agreement_rate", path="$.calibration")
        sample_count = calibration.get("sample_count")
        agreement_rate = calibration.get("agreement_rate")
        if not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count < 0:
            raise SuiteError("calibration sample_count 必须是非负整数", path="$.calibration.sample_count")
        if (
            not isinstance(agreement_rate, (int, float))
            or isinstance(agreement_rate, bool)
            or not 0 <= agreement_rate <= 1
        ):
            raise SuiteError("calibration agreement_rate 必须在 0 到 1", path="$.calibration.agreement_rate")
        calibrated = sample_count >= 5 and agreement_rate >= 0.8
    decision = translated[0] if translated[0] == translated[1] else "inconclusive"
    return {
        "status": decision,
        "authority": "decision" if calibrated and decision != "inconclusive" else "advisory",
        "calibrated": calibrated,
        "translated_winners": translated,
        "mean_confidence": sum(confidences) / len(confidences),
    }
