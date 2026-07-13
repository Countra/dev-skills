"""与 runner 解耦的质量、配对、成本和不确定性统计。"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from typing import Any

from .errors import SuiteError


def wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> dict[str, Any]:
    """计算二项比例 Wilson interval；空样本不伪造区间。"""
    if total < 0 or successes < 0 or successes > total:
        raise ValueError("successes/total 组合无效")
    if total == 0:
        return {"low": None, "high": None, "confidence": 0.95, "available": False}
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return {
        "low": max(0.0, center - margin),
        "high": min(1.0, center + margin),
        "confidence": 0.95,
        "available": True,
    }


def percentile(values: list[float], quantile: float) -> float | None:
    if not 0 <= quantile <= 1:
        raise ValueError("quantile 必须在 0 到 1")
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize_numeric(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "p95": None,
            "sample_stdev": None,
            "available": False,
        }
    normalized = [float(value) for value in values]
    return {
        "count": len(normalized),
        "min": min(normalized),
        "max": max(normalized),
        "mean": statistics.fmean(normalized),
        "median": statistics.median(normalized),
        "p95": percentile(normalized, 0.95),
        "sample_stdev": statistics.stdev(normalized) if len(normalized) >= 2 else None,
        "available": True,
    }


def _quality_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(bool(item.get("deterministic", {}).get("passed")) for item in items)
    return {
        "n": len(items),
        "passed": passed,
        "pass_rate": passed / len(items),
        "wilson_interval": wilson_interval(passed, len(items)),
    }


def quality_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_variant[str(record.get("variant"))].append(record)
    result: dict[str, Any] = {}
    for variant, items in sorted(by_variant.items()):
        by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            by_mode[str(item.get("mode"))].append(item)
        result[variant] = {
            **_quality_summary(items),
            "by_mode": {mode: _quality_summary(mode_items) for mode, mode_items in sorted(by_mode.items())},
        }
    return result


def _optional_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def trigger_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总 candidate trigger observation，不把缺失真相的记录猜成负例。"""
    confusion = {"true_positive": 0, "false_positive": 0, "true_negative": 0, "false_negative": 0}
    invalid_records: list[str] = []
    for record in records:
        if record.get("variant") != "candidate" or record.get("mode") != "trigger":
            continue
        trigger = record.get("trigger")
        expected = trigger.get("expected") if isinstance(trigger, dict) else None
        observed = trigger.get("observed") if isinstance(trigger, dict) else None
        if not isinstance(expected, bool) or not isinstance(observed, bool):
            invalid_records.append(str(record.get("record_key")))
            continue
        if expected and observed:
            confusion["true_positive"] += 1
        elif expected:
            confusion["false_negative"] += 1
        elif observed:
            confusion["false_positive"] += 1
        else:
            confusion["true_negative"] += 1
    valid = sum(confusion.values())
    activated = confusion["true_positive"] + confusion["false_positive"]
    positives = confusion["true_positive"] + confusion["false_negative"]
    negatives = confusion["true_negative"] + confusion["false_positive"]
    return {
        "n": valid + len(invalid_records),
        "valid_n": valid,
        "invalid_n": len(invalid_records),
        "activated": activated,
        "activation_rate": _optional_rate(activated, valid),
        "true_positive_rate": _optional_rate(confusion["true_positive"], positives),
        "true_negative_rate": _optional_rate(confusion["true_negative"], negatives),
        "false_positive_rate": _optional_rate(confusion["false_positive"], negatives),
        "false_negative_rate": _optional_rate(confusion["false_negative"], positives),
        "confusion_matrix": confusion,
        "invalid_records": invalid_records,
        "available": valid > 0,
    }


def _provenance_key(record: dict[str, Any]) -> tuple[Any, ...]:
    value = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
    return (
        value.get("fingerprint"),
        value.get("lab_tree_sha256"),
        value.get("adapter"),
        value.get("cli_version"),
        value.get("model"),
        value.get("sandbox"),
        value.get("network_access"),
    )


