"""Behavior case 的闭合机械断言和 trusted verifier。"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ExecutionError, SuiteError
from .isolation import resolve_within
from .security import build_child_env, redact_text, sensitive_values


MAX_ASSERTION_FILE_BYTES = 4 * 1024 * 1024
MAX_VERIFIER_OUTPUT_BYTES = 1024 * 1024
MAX_GIT_STATUS_BYTES = 4 * 1024 * 1024
MAX_CHANGED_PATHS = 10_000


@dataclass(frozen=True)
class AssertionResult:
    """单项断言的稳定结果。"""

    assertion_id: str
    assertion_type: str
    status: str
    message: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "type": self.assertion_type,
            "status": self.status,
            "message": self.message,
            "evidence": self.evidence,
        }


def _result(assertion: dict[str, Any], passed: bool, message: str, evidence: dict[str, Any]) -> AssertionResult:
    return AssertionResult(assertion["id"], assertion["type"], "PASS" if passed else "FAIL", message, evidence)


def _error(assertion: dict[str, Any], message: str, evidence: dict[str, Any] | None = None) -> AssertionResult:
    return AssertionResult(assertion["id"], assertion["type"], "ERROR", message, evidence or {})


def _safe_path(workspace: Path, raw: str, *, must_exist: bool = False) -> Path:
    unresolved = workspace.resolve() / Path(raw.replace("\\", "/"))
    is_junction = getattr(unresolved, "is_junction", None)
    if unresolved.is_symlink() or bool(is_junction and is_junction()):
        raise SuiteError(f"断言路径不能是链接或 junction：{raw}", path="$.cases.assertions.path")
    return resolve_within(workspace, raw, must_exist=must_exist)


def _file_hash(path: Path, *, max_bytes: int) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(chunk)
            if total > max_bytes:
                raise ExecutionError(f"断言目标在读取期间超过 {max_bytes} bytes")
            digest.update(chunk)
    return digest.hexdigest()


def _path_evidence(path: Path, raw: str) -> dict[str, Any]:
    evidence: dict[str, Any] = {"path": raw, "exists": path.exists()}
    if path.is_file():
        size = path.stat().st_size
        evidence.update({"kind": "file", "size": size, "sha256_available": size <= MAX_ASSERTION_FILE_BYTES})
        if size <= MAX_ASSERTION_FILE_BYTES:
            evidence["sha256"] = _file_hash(path, max_bytes=MAX_ASSERTION_FILE_BYTES)
    elif path.is_dir():
        evidence["kind"] = "directory"
    return evidence


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise ExecutionError(f"断言目标不是文件：{path}")
    size = path.stat().st_size
    if size > MAX_ASSERTION_FILE_BYTES:
        raise ExecutionError(f"断言目标超过 {MAX_ASSERTION_FILE_BYTES} bytes")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ExecutionError(f"无法读取 UTF-8 断言目标：{exc}") from exc


def changed_paths(workspace: Path) -> list[str]:
    """返回相对 Git baseline 的 tracked 与 untracked 文件集合。"""
    try:
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.Popen(
                ["git", "-c", "core.quotepath=false", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
                cwd=workspace,
                env=build_child_env(
                    extra={
                        "GIT_CONFIG_GLOBAL": os.devnull,
                        "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_TERMINAL_PROMPT": "0",
                    }
                ),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
            )
            try:
                return_code = process.wait(timeout=30)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired as stop_exc:
                    raise ExecutionError("Git status 终止后仍未退出") from stop_exc
                raise ExecutionError("Git status 在 30 秒后超时") from exc
            output_bytes = os.fstat(stdout_file.fileno()).st_size + os.fstat(stderr_file.fileno()).st_size
            if output_bytes > MAX_GIT_STATUS_BYTES:
                raise ExecutionError("Git status 输出超过大小上限")
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read(MAX_GIT_STATUS_BYTES + 1).decode("utf-8", errors="replace")
            stderr = stderr_file.read(1000).decode("utf-8", errors="replace")
    except OSError as exc:
        raise ExecutionError(f"无法读取 Git 差异：{exc}") from exc
    if return_code != 0:
        raise ExecutionError(f"Git status 失败：{stderr.strip()}")
    paths: set[str] = set()
    entries = [entry for entry in stdout.split("\0") if entry]
    index = 0
    while index < len(entries):
        entry = entries[index]
        if len(entry) < 4 or entry[2] != " ":
            raise ExecutionError("Git status 返回无法识别的 porcelain 记录")
        paths.add(entry[3:].replace("\\", "/"))
        if "R" in entry[:2] or "C" in entry[:2]:
            index += 1
            if index >= len(entries):
                raise ExecutionError("Git status 的 rename/copy 记录缺少原路径")
            paths.add(entries[index].replace("\\", "/"))
        if len(paths) > MAX_CHANGED_PATHS:
            raise ExecutionError(f"Git 变化路径超过 {MAX_CHANGED_PATHS} 项")
        index += 1
    return sorted(paths)


def _json_field(value: Any, selector: str) -> Any:
    parts = selector.split(".") if not selector.startswith("/") else [
        item.replace("~1", "/").replace("~0", "~") for item in selector[1:].split("/")
    ]
    current = value
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(selector)
    return current


def _evaluate_path_assertion(assertion: dict[str, Any], workspace: Path) -> AssertionResult:
    raw = assertion["path"]
    path = _safe_path(workspace, raw)
    evidence = _path_evidence(path, raw)
    kind = assertion["type"]
    if kind == "file_exists":
        return _result(assertion, path.is_file(), "目标文件存在" if path.is_file() else "目标文件不存在", evidence)
    if kind == "file_absent":
        return _result(assertion, not path.exists(), "目标路径不存在" if not path.exists() else "目标路径意外存在", evidence)
    changes = changed_paths(workspace)
    portable = raw.replace("\\", "/").rstrip("/")
    changed = portable in changes or any(item.startswith(portable + "/") for item in changes)
    evidence["changed"] = changed
    evidence["changed_path_count"] = len(changes)
    expected = kind == "path_changed"
    return _result(assertion, changed == expected, f"路径变化状态为 {changed}", evidence)


def _evaluate_content_assertion(assertion: dict[str, Any], workspace: Path) -> AssertionResult:
    raw = assertion["path"]
    path = _safe_path(workspace, raw, must_exist=True)
    kind = assertion["type"]
    if kind == "json_valid":
        try:
            json.loads(_read_text(path))
        except json.JSONDecodeError as exc:
            return _result(assertion, False, f"JSON 无效：{exc.msg}", _path_evidence(path, raw))
        return _result(assertion, True, "JSON 有效", _path_evidence(path, raw))
    if kind == "json_field_equals":
        specification = assertion.get("value")
        if not isinstance(specification, dict) or set(specification) != {"field", "equals"}:
            return _error(assertion, "json_field_equals.value 必须包含且仅包含 field 与 equals")
        try:
            document = json.loads(_read_text(path))
            actual = _json_field(document, str(specification["field"]))
        except (json.JSONDecodeError, KeyError) as exc:
            return _result(assertion, False, f"JSON field 无法读取：{exc}", _path_evidence(path, raw))
        evidence = _path_evidence(path, raw)
        evidence.update({"field": specification["field"], "actual": actual, "expected": specification["equals"]})
        return _result(assertion, actual == specification["equals"], "JSON field 比较完成", evidence)
    text = _read_text(path)
    if kind == "regex_matches":
        matched = re.search(assertion["pattern"], text) is not None
        return _result(assertion, matched, "正则匹配完成", {**_path_evidence(path, raw), "matched": matched})
    needle = assertion.get("value")
    if not isinstance(needle, str):
        return _error(assertion, "文本断言 value 必须是字符串")
    contains = needle in text
    expected = kind == "text_contains"
    return _result(assertion, contains == expected, f"文本包含状态为 {contains}", _path_evidence(path, raw))


def _evaluate_diff_assertion(assertion: dict[str, Any], workspace: Path) -> AssertionResult:
    changes = changed_paths(workspace)
    kind = assertion["type"]
    raw_patterns = assertion["allow"] if kind == "diff_allows_only" else assertion["deny"]
    patterns = [pattern.replace("\\", "/") for pattern in raw_patterns]
    matched = [path for path in changes if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)]
    if kind == "diff_allows_only":
        unexpected = [path for path in changes if path not in matched]
        passed = not unexpected
        message = "所有变化均在 allow 范围内" if passed else "存在 allow 范围外变化"
        details = unexpected
    else:
        passed = not matched
        message = "没有命中 deny 范围" if passed else "存在被禁止的变化"
        details = matched
    return _result(
        assertion,
        passed,
        message,
        {
            "patterns": patterns,
            "changed_path_count": len(changes),
            "relevant_paths": details[:100],
            "evidence_truncated": len(details) > 100,
        },
    )


def _evaluate_verifier(assertion: dict[str, Any], workspace: Path, *, trusted: bool) -> AssertionResult:
    if not trusted:
        return _error(assertion, "verifier_command 未获得 trusted_verifier 授权")
    cwd = _safe_path(workspace, assertion.get("cwd", "."), must_exist=True)
    if not cwd.is_dir():
        return _error(assertion, "verifier cwd 不是目录", {"cwd": assertion.get("cwd", ".")})
    argv = assertion["argv"]
    timeout = int(assertion.get("timeout_seconds", 30))
    try:
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            with subprocess.Popen(
                argv,
                cwd=cwd,
                env=build_child_env(
                    extra={
                        "GIT_CONFIG_GLOBAL": os.devnull,
                        "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_TERMINAL_PROMPT": "0",
                    }
                ),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                shell=False,
            ) as process:
                deadline = time.monotonic() + timeout
                failure: str | None = None
                while process.poll() is None:
                    output_size = os.fstat(stdout_file.fileno()).st_size + os.fstat(stderr_file.fileno()).st_size
                    if output_size > MAX_VERIFIER_OUTPUT_BYTES:
                        failure = "verifier 输出超过大小上限"
                        process.kill()
                        break
                    if time.monotonic() >= deadline:
                        failure = f"verifier 在 {timeout} 秒后超时"
                        process.kill()
                        break
                    time.sleep(0.02)
                return_code = process.wait(timeout=5)
            output_size = os.fstat(stdout_file.fileno()).st_size + os.fstat(stderr_file.fileno()).st_size
            if output_size > MAX_VERIFIER_OUTPUT_BYTES and failure is None:
                failure = "verifier 输出超过大小上限"
            if failure:
                return _error(assertion, failure, {"output_bytes": output_size})
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read(2000).decode("utf-8", errors="replace")
            stderr = stderr_file.read(2000).decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return _error(assertion, "verifier 终止后仍未退出", {"cwd": str(cwd.relative_to(workspace))})
    except OSError as exc:
        return _error(assertion, f"verifier 无法启动：{exc}", {"cwd": str(cwd.relative_to(workspace))})
    secrets = sensitive_values()
    evidence = {
        "cwd": str(cwd.relative_to(workspace)).replace("\\", "/") or ".",
        "return_code": return_code,
        "stdout_excerpt": redact_text(stdout, secrets=secrets),
        "stderr_excerpt": redact_text(stderr, secrets=secrets),
        "output_bytes": output_size,
    }
    passed = return_code == 0
    return _result(assertion, passed, "verifier 通过" if passed else "verifier 返回非零退出码", evidence)


def evaluate_assertion(
    assertion: dict[str, Any],
    *,
    workspace: Path,
    trusted_verifier: bool = False,
) -> AssertionResult:
    """执行单个闭合断言；运行期异常转换为可报告的 ERROR。"""
    assertion_type = assertion.get("type")
    try:
        if assertion_type in {"file_exists", "file_absent", "path_changed", "path_unchanged"}:
            return _evaluate_path_assertion(assertion, workspace)
        if assertion_type in {
            "text_contains",
            "text_excludes",
            "regex_matches",
            "json_valid",
            "json_field_equals",
        }:
            return _evaluate_content_assertion(assertion, workspace)
        if assertion_type in {"diff_allows_only", "diff_excludes"}:
            return _evaluate_diff_assertion(assertion, workspace)
        if assertion_type == "verifier_command":
            return _evaluate_verifier(assertion, workspace, trusted=trusted_verifier)
        return _error(assertion, f"未知 assertion type：{assertion_type}")
    except (ExecutionError, SuiteError, OSError, ValueError, TypeError) as exc:
        return _error(assertion, str(exc))


def evaluate_assertions(
    assertions: list[dict[str, Any]],
    *,
    workspace: Path,
    trusted_verifier: bool = False,
) -> dict[str, Any]:
    """执行全部断言，不因单项 FAIL/ERROR 隐藏后续证据。"""
    results = [
        evaluate_assertion(item, workspace=workspace, trusted_verifier=trusted_verifier).to_dict()
        for item in assertions
    ]
    counts = {status: sum(item["status"] == status for item in results) for status in ("PASS", "FAIL", "ERROR")}
    return {
        "status": "ERROR" if counts["ERROR"] else "FAIL" if counts["FAIL"] else "PASS",
        "counts": counts,
        "results": results,
    }
