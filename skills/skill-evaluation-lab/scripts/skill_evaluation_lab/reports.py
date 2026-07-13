"""从规范化 grade 构建 JSON 与 Markdown 决策证据。"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .errors import SuiteError
from .grade_contracts import validate_grade_document
from .metrics import cost_metrics, failure_taxonomy, paired_delta_metrics, quality_metrics, trigger_metrics


PROVENANCE_FIELDS = (
    "fingerprint",
    "lab_tree_sha256",
    "adapter",
    "cli_version",
    "model",
    "sandbox",
    "network_access",
    "permission_profile",
)
MAX_REPORT_RECORDS = 256


def _provenance_groups(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: Counter[tuple[Any, ...]] = Counter()
    for record in records:
        value = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
        groups[tuple(value.get(field) for field in PROVENANCE_FIELDS)] += 1
    return [
        {**dict(zip(PROVENANCE_FIELDS, key)), "record_count": count}
        for key, count in sorted(groups.items(), key=lambda item: tuple(str(value) for value in item[0]))
    ]


def _case_results(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for record in records:
        deterministic = record.get("deterministic") if isinstance(record.get("deterministic"), dict) else {}
        assertion_summary = deterministic.get("assertions")
        counts = assertion_summary.get("counts") if isinstance(assertion_summary, dict) else None
        human = record.get("human_feedback") if isinstance(record.get("human_feedback"), dict) else None
        results.append(
            {
                "record_key": record.get("record_key"),
                "case_id": record.get("case_id"),
                "mode": record.get("mode"),
                "split": record.get("split"),
                "variant": record.get("variant"),
                "repetition": record.get("repetition"),
                "status": deterministic.get("status"),
                "passed": deterministic.get("passed"),
                "failure_type": deterministic.get("failure_type"),
                "assertion_counts": counts if isinstance(counts, dict) else None,
                "trigger": record.get("trigger") if isinstance(record.get("trigger"), dict) else None,
                "duration_seconds": record.get("duration_seconds"),
                "human_label": human.get("label") if human else None,
            }
        )
    return results


def _quality_gate(
    quality: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    name: str,
    mode: str,
    threshold: float,
) -> dict[str, Any]:
    sample_count = sum(
        record.get("variant") == "candidate" and record.get("mode") == mode for record in records
    )
    if sample_count == 0:
        return {
            "name": name,
            "required": False,
            "available": False,
            "status": "not_applicable",
            "threshold": threshold,
            "actual": None,
            "sample_count": 0,
            "passed": None,
            "reason": f"no_candidate_{mode}_cases",
        }
    metric = quality.get("candidate", {}).get("by_mode", {}).get(mode, {})
    actual = metric.get("pass_rate")
    available = isinstance(actual, (int, float)) and not isinstance(actual, bool)
    passed = bool(available and actual >= threshold)
    return {
        "name": name,
        "required": True,
        "available": available,
        "status": "passed" if passed else "failed",
        "threshold": threshold,
        "actual": actual if available else None,
        "sample_count": sample_count,
        "passed": passed,
        "reason": "threshold_met" if passed else ("threshold_not_met" if available else "metric_unavailable"),
    }


def _gate_decisions(
    quality: dict[str, Any],
    records: list[dict[str, Any]],
    judge: dict[str, Any],
    gates: dict[str, Any],
    *,
    run_state: str,
    run_status: str,
) -> dict[str, Any]:
    run_completed = run_state == "completed"
    expected_run_status = "PASS" if all(
        record["deterministic"]["passed"] for record in records
    ) else "FAIL"
    run_status_consistent = not run_completed or run_status == expected_run_status
    decisions = [
        {
            "name": "run_completed",
            "required": True,
            "available": True,
            "status": "passed" if run_completed else "failed",
            "threshold": None,
            "actual": f"{run_state}/{run_status}",
            "sample_count": len(records),
            "passed": run_completed,
            "reason": "run_completed" if run_completed else "run_failed",
        },
        {
            "name": "run_status_consistent",
            "required": run_completed,
            "available": run_completed,
            "status": "passed" if run_status_consistent else "failed",
            "threshold": None,
            "actual": f"reported={run_status},deterministic={expected_run_status}",
            "sample_count": len(records),
            "passed": run_status_consistent if run_completed else None,
            "reason": "status_consistent" if run_status_consistent else "status_conflict",
        },
        _quality_gate(
            quality,
            records,
            name="trigger_threshold",
            mode="trigger",
            threshold=float(gates["trigger_threshold"]),
        ),
        _quality_gate(
            quality,
            records,
            name="required_case_pass_rate",
            mode="behavior",
            threshold=float(gates["required_case_pass_rate"]),
        ),
    ]
    judge_required = bool(gates["judge_required"])
    judge_available = judge.get("status") not in {None, "disabled", "invalid"}
    judge_passed = judge.get("authority") == "decision" and judge.get("status") == "candidate"
    if not judge_required:
        judge_reason = "judge_not_required"
        judge_status = "not_required"
        judge_result: bool | None = None
    elif judge_passed:
        judge_reason = "calibrated_candidate_decision"
        judge_status = "passed"
        judge_result = True
    elif not judge_available:
        judge_reason = "judge_evidence_unavailable"
        judge_status = "failed"
        judge_result = False
    else:
        judge_reason = "judge_not_candidate_decision"
        judge_status = "failed"
        judge_result = False
    decisions.append(
        {
            "name": "judge_required",
            "required": judge_required,
            "available": judge_available,
            "status": judge_status,
            "threshold": None,
            "actual": {"status": judge.get("status"), "authority": judge.get("authority")},
            "sample_count": None,
            "passed": judge_result,
            "reason": judge_reason,
        }
    )
    required = [decision for decision in decisions if decision["required"]]
    return {
        "all_required_passed": all(decision["passed"] is True for decision in required),
        "all_required_available": all(decision["available"] for decision in required),
        "required_gate_count": len(required),
        "decisions": decisions,
    }


def _validated_gates(value: Any) -> dict[str, Any]:
    fields = {"trigger_threshold", "required_case_pass_rate", "judge_required"}
    if not isinstance(value, dict) or set(value) != fields:
        raise SuiteError("grade 文档缺少闭合 gates", path="$.gates")
    for field in ("trigger_threshold", "required_case_pass_rate"):
        threshold = value[field]
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not 0 <= threshold <= 1:
            raise SuiteError("gate threshold 必须在 0 到 1", path=f"$.gates.{field}")
    if not isinstance(value["judge_required"], bool):
        raise SuiteError("judge_required 必须是 boolean", path="$.gates.judge_required")
    return dict(value)


def build_report(graded: dict[str, Any]) -> dict[str, Any]:
    graded = validate_grade_document(graded)
    records = graded.get("records")
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise SuiteError("grade 文档缺少 records", path="$.records")
    if len(records) > MAX_REPORT_RECORDS:
        raise SuiteError(f"grade records 不能超过 {MAX_REPORT_RECORDS} 项", path="$.records")
    quality = quality_metrics(records)
    trigger = trigger_metrics(records)
    paired = paired_delta_metrics(records)
    cost = cost_metrics(records)
    humans = Counter(
        item["human_feedback"]["label"]
        for item in records
        if isinstance(item.get("human_feedback"), dict) and item["human_feedback"].get("label")
    )
    small_sample = not quality or any(item["n"] < 5 for item in quality.values())
    judge = graded.get("judge") if isinstance(graded.get("judge"), dict) else {"status": "invalid"}
    gates = _validated_gates(graded.get("gates"))
    expected_run_status = "PASS" if all(
        record["deterministic"]["passed"] for record in records
    ) else "FAIL"
    run_status_consistent = (
        graded["run_state"] != "completed" or graded["run_status"] == expected_run_status
    )
    gate_decisions = _gate_decisions(
        quality,
        records,
        judge,
        gates,
        run_state=graded["run_state"],
        run_status=graded["run_status"],
    )
    return {
        "schema_version": 1,
        "suite_id": graded.get("suite_id"),
        "run_id": graded.get("run_id"),
        "fingerprint": graded.get("fingerprint"),
        "run": {
            "state": graded["run_state"],
            "status": graded["run_status"],
            "error": graded["run_error"],
        },
        "quality": quality,
        "trigger": trigger,
        "case_results": _case_results(records),
        "paired_delta": paired,
        "cost": cost,
        "failure_taxonomy": failure_taxonomy(records),
        "human_feedback": {"n": sum(humans.values()), "labels": dict(sorted(humans.items()))},
        "judge": judge,
        "gates": dict(gates),
        "gate_decisions": gate_decisions,
        "uncertainty": {
            "small_sample": small_sample,
            "paired_low_information": paired["low_information"],
            "duration_available": cost["duration_seconds"]["available"],
            "token_usage_complete": all(
                item["complete"] for item in cost["token_availability"].values()
            ),
            "judge_advisory_only": judge.get("authority") != "decision",
            "gate_evidence_complete": gate_decisions["all_required_available"],
            "run_completed": graded["run_state"] == "completed",
            "run_status_consistent": run_status_consistent,
        },
        "provenance": {
            "fingerprint": graded.get("fingerprint"),
            "source_identity": graded.get("source_identity", {}),
            "lab_identity": graded.get("lab_identity", {}),
            "grader_identity": graded.get("grader_identity", {}),
            "record_count": len(records),
            "execution_groups": _provenance_groups(records),
        },
    }


def _number(value: Any, *, digits: int = 3) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    """渲染紧凑报告，不折叠样本量、区间或失败。"""
    lines = [
        "# Skill Evaluation Report",
        "",
        f"- Suite: `{report.get('suite_id')}`",
        f"- Run: `{report.get('run_id')}`",
        f"- Fingerprint: `{report.get('fingerprint')}`",
        f"- Run state: `{report['run']['state']}/{report['run']['status']}`",
        "",
        "## Quality",
        "",
        "| Variant | n | Passed | Pass rate | Wilson 95% interval |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    run_error = report["run"].get("error")
    if isinstance(run_error, dict):
        lines.insert(6, f"- Run error: `{run_error.get('code')}` {run_error.get('message')}")
    for variant, value in sorted(report["quality"].items()):
        interval = value["wilson_interval"]
        interval_text = f"{_number(interval['low'])} to {_number(interval['high'])}"
        lines.append(
            f"| {variant} | {value['n']} | {value['passed']} | {_number(value['pass_rate'])} | {interval_text} |"
        )
    lines.extend(
        [
            "",
            "### Quality By Mode",
            "",
            "| Variant | Mode | n | Passed | Pass rate | Wilson 95% interval |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for variant, value in sorted(report["quality"].items()):
        for mode, mode_value in sorted(value["by_mode"].items()):
            interval = mode_value["wilson_interval"]
            interval_text = f"{_number(interval['low'])} to {_number(interval['high'])}"
            lines.append(
                f"| {variant} | {mode} | {mode_value['n']} | {mode_value['passed']} | "
                f"{_number(mode_value['pass_rate'])} | {interval_text} |"
            )
    trigger = report["trigger"]
    confusion = trigger["confusion_matrix"]
    lines.extend(
        [
            "",
            "## Trigger",
            "",
            f"- Records: {trigger['valid_n']} valid, {trigger['invalid_n']} invalid",
            f"- Activation rate: {_number(trigger['activation_rate'])}",
            f"- Confusion: TP {confusion['true_positive']}, FP {confusion['false_positive']}, "
            f"TN {confusion['true_negative']}, FN {confusion['false_negative']}",
            "",
            "## Case Results",
            "",
            "| Record | Mode | Variant | Status | Failure | Duration seconds |",
            "| --- | --- | --- | --- | --- | ---: |",
        ]
    )
    for item in report["case_results"]:
        lines.append(
            f"| {item['record_key']} | {item['mode']} | {item['variant']} | {item['status']} | "
            f"{item['failure_type'] or 'none'} | {_number(item['duration_seconds'])} |"
        )
    paired = report["paired_delta"]
    lines.extend(
        [
            "",
            "## Paired Delta",
            "",
            f"- Pairs: {paired['n_pairs']} (wins {paired['wins']}, losses {paired['losses']}, ties {paired['ties']})",
            f"- Mean delta: {_number(paired['delta']['mean'])}",
            f"- Low information: `{str(paired['low_information']).lower()}`",
            f"- Excluded incompatible pairs: {len(paired['excluded_pairs'])}",
            "",
            "## Cost",
            "",
        ]
    )
    for name, value in sorted(report["cost"]["tokens"].items()):
        availability = report["cost"]["token_availability"][name]
        lines.append(
            f"- {name}: {value} (samples {availability['sample_count']}, "
            f"complete `{str(availability['complete']).lower()}`)"
        )
    duration = report["cost"]["duration_seconds"]
    lines.append(f"- Duration samples: {duration['count']}; mean seconds: {_number(duration['mean'])}")
    lines.extend(["", "## Failures", ""])
    if report["failure_taxonomy"]:
        for name, count in sorted(report["failure_taxonomy"].items()):
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- None")
    human = report["human_feedback"]
    lines.extend(["", "## Human Feedback", "", f"- Samples: {human['n']}"])
    if human["labels"]:
        for name, count in sorted(human["labels"].items()):
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- Labels: unavailable")
    judge = report["judge"]
    lines.extend(
        [
            "",
            "## Judge",
            "",
            f"- Status: `{judge.get('status')}`",
            f"- Authority: `{judge.get('authority')}`",
            "",
            "## Gate Decisions",
            "",
            "| Gate | Required | Available | Status | Threshold | Actual | n | Reason |",
            "| --- | --- | --- | --- | ---: | --- | ---: | --- |",
        ]
    )
    for decision in report["gate_decisions"]["decisions"]:
        actual = decision["actual"]
        if isinstance(actual, dict):
            actual_text = f"{actual.get('status')}/{actual.get('authority')}"
        else:
            actual_text = _number(actual)
        lines.append(
            f"| {decision['name']} | {str(decision['required']).lower()} | "
            f"{str(decision['available']).lower()} | {decision['status']} | "
            f"{_number(decision['threshold'])} | {actual_text} | "
            f"{_number(decision['sample_count'])} | {decision['reason']} |"
        )
    lines.extend(
        [
            "",
            f"- All required gates passed: `{str(report['gate_decisions']['all_required_passed']).lower()}`",
            f"- All required evidence available: `{str(report['gate_decisions']['all_required_available']).lower()}`",
            "",
            "## Uncertainty",
            "",
        ]
    )
    for name, value in sorted(report["uncertainty"].items()):
        lines.append(f"- {name}: `{str(value).lower()}`")
    lines.extend(["", "## Provenance", ""])
    lines.append(
        f"- Lab tree: `{report['provenance']['lab_identity'].get('tree_sha256')}`; "
        f"grader tree: `{report['provenance']['grader_identity'].get('tree_sha256')}`"
    )
    for group in report["provenance"]["execution_groups"]:
        lines.append(
            f"- {group['record_count']} record(s): adapter `{group['adapter']}`, CLI `{group['cli_version']}`, "
            f"model `{group['model']}`, sandbox `{group['sandbox']}`, network `{group['network_access']}`, "
            f"permission profile `{group['permission_profile']}`"
        )
    return "\n".join(lines) + "\n"
