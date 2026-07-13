"""Run manifest 的闭合结构与跨阶段证据校验。"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .errors import SuiteError


ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
WINDOWS_ABSOLUTE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")
ROOT_FIELDS = {
    "schema_version",
    "state",
    "status",
    "suite_id",
    "fingerprint",
    "run_id",
    "execution_order",
    "requested_concurrency",
    "effective_concurrency",
    "gates",
    "lab_identity",
    "source_identity",
    "records",
    "budget",
    "error",
}
ROOT_REQUIRED = ROOT_FIELDS - {"error"}
RECORD_FIELDS = {
    "case_id",
    "mode",
    "split",
    "repetition",
    "variant",
    "status",
    "workspace",
    "baseline_commit",
    "pairing",
    "expected_trigger",
    "observed_trigger",
    "runner",
    "assertions",
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
RUNNER_FIELDS = {
    "outcome",
    "return_code",
    "final",
    "trace_path",
    "stderr_path",
    "duration_seconds",
    "usage",
    "provenance",
    "observation",
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
ASSERTION_RESULT_FIELDS = {"assertion_id", "type", "status", "message", "evidence"}
MAX_RECORDS = 256
MAX_INPUTS = 64
MAX_ASSERTIONS = 64
MAX_REPETITIONS = 20
MAX_AGENT_RUNS = 256
MAX_JUDGE_RUNS = 32
MAX_WALL_SECONDS = 86_400


def _object(value: Any, path: str, fields: set[str], required: set[str] | None = None) -> dict[str, Any]:
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


def _nonnegative_number(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise SuiteError("必须是非负数值", path=path)
    return float(value)


def _relative_or_none(value: Any, path: str) -> None:
    if value is None:
        return
    raw = _string(value, path)
    candidate = Path(raw)
    if (
        candidate.is_absolute()
        or raw.startswith(("/", "\\"))
        or WINDOWS_ABSOLUTE_PATTERN.match(raw)
        or ".." in re.split(r"[\\/]", raw)
    ):
        raise SuiteError("必须是 run 目录内相对路径", path=path)


def _identity(value: Any, path: str) -> dict[str, Any]:
    item = _object(value, path, {"tree_sha256", "file_count"})
    _sha256(item["tree_sha256"], f"{path}.tree_sha256")
    count = item["file_count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise SuiteError("file_count 必须是正整数", path=f"{path}.file_count")
    return item


def _validate_pairing(value: Any, path: str) -> dict[str, Any]:
    item = _object(value, path, PAIRING_FIELDS)
    _string(item["pair_key"], f"{path}.pair_key")
    _sha256(item["prompt_sha256"], f"{path}.prompt_sha256")
    if (
        not isinstance(item["inputs"], list)
        or len(item["inputs"]) > MAX_INPUTS
        or not all(isinstance(raw, str) for raw in item["inputs"])
    ):
        raise SuiteError(f"inputs 必须是至多 {MAX_INPUTS} 项的字符串数组", path=f"{path}.inputs")
    for index, raw in enumerate(item["inputs"]):
        _relative_or_none(raw, f"{path}.inputs[{index}]")
    _string(item["model"], f"{path}.model")
    if item["sandbox"] not in {"read-only", "workspace-write"}:
        raise SuiteError("sandbox 无效", path=f"{path}.sandbox")
    if not isinstance(item["timeout_seconds"], int) or isinstance(item["timeout_seconds"], bool):
        raise SuiteError("timeout_seconds 必须是正整数", path=f"{path}.timeout_seconds")
    if item["timeout_seconds"] < 1 or item["timeout_seconds"] > 3600:
        raise SuiteError("timeout_seconds 超出实现上限", path=f"{path}.timeout_seconds")
    if item["network_access"] is not False:
        raise SuiteError("network_access 必须为 false", path=f"{path}.network_access")
    if item["skill_snapshot"] not in {"candidate", "baseline", "none"}:
        raise SuiteError("skill_snapshot 无效", path=f"{path}.skill_snapshot")
    return item


def _validate_runner(value: Any, path: str, record: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    item = _object(value, path, RUNNER_FIELDS)
    if item["outcome"] not in {"passed", "failed"}:
        raise SuiteError("runner outcome 无效", path=f"{path}.outcome")
    if not isinstance(item["return_code"], int) or isinstance(item["return_code"], bool):
        raise SuiteError("return_code 必须是整数", path=f"{path}.return_code")
    if not isinstance(item["final"], dict) or set(item["final"]) - {"activation_receipt", "response"}:
        raise SuiteError("final 字段无效", path=f"{path}.final")
    if "activation_receipt" in item["final"] and not isinstance(
        item["final"]["activation_receipt"],
        (str, type(None)),
    ):
        raise SuiteError("activation_receipt 必须是字符串或 null", path=f"{path}.final.activation_receipt")
    if "response" in item["final"] and not isinstance(item["final"]["response"], str):
        raise SuiteError("response 必须是字符串", path=f"{path}.final.response")
    _relative_or_none(item["trace_path"], f"{path}.trace_path")
    _relative_or_none(item["stderr_path"], f"{path}.stderr_path")
    if item["duration_seconds"] is not None:
        _nonnegative_number(item["duration_seconds"], f"{path}.duration_seconds")
    usage = _object(item["usage"], f"{path}.usage", TOKEN_FIELDS, set())
    for name, token_count in usage.items():
        if not isinstance(token_count, int) or isinstance(token_count, bool) or token_count < 0:
            raise SuiteError("token count 必须是非负整数", path=f"{path}.usage.{name}")
    provenance = _object(item["provenance"], f"{path}.provenance", PROVENANCE_FIELDS, PROVENANCE_REQUIRED)
    if provenance["adapter"] not in {"fake", "codex-cli"}:
        raise SuiteError("adapter 无效", path=f"{path}.provenance.adapter")
    for name in ("cli_version", "model", "case_id", "variant"):
        _string(provenance[name], f"{path}.provenance.{name}")
    for name in ("fingerprint", "lab_tree_sha256", "prompt_sha256"):
        _sha256(provenance[name], f"{path}.provenance.{name}")
    if "permission_profile" in provenance:
        _string(provenance["permission_profile"], f"{path}.provenance.permission_profile")
    if "skill_tree_sha256" in provenance:
        _sha256(provenance["skill_tree_sha256"], f"{path}.provenance.skill_tree_sha256")
    if "trace" in provenance and not isinstance(provenance["trace"], dict):
        raise SuiteError("trace 必须是 JSON object", path=f"{path}.provenance.trace")
    if provenance["fingerprint"] != manifest["fingerprint"]:
        raise SuiteError("provenance fingerprint 不一致", path=f"{path}.provenance.fingerprint")
    if provenance["lab_tree_sha256"] != manifest["lab_identity"]["tree_sha256"]:
        raise SuiteError("provenance lab identity 不一致", path=f"{path}.provenance.lab_tree_sha256")
    if provenance["case_id"] != record["case_id"] or provenance["variant"] != record["variant"]:
        raise SuiteError("provenance case/variant 不一致", path=f"{path}.provenance")
    if (
        not isinstance(provenance["attempt"], int)
        or isinstance(provenance["attempt"], bool)
        or provenance["attempt"] != record["repetition"]
    ):
        raise SuiteError("provenance attempt 不一致", path=f"{path}.provenance.attempt")
    if (
        provenance["network_access"] is not False
        or provenance["sandbox"] != record["pairing"]["sandbox"]
        or provenance["model"] != record["pairing"]["model"]
        or provenance["prompt_sha256"] != record["pairing"]["prompt_sha256"]
    ):
        raise SuiteError("provenance 执行条件不一致", path=f"{path}.provenance")
    snapshot_variant = "candidate" if record["mode"] == "trigger" else record["pairing"]["skill_snapshot"]
    expected_skill = manifest["source_identity"].get(snapshot_variant)
    expected_hash = expected_skill.get("tree_sha256") if isinstance(expected_skill, dict) else None
    if expected_hash is not None and provenance.get("skill_tree_sha256") != expected_hash:
        raise SuiteError("provenance skill identity 不一致", path=f"{path}.provenance.skill_tree_sha256")
    if expected_hash is None and "skill_tree_sha256" in provenance:
        raise SuiteError("无 skill 的 run 不允许 skill identity", path=f"{path}.provenance.skill_tree_sha256")
    observation = _object(item["observation"], f"{path}.observation", {"activation_receipt_exact"}, set())
    if "activation_receipt_exact" in observation and not isinstance(observation["activation_receipt_exact"], bool):
        raise SuiteError("activation observation 必须是 boolean", path=f"{path}.observation.activation_receipt_exact")
    observed = bool(observation.get("activation_receipt_exact"))
    if record["mode"] == "trigger" and observed != record["observed_trigger"]:
        raise SuiteError("runner observation 与 trigger truth 不一致", path=f"{path}.observation")
    if record["mode"] == "behavior" and observation:
        raise SuiteError("behavior runner 不允许 trigger observation", path=f"{path}.observation")
    return item


def _validate_assertions(value: Any, path: str, mode: str) -> None:
    if mode == "trigger":
        if value is not None:
            raise SuiteError("trigger record 不允许 assertions", path=path)
        return
    item = _object(value, path, {"status", "counts", "results"})
    if item["status"] not in {"PASS", "FAIL", "ERROR"}:
        raise SuiteError("assertion status 无效", path=f"{path}.status")
    counts = _object(item["counts"], f"{path}.counts", {"PASS", "FAIL", "ERROR"})
    if not all(isinstance(count, int) and not isinstance(count, bool) and count >= 0 for count in counts.values()):
        raise SuiteError("assertion counts 必须是非负整数", path=f"{path}.counts")
    if (
        not isinstance(item["results"], list)
        or len(item["results"]) > MAX_ASSERTIONS
        or len(item["results"]) != sum(counts.values())
    ):
        raise SuiteError("assertion results 与 counts 数量不一致", path=f"{path}.results")
    statuses = []
    for index, raw in enumerate(item["results"]):
        result_path = f"{path}.results[{index}]"
        result = _object(raw, result_path, ASSERTION_RESULT_FIELDS)
        assertion_id = _string(result["assertion_id"], f"{result_path}.assertion_id")
        if not ID_PATTERN.fullmatch(assertion_id):
            raise SuiteError("assertion_id 格式无效", path=f"{result_path}.assertion_id")
        _string(result["type"], f"{result_path}.type")
        if result["status"] not in {"PASS", "FAIL", "ERROR"}:
            raise SuiteError("assertion result status 无效", path=f"{result_path}.status")
        if not isinstance(result["message"], str) or not isinstance(result["evidence"], dict):
            raise SuiteError("assertion result message/evidence 无效", path=result_path)
        statuses.append(result["status"])
    if Counter(statuses) != Counter(counts):
        raise SuiteError("assertion result 状态与 counts 不一致", path=f"{path}.results")
    expected_status = "ERROR" if counts["ERROR"] else "FAIL" if counts["FAIL"] else "PASS"
    if item["status"] != expected_status:
        raise SuiteError("assertion summary 与 counts 不一致", path=f"{path}.status")


def validate_assertion_summary(value: Any, *, path: str, mode: str) -> None:
    """复用 run assertion 契约校验 grade 中保留的原始证据。"""
    _validate_assertions(value, path, mode)


def _validate_record(value: Any, path: str, manifest: dict[str, Any]) -> dict[str, Any]:
    item = _object(value, path, RECORD_FIELDS)
    case_id = _string(item["case_id"], f"{path}.case_id")
    if not ID_PATTERN.fullmatch(case_id):
        raise SuiteError("case_id 格式无效", path=f"{path}.case_id")
    if item["mode"] not in {"trigger", "behavior"} or item["split"] not in {"train", "validation", "holdout"}:
        raise SuiteError("mode 或 split 无效", path=path)
    if (
        not isinstance(item["repetition"], int)
        or isinstance(item["repetition"], bool)
        or not 1 <= item["repetition"] <= MAX_REPETITIONS
    ):
        raise SuiteError(f"repetition 必须在 1 到 {MAX_REPETITIONS}", path=f"{path}.repetition")
    allowed_variants = {"candidate"} if item["mode"] == "trigger" else {"candidate", "baseline"}
    if item["variant"] not in allowed_variants or item["status"] not in {"PASS", "FAIL"}:
        raise SuiteError("variant 或 status 无效", path=path)
    if item["workspace"] is None:
        raise SuiteError("workspace 必须是相对路径", path=f"{path}.workspace")
    _relative_or_none(item["workspace"], f"{path}.workspace")
    if not isinstance(item["baseline_commit"], str) or not GIT_COMMIT_PATTERN.fullmatch(item["baseline_commit"]):
        raise SuiteError("baseline_commit 无效", path=f"{path}.baseline_commit")
    pairing = _validate_pairing(item["pairing"], f"{path}.pairing")
    if pairing["pair_key"] != f"{case_id}:{item['repetition']}":
        raise SuiteError("pair_key 与 case/repetition 不一致", path=f"{path}.pairing.pair_key")
    if item["mode"] == "trigger":
        if not isinstance(item["expected_trigger"], bool) or not isinstance(item["observed_trigger"], bool):
            raise SuiteError("trigger truth 必须是 boolean", path=path)
        if pairing["sandbox"] != "read-only" or pairing["skill_snapshot"] != "none":
            raise SuiteError("trigger pairing 必须只读且不挂载 behavior snapshot", path=f"{path}.pairing")
    elif item["expected_trigger"] is not None or item["observed_trigger"] is not None:
        raise SuiteError("behavior record 不允许 trigger truth", path=path)
    elif item["variant"] == "candidate" and pairing["skill_snapshot"] != "candidate":
        raise SuiteError("candidate behavior 缺少 candidate snapshot", path=f"{path}.pairing.skill_snapshot")
    elif item["variant"] == "baseline":
        expected_snapshot = "none" if manifest["source_identity"]["baseline"] == "none" else "baseline"
        if pairing["skill_snapshot"] != expected_snapshot:
            raise SuiteError("baseline snapshot 与 source identity 不一致", path=f"{path}.pairing.skill_snapshot")
    _validate_runner(item["runner"], f"{path}.runner", item, manifest)
    _validate_assertions(item["assertions"], f"{path}.assertions", item["mode"])
    return item


def validate_run_manifest(value: Any) -> dict[str, Any]:
    """校验可评分的 completed/failed run manifest，拒绝运行中快照。"""
    manifest = _object(value, "$", ROOT_FIELDS, ROOT_REQUIRED)
    if isinstance(manifest["schema_version"], bool) or manifest["schema_version"] != 1:
        raise SuiteError("schema_version 必须为 1", path="$.schema_version")
    if manifest["state"] not in {"completed", "failed"}:
        raise SuiteError("只允许评分 completed 或 failed manifest", path="$.state")
    expected_statuses = {"PASS", "FAIL"} if manifest["state"] == "completed" else {"ERROR"}
    if manifest["status"] not in expected_statuses:
        raise SuiteError("state 与 status 不一致", path="$.status")
    if manifest["state"] == "failed" and "error" not in manifest:
        raise SuiteError("failed manifest 缺少 error", path="$.error")
    if manifest["state"] == "completed" and "error" in manifest:
        raise SuiteError("completed manifest 不允许 error", path="$.error")
    suite_id = _string(manifest["suite_id"], "$.suite_id")
    run_id = _string(manifest["run_id"], "$.run_id")
    if not ID_PATTERN.fullmatch(suite_id) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise SuiteError("suite_id 或 run_id 格式无效", path="$")
    _sha256(manifest["fingerprint"], "$.fingerprint")
    if manifest["execution_order"] != "serial-paired-alternating":
        raise SuiteError("execution_order 无效", path="$.execution_order")
    if (
        not isinstance(manifest["requested_concurrency"], int)
        or isinstance(manifest["requested_concurrency"], bool)
        or not 1 <= manifest["requested_concurrency"] <= 4
    ):
        raise SuiteError("requested_concurrency 必须在 1 到 4", path="$.requested_concurrency")
    if isinstance(manifest["effective_concurrency"], bool) or manifest["effective_concurrency"] != 1:
        raise SuiteError("effective_concurrency 必须为 1", path="$.effective_concurrency")
    gates = _object(
        manifest["gates"],
        "$.gates",
        {"trigger_threshold", "required_case_pass_rate", "judge_required"},
    )
    for name in ("trigger_threshold", "required_case_pass_rate"):
        threshold = gates[name]
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not 0 <= threshold <= 1:
            raise SuiteError("gate threshold 必须在 0 到 1", path=f"$.gates.{name}")
    if not isinstance(gates["judge_required"], bool):
        raise SuiteError("judge_required 必须是 boolean", path="$.gates.judge_required")
    _identity(manifest["lab_identity"], "$.lab_identity")
    source = _object(manifest["source_identity"], "$.source_identity", {"candidate", "baseline"})
    _identity(source["candidate"], "$.source_identity.candidate")
    if source["baseline"] != "none":
        _identity(source["baseline"], "$.source_identity.baseline")
    budget = _object(manifest["budget"], "$.budget", {"agent_runs", "judge_runs", "remaining_seconds"})
    limits = {"agent_runs": MAX_AGENT_RUNS, "judge_runs": MAX_JUDGE_RUNS}
    for name, limit in limits.items():
        if (
            not isinstance(budget[name], int)
            or isinstance(budget[name], bool)
            or not 0 <= budget[name] <= limit
        ):
            raise SuiteError("budget count 必须是非负整数", path=f"$.budget.{name}")
    remaining_seconds = _nonnegative_number(budget["remaining_seconds"], "$.budget.remaining_seconds")
    if remaining_seconds > MAX_WALL_SECONDS:
        raise SuiteError("remaining_seconds 超出实现上限", path="$.budget.remaining_seconds")
    records = manifest["records"]
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise SuiteError(f"records 必须是至多 {MAX_RECORDS} 项的数组", path="$.records")
    if manifest["state"] == "completed" and not records:
        raise SuiteError("completed manifest 必须包含 records", path="$.records")
    for index, record in enumerate(records):
        _validate_record(record, f"$.records[{index}]", manifest)
    if "error" in manifest:
        error = _object(
            manifest["error"],
            "$.error",
            {"code", "message", "outcome", "path", "guidance"},
            {"code", "message", "outcome"},
        )
        for name in ("code", "message", "outcome"):
            _string(error[name], f"$.error.{name}")
        for name in ("path", "guidance"):
            if name in error and not isinstance(error[name], str):
                raise SuiteError("error 可选字段必须是字符串", path=f"$.error.{name}")
    if manifest["state"] == "completed":
        expected_status = "PASS" if all(record["status"] == "PASS" for record in records) else "FAIL"
        if manifest["status"] != expected_status:
            raise SuiteError("manifest status 与 record 状态不一致", path="$.status")
        if budget["agent_runs"] != len(records):
            raise SuiteError("completed manifest 的 agent_runs 与 records 不一致", path="$.budget.agent_runs")
        record_keys: set[tuple[str, int, str]] = set()
        behavior_groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for record in records:
            record_key = (record["case_id"], record["repetition"], record["variant"])
            if record_key in record_keys:
                raise SuiteError("run record key 重复", path="$.records")
            record_keys.add(record_key)
            if record["mode"] == "behavior":
                key = (record["case_id"], record["repetition"])
                behavior_groups.setdefault(key, []).append(record)
        for pair in behavior_groups.values():
            if len(pair) != 2 or {record["variant"] for record in pair} != {"candidate", "baseline"}:
                raise SuiteError("completed behavior pair 不完整", path="$.records")
            expected_order = ["candidate", "baseline"] if pair[0]["repetition"] % 2 else ["baseline", "candidate"]
            if [record["variant"] for record in pair] != expected_order:
                raise SuiteError("behavior pair 顺序未按 repetition 交替", path="$.records")
            left_pairing = {key: value for key, value in pair[0]["pairing"].items() if key != "skill_snapshot"}
            right_pairing = {key: value for key, value in pair[1]["pairing"].items() if key != "skill_snapshot"}
            if left_pairing != right_pairing:
                raise SuiteError("behavior pair 执行条件不一致", path="$.records")
    return manifest
