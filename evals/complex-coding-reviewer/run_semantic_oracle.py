#!/usr/bin/env python3
"""对人工裁定后的 Reviewer 语义观察结果执行确定性评分。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SEVERITIES = {"blocking", "major", "minor", "advisory"}
PROFILES = {"plan-review", "code-review"}
CATEGORIES = {"clean", "near-miss", "known-defect"}
PROVENANCE_MODES = {
    "deterministic-fixture",
    "same-context",
    "fresh-context",
    "external-agent",
    "human",
}
OBSERVED_MODES = PROVENANCE_MODES - {"deterministic-fixture"}
REQUIRED_CORPUS_TAGS = {
    "missing",
    "extra",
    "misunderstood",
    "risk-trigger",
    "stale-context",
    "lineage",
    "framing-bias",
    "prompt-injection",
    "parent-contamination",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CORPUS_PATH = Path(__file__).with_name("semantic_cases") / "corpus.json"
REPO_ROOT = Path(__file__).resolve().parents[2]


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
    if not isinstance(value, str):
        raise OracleError("ORACLE_INVALID_TYPE", f"{path} 必须是 string")
    if not value.strip():
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


def require_boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise OracleError("ORACLE_INVALID_TYPE", f"{path} 必须是 boolean")
    return value


def require_sha256(value: Any, path: str) -> str:
    digest = require_string(value, path)
    if not SHA256_PATTERN.fullmatch(digest):
        raise OracleError("ORACLE_INVALID_VALUE", f"{path} 必须是小写 SHA-256")
    return digest


def validate_expectations(value: Any, path: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(require_list(value, path)):
        item_path = f"{path}[{index}]"
        item = dict(require_object(raw, item_path))
        closed_fields(
            item,
            {"id", "severity", "locator_required", "evidence_required"},
            item_path,
        )
        item_id = require_string(item["id"], f"{item_path}.id")
        if item_id in result:
            raise OracleError("ORACLE_DUPLICATE_ID", f"{item_path}.id 重复")
        severity = require_string(item["severity"], f"{item_path}.severity")
        if severity not in SEVERITIES:
            raise OracleError("ORACLE_INVALID_VALUE", f"{item_path}.severity 无效")
        item["severity"] = severity
        require_boolean(item["locator_required"], f"{item_path}.locator_required")
        require_boolean(item["evidence_required"], f"{item_path}.evidence_required")
        result[item_id] = item
    return result


def validate_matches(value: Any, path: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(require_list(value, path)):
        item_path = f"{path}[{index}]"
        item = dict(require_object(raw, item_path))
        closed_fields(
            item,
            {"expectation_id", "severity", "locator_present", "evidence_refs"},
            item_path,
        )
        expectation_id = require_string(item["expectation_id"], f"{item_path}.expectation_id")
        if expectation_id in result:
            raise OracleError("ORACLE_DUPLICATE_ID", f"{item_path}.expectation_id 重复")
        severity = require_string(item["severity"], f"{item_path}.severity")
        if severity not in SEVERITIES:
            raise OracleError("ORACLE_INVALID_VALUE", f"{item_path}.severity 无效")
        item["severity"] = severity
        require_boolean(item["locator_present"], f"{item_path}.locator_present")
        item["evidence_refs"] = unique_strings(item["evidence_refs"], f"{item_path}.evidence_refs")
        result[expectation_id] = item
    return result


def validate_receipts(value: Any, path: str) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    for index, raw in enumerate(require_list(value, path)):
        item_path = f"{path}[{index}]"
        item = dict(require_object(raw, item_path))
        closed_fields(item, {"profile", "review_id", "path", "sha256"}, item_path)
        profile = require_string(item["profile"], f"{item_path}.profile")
        if profile not in PROFILES:
            raise OracleError("ORACLE_INVALID_VALUE", f"{item_path}.profile 无效")
        item["profile"] = profile
        review_id = require_string(item["review_id"], f"{item_path}.review_id")
        receipt_path = require_string(item["path"], f"{item_path}.path")
        if Path(receipt_path).is_absolute() or ".." in Path(receipt_path).parts:
            raise OracleError("ORACLE_INVALID_VALUE", f"{item_path}.path 必须是安全相对路径")
        require_sha256(item["sha256"], f"{item_path}.sha256")
        identity = (item["profile"], review_id)
        if identity in identities:
            raise OracleError("ORACLE_DUPLICATE_ID", f"{item_path} receipt identity 重复")
        identities.add(identity)
        receipts.append(item)
    return receipts


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
    profile = require_string(case["profile"], f"{path}.profile")
    category = require_string(case["category"], f"{path}.category")
    if profile not in PROFILES:
        raise OracleError("ORACLE_INVALID_VALUE", f"{path}.profile 无效")
    if category not in CATEGORIES:
        raise OracleError("ORACLE_INVALID_VALUE", f"{path}.category 无效")

    expectations = validate_expectations(case["expected_findings"], f"{path}.expected_findings")
    forbidden = set(unique_strings(case["forbidden_finding_ids"], f"{path}.forbidden_finding_ids"))
    if set(expectations) & forbidden:
        raise OracleError(
            "ORACLE_EXPECTATION_CONFLICT",
            f"{path} finding 不能同时是 expected 与 forbidden",
        )
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
    missing_evidence = sorted(
        expectation_id
        for expectation_id in matched_ids
        if expectations[expectation_id]["evidence_required"]
        and not matches[expectation_id]["evidence_refs"]
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
    evidence_required_ids = {
        expectation_id
        for expectation_id, expectation in expectations.items()
        if expectation["evidence_required"]
    }
    evidenced_required_ids = {
        expectation_id
        for expectation_id in evidence_required_ids & matched_ids
        if matches[expectation_id]["evidence_refs"]
    }
    missing_gaps = sorted(expected_gaps - actual_gaps)
    unexpected_gaps = sorted(actual_gaps - expected_gaps)
    false_positive_ids = sorted(unmatched | triggered_forbidden)
    passed = not any(
        (
            missed_ids,
            severity_mismatches,
            missing_locators,
            missing_evidence,
            missing_gaps,
            unexpected_gaps,
            false_positive_ids,
        )
    )
    return {
        "id": case_id,
        "profile": profile,
        "category": category,
        "passed": passed,
        "expected_count": len(expectations),
        "matched_count": len(matched_ids),
        "locator_required_count": len(locator_required_ids),
        "locator_present_count": len(located_required_ids),
        "evidence_required_count": len(evidence_required_ids),
        "evidence_present_count": len(evidenced_required_ids),
        "missed_ids": missed_ids,
        "severity_mismatch_ids": severity_mismatches,
        "missing_locator_ids": missing_locators,
        "missing_evidence_ids": missing_evidence,
        "false_positive_ids": false_positive_ids,
        "missing_gap_ids": missing_gaps,
        "unexpected_gap_ids": unexpected_gaps,
    }


def score_suite(value: Any) -> dict[str, Any]:
    root = require_object(value, "$")
    closed_fields(root, {"suite", "provenance", "cases"}, "$")
    suite = require_string(root["suite"], "$.suite")
    provenance = require_object(root["provenance"], "$.provenance")
    closed_fields(
        provenance,
        {
            "mode",
            "declared_by",
            "independence_claim",
            "agent_calls",
            "network_calls",
            "target_executions",
            "reviewer_receipts",
        },
        "$.provenance",
    )
    mode = require_string(provenance["mode"], "$.provenance.mode")
    if mode not in PROVENANCE_MODES:
        raise OracleError("ORACLE_INVALID_VALUE", "$.provenance.mode 无效")
    declared_by = require_string(provenance["declared_by"], "$.provenance.declared_by")
    independence_claim = require_boolean(
        provenance["independence_claim"],
        "$.provenance.independence_claim",
    )
    for field in ("agent_calls", "network_calls", "target_executions"):
        if not isinstance(provenance[field], int) or isinstance(provenance[field], bool) or provenance[field] < 0:
            raise OracleError("ORACLE_INVALID_VALUE", f"$.provenance.{field} 必须是非负整数")

    receipts = validate_receipts(provenance["reviewer_receipts"], "$.provenance.reviewer_receipts")
    if mode == "deterministic-fixture":
        if independence_claim or receipts or declared_by != "deterministic-harness":
            raise OracleError(
                "ORACLE_PROVENANCE_INVALID",
                "deterministic fixture 必须由 deterministic-harness 声明且不得附带独立性或 receipt",
            )
    elif mode == "same-context" and independence_claim:
        raise OracleError(
            "ORACLE_PROVENANCE_INVALID",
            "same-context 不得声明 reviewer independence",
        )
    elif mode in {"fresh-context", "external-agent"} and not independence_claim:
        raise OracleError(
            "ORACLE_PROVENANCE_INVALID",
            f"{mode} 必须显式声明独立性",
        )

    cases = require_list(root["cases"], "$.cases")
    if not cases:
        raise OracleError("ORACLE_EMPTY_SUITE", "$.cases 至少需要一个语义观察 case")
    results = [score_case(item, index) for index, item in enumerate(cases)]
    case_ids = [item["id"] for item in results]
    if len(case_ids) != len(set(case_ids)):
        raise OracleError("ORACLE_DUPLICATE_ID", "$.cases 包含重复 case ID")
    if mode in OBSERVED_MODES:
        reviewed_profiles = {item["profile"] for item in receipts}
        missing_profiles = sorted({item["profile"] for item in results} - reviewed_profiles)
        if missing_profiles:
            raise OracleError(
                "ORACLE_PROVENANCE_INCOMPLETE",
                f"observed suite 缺少 profile receipt: {missing_profiles}",
            )
        receipt_paths = {
            profile: {item["path"] for item in receipts if item["profile"] == profile}
            for profile in PROFILES
        }
        for index, raw_case in enumerate(cases):
            case = require_object(raw_case, f"$.cases[{index}]")
            actual = require_object(case["actual"], f"$.cases[{index}].actual")
            matches = validate_matches(
                actual["matched_findings"],
                f"$.cases[{index}].actual.matched_findings",
            )
            for expectation_id, match in matches.items():
                for reference in match["evidence_refs"]:
                    receipt_path = reference.split("#", 1)[0]
                    if receipt_path not in receipt_paths[case["profile"]]:
                        raise OracleError(
                            "ORACLE_PROVENANCE_INCOMPLETE",
                            f"case {case['id']} expectation {expectation_id} evidence 未绑定对应 profile receipt",
                        )
    expected = sum(item["expected_count"] for item in results)
    matched = sum(item["matched_count"] for item in results)
    false_positives = sum(len(item["false_positive_ids"]) for item in results)
    severity_total = matched
    severity_exact = severity_total - sum(len(item["severity_mismatch_ids"]) for item in results)
    locator_required = sum(item["locator_required_count"] for item in results)
    locator_present = sum(item["locator_present_count"] for item in results)
    evidence_required = sum(item["evidence_required_count"] for item in results)
    evidence_present = sum(item["evidence_present_count"] for item in results)
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
            "evidence_present_rate": ratio(evidence_present, evidence_required),
            "gap_honesty_failures": sum(
                len(item["missing_gap_ids"]) + len(item["unexpected_gap_ids"])
                for item in results
            ),
        },
        "claim_boundaries": {
            "semantic_matching_source": "human-adjudicated expectation IDs",
            "semantic_quality_observed": mode in OBSERVED_MODES,
            "provenance_mode": mode,
            "declared_by": declared_by,
            "independence_claim": independence_claim,
            "reviewer_receipt_count": len(receipts),
            "reviewer_receipts_verified": (
                "not-applicable" if mode == "deterministic-fixture" else "not-performed"
            ),
            "agent_calls": provenance["agent_calls"],
            "network_calls": provenance["network_calls"],
            "target_executions": provenance["target_executions"],
        },
        "results": results,
    }


def load_corpus(path: Path = CORPUS_PATH) -> tuple[dict[str, Any], dict[str, Any]]:
    root = require_object(json.loads(path.read_text(encoding="utf-8")), "$corpus")
    closed_fields(root, {"schema_version", "suite", "required_tags", "cases"}, "$corpus")
    if root["schema_version"] != 1:
        raise OracleError("ORACLE_CORPUS_INVALID", "$corpus.schema_version 必须为 1")
    suite = require_string(root["suite"], "$corpus.suite")
    required_tags = set(unique_strings(root["required_tags"], "$corpus.required_tags"))
    if required_tags != REQUIRED_CORPUS_TAGS:
        raise OracleError(
            "ORACLE_CORPUS_INVALID",
            f"$corpus.required_tags 必须精确覆盖 {sorted(REQUIRED_CORPUS_TAGS)}",
        )

    cases = require_list(root["cases"], "$corpus.cases")
    if not cases:
        raise OracleError("ORACLE_CORPUS_INVALID", "$corpus.cases 不得为空")
    case_ids: set[str] = set()
    target_paths: set[str] = set()
    observed_tags: set[str] = set()
    profile_categories = {profile: set() for profile in PROFILES}
    file_evidence: list[dict[str, Any]] = []
    for index, raw in enumerate(cases):
        case_path = f"$corpus.cases[{index}]"
        case = require_object(raw, case_path)
        closed_fields(
            case,
            {
                "id",
                "profile",
                "category",
                "target_path",
                "tags",
                "expected_findings",
                "forbidden_finding_ids",
                "expected_gap_ids",
            },
            case_path,
        )
        case_id = require_string(case["id"], f"{case_path}.id")
        if case_id in case_ids:
            raise OracleError("ORACLE_DUPLICATE_ID", f"{case_path}.id 重复")
        case_ids.add(case_id)
        profile = require_string(case["profile"], f"{case_path}.profile")
        category = require_string(case["category"], f"{case_path}.category")
        if profile not in PROFILES or category not in CATEGORIES:
            raise OracleError("ORACLE_CORPUS_INVALID", f"{case_path} profile/category 无效")
        profile_categories[profile].add(category)
        target_path = require_string(case["target_path"], f"{case_path}.target_path")
        relative = Path(target_path)
        if relative.is_absolute() or ".." in relative.parts or target_path in target_paths:
            raise OracleError("ORACLE_CORPUS_INVALID", f"{case_path}.target_path 无效或重复")
        target_paths.add(target_path)
        target = path.parent / relative
        if not target.is_file():
            raise OracleError("ORACLE_CORPUS_INVALID", f"{case_path}.target_path 不存在")
        tags = set(unique_strings(case["tags"], f"{case_path}.tags"))
        observed_tags.update(tags)
        expectations = validate_expectations(case["expected_findings"], f"{case_path}.expected_findings")
        forbidden = set(unique_strings(case["forbidden_finding_ids"], f"{case_path}.forbidden_finding_ids"))
        unique_strings(case["expected_gap_ids"], f"{case_path}.expected_gap_ids")
        if set(expectations) & forbidden:
            raise OracleError("ORACLE_CORPUS_INVALID", f"{case_path} expectation 与 forbidden ID 重叠")
        content = target.read_bytes()
        file_evidence.append(
            {
                "case_id": case_id,
                "path": target_path,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )

    missing_tags = sorted(required_tags - observed_tags)
    incomplete_profiles = {
        profile: sorted(CATEGORIES - categories)
        for profile, categories in profile_categories.items()
        if categories != CATEGORIES
    }
    if missing_tags or incomplete_profiles:
        raise OracleError(
            "ORACLE_CORPUS_INCOMPLETE",
            f"missing_tags={missing_tags}; missing_profile_categories={incomplete_profiles}",
        )
    return root, {
        "suite": suite,
        "case_total": len(cases),
        "profile_case_counts": {
            profile: sum(case["profile"] == profile for case in cases)
            for profile in sorted(PROFILES)
        },
        "categories_by_profile": {
            profile: sorted(categories)
            for profile, categories in sorted(profile_categories.items())
        },
        "required_tags": sorted(required_tags),
        "files": file_evidence,
    }


def perfect_payload(corpus: dict[str, Any]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for raw in corpus["cases"]:
        expectations = deepcopy(raw["expected_findings"])
        cases.append(
            {
                "id": raw["id"],
                "profile": raw["profile"],
                "category": raw["category"],
                "expected_findings": expectations,
                "forbidden_finding_ids": list(raw["forbidden_finding_ids"]),
                "expected_gap_ids": list(raw["expected_gap_ids"]),
                "actual": {
                    "matched_findings": [
                        {
                            "expectation_id": expectation["id"],
                            "severity": expectation["severity"],
                            "locator_present": expectation["locator_required"],
                            "evidence_refs": (
                                [f"fixture://{raw['id']}#{expectation['id']}"]
                                if expectation["evidence_required"]
                                else []
                            ),
                        }
                        for expectation in expectations
                    ],
                    "unmatched_finding_ids": [],
                    "triggered_forbidden_ids": [],
                    "gap_ids": list(raw["expected_gap_ids"]),
                },
            }
        )
    return {
        "suite": corpus["suite"],
        "provenance": {
            "mode": "deterministic-fixture",
            "declared_by": "deterministic-harness",
            "independence_claim": False,
            "agent_calls": 0,
            "network_calls": 0,
            "target_executions": 0,
            "reviewer_receipts": [],
        },
        "cases": cases,
    }


def probe_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "passed": report["passed"],
        "failed_case_ids": [item["id"] for item in report["results"] if not item["passed"]],
        "metrics": report["metrics"],
    }


def run_self_test() -> dict[str, Any]:
    corpus, corpus_summary = load_corpus()
    payload = perfect_payload(corpus)
    positive = score_suite(payload)

    false_positive_payload = deepcopy(payload)
    false_positive_payload["cases"][0]["actual"]["unmatched_finding_ids"] = ["UNEXPECTED"]
    false_positive = score_suite(false_positive_payload)

    first_expected = next(case for case in payload["cases"] if case["expected_findings"])
    evidence_payload = deepcopy(payload)
    evidence_case = next(case for case in evidence_payload["cases"] if case["id"] == first_expected["id"])
    evidence_case["actual"]["matched_findings"][0]["evidence_refs"] = []
    missing_evidence = score_suite(evidence_payload)

    severity_payload = deepcopy(payload)
    severity_case = next(case for case in severity_payload["cases"] if case["id"] == first_expected["id"])
    severity_case["actual"]["matched_findings"][0]["severity"] = "minor"
    severity_mismatch = score_suite(severity_payload)

    gap_case_id = next(case["id"] for case in payload["cases"] if case["expected_gap_ids"])
    gap_payload = deepcopy(payload)
    gap_case = next(case for case in gap_payload["cases"] if case["id"] == gap_case_id)
    gap_case["actual"]["gap_ids"] = []
    missing_gap = score_suite(gap_payload)

    observed_payload = deepcopy(payload)
    observed_payload["provenance"] = {
        "mode": "same-context",
        "declared_by": "current-executor",
        "independence_claim": False,
        "agent_calls": 0,
        "network_calls": 0,
        "target_executions": 0,
        "reviewer_receipts": [
            {
                "profile": profile,
                "review_id": f"REV-SELF-{profile.upper()}",
                "path": f"receipts/{profile}.json",
                "sha256": "0" * 64,
            }
            for profile in sorted(PROFILES)
        ],
    }
    receipt_paths = {
        item["profile"]: item["path"]
        for item in observed_payload["provenance"]["reviewer_receipts"]
    }
    for case in observed_payload["cases"]:
        for match in case["actual"]["matched_findings"]:
            match["evidence_refs"] = [
                f"{receipt_paths[case['profile']]}#{match['expectation_id']}"
            ]
    observed = score_suite(observed_payload)
    checks = {
        "corpus_is_complete": corpus_summary["case_total"] >= 6,
        "accepts_expected_matches": positive["passed"] is True,
        "rejects_false_positive": false_positive["passed"] is False,
        "rejects_missing_evidence": missing_evidence["passed"] is False,
        "rejects_severity_mismatch": severity_mismatch["passed"] is False,
        "rejects_gap_dishonesty": missing_gap["passed"] is False,
        "binds_same_context_receipts": (
            observed["passed"] is True
            and observed["claim_boundaries"]["semantic_quality_observed"] is True
            and observed["claim_boundaries"]["independence_claim"] is False
            and observed["claim_boundaries"]["reviewer_receipt_count"] == 2
        ),
        "reports_zero_execution": positive["claim_boundaries"]["target_executions"] == 0,
    }
    return {
        "suite": "semantic-oracle-self-test",
        "passed": all(checks.values()),
        "checks": checks,
        "corpus": corpus_summary,
        "positive": positive,
        "negative_probes": {
            "false_positive": probe_summary(false_positive),
            "missing_evidence": probe_summary(missing_evidence),
            "severity_mismatch": probe_summary(severity_mismatch),
            "gap_dishonesty": probe_summary(missing_gap),
        },
        "same_context_provenance_probe": probe_summary(observed),
    }


def verify_receipt_files(value: dict[str, Any], workspace: Path) -> list[dict[str, Any]]:
    provenance = require_object(value.get("provenance"), "$.provenance")
    mode = require_string(provenance.get("mode"), "$.provenance.mode")
    if mode == "deterministic-fixture":
        return []
    receipts = validate_receipts(
        provenance.get("reviewer_receipts"),
        "$.provenance.reviewer_receipts",
    )
    root = workspace.resolve(strict=True)
    if not root.is_dir():
        raise OracleError("ORACLE_RECEIPT_PATH_INVALID", "workspace 必须是目录")
    verified: list[dict[str, Any]] = []
    for index, item in enumerate(receipts):
        try:
            path = (root / item["path"]).resolve(strict=True)
        except OSError as exc:
            raise OracleError(
                "ORACLE_RECEIPT_MISSING",
                f"receipt 不存在或不可读: {item['path']}",
            ) from exc
        if path != root and not path.is_relative_to(root):
            raise OracleError(
                "ORACLE_RECEIPT_PATH_INVALID",
                f"$.provenance.reviewer_receipts[{index}].path 越出 workspace",
            )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise OracleError(
                "ORACLE_RECEIPT_STALE",
                f"receipt hash 不匹配: {item['path']}",
            )
        document = require_object(
            json.loads(path.read_text(encoding="utf-8")),
            f"$receipt[{index}]",
        )
        reviewer = require_object(document.get("reviewer"), f"$receipt[{index}].reviewer")
        if document.get("review_id") != item["review_id"] or document.get("profile") != item["profile"]:
            raise OracleError(
                "ORACLE_RECEIPT_IDENTITY_MISMATCH",
                f"receipt identity 不匹配: {item['path']}",
            )
        if reviewer.get("mode") != mode:
            raise OracleError(
                "ORACLE_RECEIPT_PROVENANCE_MISMATCH",
                f"receipt mode 与 suite provenance 不一致: {item['path']}",
            )
        if reviewer.get("independence_claim") != provenance.get("independence_claim"):
            raise OracleError(
                "ORACLE_RECEIPT_PROVENANCE_MISMATCH",
                f"receipt independence 与 suite provenance 不一致: {item['path']}",
            )
        verified.append(
            {
                "profile": item["profile"],
                "review_id": item["review_id"],
                "path": item["path"],
                "sha256": digest,
                "verification_scope": "identity-hash-provenance",
            }
        )
    return verified


def render(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="确定性评分 Reviewer 语义 observation")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="人工裁定后的 observation JSON")
    source.add_argument("--self-test", action="store_true", help="运行内置正负自测")
    parser.add_argument("--workspace", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.self_test:
            report = run_self_test()
        else:
            payload = require_object(
                json.loads(args.input.read_text(encoding="utf-8")),
                "$",
            )
            report = score_suite(payload)
            verified = verify_receipt_files(payload, args.workspace)
            report["claim_boundaries"]["reviewer_receipts_verified"] = (
                "identity-hash-provenance"
            )
            report["verified_reviewer_receipts"] = verified
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