def _pair_compatible(candidate: dict[str, Any], baseline: dict[str, Any]) -> tuple[bool, list[str]]:
    candidate_pairing = candidate.get("pairing")
    baseline_pairing = baseline.get("pairing")
    if not isinstance(candidate_pairing, dict) or not isinstance(baseline_pairing, dict):
        return False, ["invalid_pairing"]
    left = dict(candidate_pairing)
    right = dict(baseline_pairing)
    left.pop("skill_snapshot", None)
    right.pop("skill_snapshot", None)
    reasons = []
    if left != right:
        reasons.append("pairing_variables")
    required_provenance = (
        "fingerprint",
        "lab_tree_sha256",
        "adapter",
        "model",
        "sandbox",
        "network_access",
    )
    candidate_provenance = candidate.get("provenance")
    baseline_provenance = baseline.get("provenance")
    if not isinstance(candidate_provenance, dict) or not isinstance(baseline_provenance, dict):
        reasons.append("missing_provenance")
    elif any(name not in candidate_provenance or name not in baseline_provenance for name in required_provenance):
        reasons.append("missing_provenance")
    elif not candidate_provenance.get("fingerprint") or not baseline_provenance.get("fingerprint"):
        reasons.append("missing_provenance")
    elif _provenance_key(candidate) != _provenance_key(baseline):
        reasons.append("provenance")
    return not reasons, reasons


def paired_delta_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        if record.get("mode") != "behavior":
            continue
        pair_key = str(
            record.get("pairing", {}).get("pair_key")
            or f"{record.get('case_id')}:{record.get('repetition')}"
        )
        groups[pair_key][str(record.get("variant"))].append(record)
    deltas: list[float] = []
    excluded: list[dict[str, Any]] = []
    for pair_key, variants in sorted(groups.items()):
        reasons = []
        if set(variants) != {"candidate", "baseline"}:
            reasons.append("incomplete_pair")
        if any(len(items) != 1 for items in variants.values()):
            reasons.append("duplicate_pair_member")
        if reasons:
            excluded.append({"pair_key": pair_key, "reasons": reasons})
            continue
        candidate, baseline = variants["candidate"][0], variants["baseline"][0]
        compatible, reasons = _pair_compatible(candidate, baseline)
        if not compatible:
            excluded.append({"pair_key": pair_key, "reasons": reasons})
            continue
        candidate_pass = bool(candidate.get("deterministic", {}).get("passed"))
        baseline_pass = bool(baseline.get("deterministic", {}).get("passed"))
        deltas.append(float(int(candidate_pass) - int(baseline_pass)))
    return {
        "n_pairs": len(deltas),
        "wins": sum(value > 0 for value in deltas),
        "losses": sum(value < 0 for value in deltas),
        "ties": sum(value == 0 for value in deltas),
        "delta": summarize_numeric(deltas),
        "low_information": len(deltas) < 2 or not deltas or all(value == 0 for value in deltas),
        "excluded_pairs": excluded,
    }


def cost_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    token_fields = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
    token_totals = {field: 0 for field in token_fields}
    token_samples = {field: 0 for field in token_fields}
    durations: list[float] = []
    by_variant: dict[str, Counter[str]] = defaultdict(Counter)
    usage_records = 0
    for record in records:
        raw_usage = record.get("usage")
        usage = raw_usage if isinstance(raw_usage, dict) else {}
        if usage:
            usage_records += 1
        variant = str(record.get("variant"))
        for field in token_fields:
            value = usage.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                token_totals[field] += value
                token_samples[field] += 1
                by_variant[variant][field] += value
        duration = record.get("duration_seconds")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= 0:
            durations.append(float(duration))
    return {
        "tokens": token_totals,
        "token_availability": {
            field: {
                "sample_count": token_samples[field],
                "available": token_samples[field] > 0,
                "complete": token_samples[field] == len(records),
            }
            for field in token_fields
        },
        "tokens_by_variant": {variant: dict(values) for variant, values in sorted(by_variant.items())},
        "usage_records": usage_records,
        "record_count": len(records),
        "duration_seconds": summarize_numeric(durations),
    }


def failure_taxonomy(records: list[dict[str, Any]]) -> dict[str, int]:
    failures = Counter(
        str(record.get("deterministic", {}).get("failure_type"))
        for record in records
        if record.get("deterministic", {}).get("failure_type")
    )
    return dict(sorted(failures.items()))


def require_compatible_documents(documents: list[dict[str, Any]]) -> str | None:
    fingerprints = {document.get("fingerprint") for document in documents}
    if documents and None in fingerprints:
        raise SuiteError("评分文档缺少 fingerprint，禁止聚合", path="$.fingerprint")
    if len(fingerprints) > 1:
        raise SuiteError("禁止聚合不同 fingerprint 的评分文档", path="$.fingerprint")
    return next(iter(fingerprints), None)
