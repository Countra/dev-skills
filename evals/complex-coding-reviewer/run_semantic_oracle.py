#!/usr/bin/env python3
"""对人工裁定后的 Reviewer 语义观察结果执行确定性评分。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SEVERITIES = {"blocking", "major", "minor", "advisory"}
PROFILES = {"plan-review", "code-review"}
CATEGORIES = {"clean", "near-miss", "known-defect"}


@dataclass(frozen=True)
class OracleError(Exception):
    """表示 observation 输入无法被确定性评分。"""

    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OracleError("ORACLE_INVALID_TYPE", f"{path} 必须是 object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise OracleError("ORACLE_INVALID_TYPE", f"{path} 必须是 array")
    return value


def require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OracleError("ORACLE_INVALID_VALUE", f"{path} 必须是非空字符串")
    return value


def closed_fields(value: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(allowed - set(value))
    if unknown or missing:
        detail = []
        if unknown:
            detail.append(f"未知字段 {unknown}")
        if missing:
            detail.append(f"缺少字段 {missing}")
        raise OracleError("ORACLE_FIELDS_INVALID", f"{path}: {'；'.join(detail)}")


def unique_strings(value: Any, path: str) -> list[str]:
    values = [require_string(item, f"{path}[]") for item in require_list(value, path)]
    if len(values) != len(set(values)):
        raise OracleError("ORACLE_DUPLICATE_ID", f"{path} 包含重复值")
    return values


def validate_expectations(value: Any, path: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(require_list(value, path)):
        item_path = f"{path}[{index}]"
        item = require_object(raw, item_path)
        closed_fields(item, {"id", "severity", "locator_required"}, item_path)
        item_id = require_string(item["id"], f"{item_path}.id")
        if item_id in result:
            raise OracleError("ORACLE_DUPLICATE_ID", f"{item_path}.id 重复")
        if item["severity"] not in SEVERITIES:
            raise OracleError("ORACLE_INVALID_VALUE", f"{item_path}.severity 无效")
        if not isinstance(item["locator_required"], bool):
            raise OracleError("ORACLE_INVALID_TYPE", f"{item_path}.locator_required 必须是 boolean")
        result[item_id] = item
    return result


def validate_matches(value: Any, path: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(require_list(value, path)):
        item_path = f"{path}[{index}]"
        item = require_object(raw, item_path)
        closed_fields(item, {"expectation_id", "severity", "locator_present"}, item_path)
        expectation_id = require_string(item["expectation_id"], f"{item_path}.expectation_id")
        if expectation_id in result:
            raise OracleError("ORACLE_DUPLICATE_ID", f"{item_path}.expectation_id 重复")
        if item["severity"] not in SEVERITIES:
            raise OracleError("ORACLE_INVALID_VALUE", f"{item_path}.severity 无效")
        if not isinstance(item["locator_present"], bool):
            raise OracleError("ORACLE_INVALID_TYPE", f"{item_path}.locator_present 必须是 boolean")
        result[expectation_id] = item
    return result


def ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else round(numerator / denominator, 6)


def score_case(raw: Any, index: int) -> dict[str, Any]:
    path = f"$.cases[{index}]"
    case = require_object(raw, path)
    closed_fields(
        case,
        {
            "id",
            "profile",
            "category",
            "expected_findings",
            "forbidden_finding_ids",
            "expected_gap_ids",
            "actual",
        },
        path,
    )
    case_id = require_string(case["id"], f"{path}.id")
    if case["profile"] not in PROFILES:
        raise OracleError("ORACLE_INVALID_VALUE", f"{path}.profile 无效")
    if case["category"] not in CATEGORIES:
        raise OracleError("ORACLE_INVALID_VALUE", f"{path}.category 无效")

    expectations = validate_expectations(case["expected_findings"], f"{path}.expected_findings")
    forbidden = set(unique_strings(case["forbidden_finding_ids"], f"{path}.forbidden_finding_ids"))
    expected_gaps = set(unique_strings(case["expected_gap_ids"], f"{path}.expected_gap_ids"))
    actual = require_object(case["actual"], f"{path}.actual")
    closed_fields(
        actual,
        {"matched_findings", "unmatched_finding_ids", "triggered_forbidden_ids", "gap_ids"},
        f"{path}.actual",
    )
    matches = validate_matches(actual["matched_findings"], f"{path}.actual.matched_findings")
    unmatched = set(unique_strings(actual["unmatched_finding_ids"], f"{path}.actual.unmatched_finding_ids"))
    triggered_forbidden = set(
        unique_strings(actual["triggered_forbidden_ids"], f"{path}.actual.triggered_forbidden_ids")
    )
    actual_gaps = set(unique_strings(actual["gap_ids"], f"{path}.actual.gap_ids"))

    unknown_matches = sorted(set(matches) - set(expectations))
    unknown_forbidden = sorted(triggered_forbidden - forbidden)
    if unknown_matches or unknown_forbidden:
        raise OracleError(
            "ORACLE_REFERENCE_UNKNOWN",
            f"{path} 引用了未知 expectation/forbidden ID: {unknown_matches + unknown_forbidden}",
        )

    matched_ids = set(matches)
    missed_ids = sorted(set(expectations) - matched_ids)
    severity_mismatches = sorted(
        expectation_id
        for expectation_id in matched_ids
        if matches[expectation_id]["severity"] != expectations[expectation_id]["severity"]
    )
    missing_locators = sorted(
        expectation_id
        for expectation_id in matched_ids
        if expectations[expectation_id]["locator_required"]
        and not matches[expectation_id]["locator_present"]
    )
    locator_required_ids = {
        expectation_id
        for expectation_id, expectation in expectations.items()
        if expectation["locator_required"]
    }
    located_required_ids = {
        expectation_id
        for expectation_id in locator_required_ids & matched_ids
        if matches[expectation_id]["locator_present"]
    }
    missing_gaps = sorted(expected_gaps - actual_gaps)
    unexpected_gaps = sorted(actual_gaps - expected_gaps)
    false_positive_ids = sorted(unmatched | triggered_forbidden)
    passed = not any(
        (missed_ids, severity_mismatches, missing_locators, missing_gaps, unexpected_gaps, false_positive_ids)
    )
    return {
        "id": case_id,
        "profile": case["profile"],
        "category": case["category"],
        "passed": passed,
        "expected_count": len(expectations),
        "matched_count": len(matched_ids),
        "locator_required_count": len(locator_required_ids),
        "locator_present_count": len(located_required_ids),
        "missed_ids": missed_ids,
        "severity_mismatch_ids": severity_mismatches,
        "missing_locator_ids": missing_locators,
        "false_positive_ids": false_positive_ids,
        "missing_gap_ids": missing_gaps,
        "unexpected_gap_ids": unexpected_gaps,
    }


def score_suite(value: Any) -> dict[str, Any]:
    root = require_object(value, "$")
    closed_fields(root, {"suite", "provenance", "cases"}, "$")
    suite = require_string(root["suite"], "$.suite")
    provenance = require_object(root["provenance"], "$.provenance")
    closed_fields(provenance, {"mode", "agent_calls", "network_calls", "target_executions"}, "$.provenance")
    mode = require_string(provenance["mode"], "$.provenance.mode")
    for field in ("agent_calls", "network_calls", "target_executions"):
        if not isinstance(provenance[field], int) or isinstance(provenance[field], bool) or provenance[field] < 0:
            raise OracleError("ORACLE_INVALID_VALUE", f"$.provenance.{field} 必须是非负整数")

    cases = require_list(root["cases"], "$.cases")
    if not cases:
        raise OracleError("ORACLE_EMPTY_SUITE", "$.cases 至少需要一个语义观察 case")
    results = [score_case(item, index) for index, item in enumerate(cases)]
    case_ids = [item["id"] for item in results]
    if len(case_ids) != len(set(case_ids)):
        raise OracleError("ORACLE_DUPLICATE_ID", "$.cases 包含重复 case ID")
    expected = sum(item["expected_count"] for item in results)
    matched = sum(item["matched_count"] for item in results)
    false_positives = sum(len(item["false_positive_ids"]) for item in results)
    severity_total = matched
    severity_exact = severity_total - sum(len(item["severity_mismatch_ids"]) for item in results)
    locator_required = sum(item["locator_required_count"] for item in results)
    locator_present = sum(item["locator_present_count"] for item in results)
    return {
        "suite": suite,
        "passed": all(item["passed"] for item in results),
        "case_total": len(results),
        "case_passed": sum(item["passed"] for item in results),
        "metrics": {
            "finding_recall": ratio(matched, expected),
            "false_positive_count": false_positives,
            "severity_exact_rate": ratio(severity_exact, severity_total),
            "locator_present_rate": ratio(locator_present, locator_required),
            "gap_honesty_failures": sum(
                len(item["missing_gap_ids"]) + len(item["unexpected_gap_ids"])
                for item in results
            ),
        },
        "claim_boundaries": {
            "semantic_matching_source": "human-adjudicated expectation IDs",
            "semantic_quality_observed": mode in {"same-context", "fresh-context", "external-agent", "human"},
            "provenance_mode": mode,
            "agent_calls": provenance["agent_calls"],
            "network_calls": provenance["network_calls"],
            "target_executions": provenance["target_executions"],
        },
        "results": results,
    }


def self_test_payload(*, false_positive: bool = False) -> dict[str, Any]:
    return {
        "suite": "semantic-oracle-self-test",
        "provenance": {
            "mode": "deterministic-fixture",
            "agent_calls": 0,
            "network_calls": 0,
            "target_executions": 0,
        },
        "cases": [
            {
                "id": "known-defect",
                "profile": "code-review",
                "category": "known-defect",
                "expected_findings": [
                    {"id": "EXP-01", "severity": "major", "locator_required": True}
                ],
                "forbidden_finding_ids": [],
                "expected_gap_ids": [],
                "actual": {
                    "matched_findings": [
                        {"expectation_id": "EXP-01", "severity": "major", "locator_present": True}
                    ],
                    "unmatched_finding_ids": [],
                    "triggered_forbidden_ids": [],
                    "gap_ids": [],
                },
            },
            {
                "id": "near-miss",
                "profile": "plan-review",
                "category": "near-miss",
                "expected_findings": [],
                "forbidden_finding_ids": ["PREFERENCE-AS-MAJOR"],
                "expected_gap_ids": ["GAP-HOSTED-CI"],
                "actual": {
                    "matched_findings": [],
                    "unmatched_finding_ids": ["UNEXPECTED"] if false_positive else [],
                    "triggered_forbidden_ids": [],
                    "gap_ids": ["GAP-HOSTED-CI"],
                },
            },
        ],
    }


def run_self_test() -> dict[str, Any]:
    positive = score_suite(self_test_payload())
    negative = score_suite(self_test_payload(false_positive=True))
    checks = {
        "accepts_expected_matches": positive["passed"] is True,
        "rejects_false_positive": negative["passed"] is False,
        "reports_zero_execution": positive["claim_boundaries"]["target_executions"] == 0,
    }
    return {
        "suite": "semantic-oracle-self-test",
        "passed": all(checks.values()),
        "checks": checks,
        "positive": positive,
        "negative": negative,
    }


def render(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="确定性评分 Reviewer 语义 observation")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="人工裁定后的 observation JSON")
    source.add_argument("--self-test", action="store_true", help="运行内置正负自测")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = run_self_test() if args.self_test else score_suite(
            json.loads(args.input.read_text(encoding="utf-8"))
        )
    except (OSError, UnicodeError, json.JSONDecodeError, OracleError) as exc:
        error = {
            "suite": "semantic-oracle",
            "passed": False,
            "error": {
                "code": exc.code if isinstance(exc, OracleError) else "ORACLE_INPUT_UNREADABLE",
                "message": str(exc),
            },
        }
        print(render(error), end="")
        return 2
    output = render(report)
    print(output, end="")
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            print(f"无法写入 oracle output：{exc}", file=sys.stderr)
            return 2
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
