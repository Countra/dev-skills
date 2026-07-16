#!/usr/bin/env python3
"""validation ledger evidence 的封闭 provenance 契约。"""

from __future__ import annotations

import re
from typing import Any

from harness_state_errors import StateError


VALIDATION_RECORD_FIELDS = {
    "validation_id",
    "result",
    "command",
    "claim_source",
    "stage_attempt",
    "target_digest",
    "exit_code",
    "summary",
    "claim_boundary",
}
VALIDATION_RESULTS = {"passed", "failed", "not-run"}
VALIDATION_CLAIM_SOURCES = {"observed", "reported", "not-run"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def validate_validation_record(
    payload: Any,
    *,
    attempt: int | None,
) -> dict[str, Any]:
    """校验 validation event 的事实来源、目标与 attempt 绑定。"""

    if not isinstance(payload, dict):
        raise StateError(
            "RUN_STATE_VALIDATION_PAYLOAD_INVALID",
            "validation payload 必须是 object。",
        )
    unknown = sorted(set(payload) - VALIDATION_RECORD_FIELDS)
    missing = sorted(VALIDATION_RECORD_FIELDS - set(payload))
    if unknown or missing:
        raise StateError(
            "RUN_STATE_VALIDATION_PAYLOAD_INVALID",
            f"validation payload 字段不封闭：unknown={unknown}, missing={missing}",
        )
    for field in ("validation_id", "command", "summary", "claim_boundary"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise StateError(
                "RUN_STATE_VALIDATION_PAYLOAD_INVALID",
                f"validation payload.{field} 必须是非空字符串。",
            )
    result = payload.get("result")
    claim_source = payload.get("claim_source")
    if result not in VALIDATION_RESULTS or claim_source not in VALIDATION_CLAIM_SOURCES:
        raise StateError(
            "RUN_STATE_VALIDATION_PROVENANCE_INVALID",
            "validation result 或 claim_source 无效。",
        )
    stage_attempt = payload.get("stage_attempt")
    if (
        not isinstance(stage_attempt, int)
        or isinstance(stage_attempt, bool)
        or stage_attempt < 1
        or stage_attempt != attempt
    ):
        raise StateError(
            "RUN_STATE_VALIDATION_ATTEMPT_MISMATCH",
            "validation stage_attempt 必须与 event/current attempt 一致。",
        )
    digest = payload.get("target_digest")
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        raise StateError(
            "RUN_STATE_VALIDATION_TARGET_INVALID",
            "validation target_digest 必须是小写 SHA-256。",
        )
    exit_code = payload.get("exit_code")
    if exit_code is not None and (
        not isinstance(exit_code, int) or isinstance(exit_code, bool)
    ):
        raise StateError(
            "RUN_STATE_VALIDATION_EXIT_INVALID",
            "validation exit_code 必须是 integer 或 null。",
        )
    if result == "passed" and (claim_source != "observed" or exit_code != 0):
        raise StateError(
            "RUN_STATE_VALIDATION_PROVENANCE_INVALID",
            "只有 observed 且 exit_code=0 的 validation 可以 passed。",
        )
    if claim_source == "observed" and result == "failed" and (
        exit_code is None or exit_code == 0
    ):
        raise StateError(
            "RUN_STATE_VALIDATION_EXIT_INVALID",
            "observed failed validation 需要非零 exit_code。",
        )
    if claim_source == "not-run" and (result != "not-run" or exit_code is not None):
        raise StateError(
            "RUN_STATE_VALIDATION_PROVENANCE_INVALID",
            "not-run claim 必须使用 result=not-run 且 exit_code=null。",
        )
    if claim_source == "reported" and result == "passed":
        raise StateError(
            "RUN_STATE_VALIDATION_PROVENANCE_INVALID",
            "reported evidence 不能直接证明 validation passed。",
        )
    return payload
