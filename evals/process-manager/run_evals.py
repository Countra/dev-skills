#!/usr/bin/env python3
"""执行 process-manager agent fixtures 与公共命令契约检查。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "process-manager"
SCRIPT_DIR = SKILL_ROOT / "scripts"
TEMPLATE_DIR = SKILL_ROOT / "templates"
EXAMPLE_DIR = REPO_ROOT / "examples" / "process-manager"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_fixtures() -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate((EVAL_DIR / "fixtures.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or not isinstance(value.get("id"), str):
            raise ValueError(f"fixtures.jsonl:{line_number} fixture 无效")
        values.append(value)
    return values


def run_command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-X", "utf8", "-B", *arguments]
    try:
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124, "", "命令执行超时")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def create_validation_fixture(workspace: Path) -> tuple[Path, Path, Path]:
    workspace.mkdir(parents=True, exist_ok=True)
    config = (workspace / ".harness" / "process-manager" / "config.json").resolve()
    service = (workspace / "service.json").resolve()
    legacy = (workspace / "legacy-service.json").resolve()
    fixture = SKILL_ROOT / "tests" / "fixtures" / "process_tree_service.py"
    write_json(
        service,
        {
            "name": "eval-service",
            "kind": "long-running",
            "cwd": str(workspace.resolve()),
            "launcher": {
                "type": "script",
                "interpreter": str(Path(sys.executable).resolve()),
                "script": str(fixture.resolve()),
                "args": ["--mode", "normal"],
                "pathArgs": [str((workspace / "identity.json").resolve())],
            },
            "environment": {"inherit": ["PATH"], "set": {}, "fromEnv": []},
            "stop": {"graceSeconds": 8},
            "readiness": {"type": "process", "stableSeconds": 1, "timeoutSeconds": 30},
            "logs": {"maxBytes": 10485760, "backups": 3},
        },
    )
    write_json(
        legacy,
        {
            "name": "legacy-service",
            "kind": "long-running",
            "cwd": str(workspace.resolve()),
            "launcher": {"type": "direct", "argv": [str(Path(sys.executable).resolve())]},
            "window": "hidden",
        },
    )
    return config, service, legacy


def parse_output(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def evaluate(work_dir: Path) -> dict[str, Any]:
    expected = load_json(EVAL_DIR / "expected.json")
    fixtures = load_fixtures()
    failures: list[str] = []
    fixture_ids = [item["id"] for item in fixtures]
    if len(fixture_ids) != len(set(fixture_ids)):
        failures.append("fixture id 不唯一")
    missing = sorted(set(expected["required_fixture_ids"]) - set(fixture_ids))
    if missing:
        failures.append("缺少 fixtures: " + ", ".join(missing))
    behavior = json.dumps(fixtures, ensure_ascii=False)
    for term in expected["required_behavior_terms"]:
        if term not in behavior:
            failures.append(f"expected behavior 缺少: {term}")
    for term in expected["forbidden_behavior_terms"]:
        if term in behavior:
            failures.append(f"expected behavior 残留旧契约: {term}")

    script_names = {path.name for path in SCRIPT_DIR.glob("pm_*.py")}
    missing_scripts = sorted(set(expected["required_scripts"]) - script_names)
    if missing_scripts:
        failures.append("缺少公共脚本: " + ", ".join(missing_scripts))
    unexpected_scripts = sorted(script_names - set(expected["required_scripts"]))
    if unexpected_scripts:
        failures.append("存在未声明公共脚本: " + ", ".join(unexpected_scripts))
    help_results: dict[str, int] = {}
    help_text = ""
    for script in expected["required_scripts"]:
        result = run_command([str(SCRIPT_DIR / script), "--help"])
        help_results[script] = result.returncode
        help_text += result.stdout
        if result.returncode != 0:
            failures.append(f"{script} --help 失败")
    for option in expected["forbidden_public_options"]:
        if option in help_text:
            failures.append(f"公共 CLI 暴露平台选项: {option}")

    workspace = work_dir / "workspace"
    config, service, legacy = create_validation_fixture(workspace)
    initialized = run_command(
        [str(SCRIPT_DIR / "pm_init.py"), "--workspace", str(workspace.resolve())]
    )
    initialized_value = parse_output(initialized)
    if initialized.returncode != 0 or not initialized_value.get("ok"):
        failures.append("current manager config 初始化失败")
    valid = run_command(
        [str(SCRIPT_DIR / "pm_validate.py"), "--config", str(config), "--service", str(service)]
    )
    valid_value = parse_output(valid)
    if valid.returncode != 0 or not valid_value.get("ok"):
        failures.append("current service schema 校验失败")
    rejected = run_command(
        [str(SCRIPT_DIR / "pm_validate.py"), "--config", str(config), "--service", str(legacy)]
    )
    rejected_value = parse_output(rejected)
    if rejected.returncode != 2 or rejected_value.get("error", {}).get("code") != "validation_error":
        failures.append("旧 service schema 未稳定拒绝")
    absent = run_command([str(SCRIPT_DIR / "pm_manager.py"), "status", "--config", str(config)])
    absent_value = parse_output(absent)
    absent_data = absent_value.get("data", {}) if isinstance(absent_value.get("data"), dict) else {}
    if (
        absent.returncode != 0
        or absent_value.get("ok") is not True
        or absent_data.get("state") != "absent"
        or absent_data.get("recommendedAction") != "ensure"
    ):
        failures.append("manager absent/recommendedAction 契约不稳定")

    template_types = {
        load_json(path).get("launcher", {}).get("type")
        for path in TEMPLATE_DIR.glob("service-*.json")
    }
    if template_types != set(expected["required_template_launchers"]):
        failures.append(f"template launcher 集合错误: {sorted(str(item) for item in template_types)}")
    manager_template = load_json(TEMPLATE_DIR / "manager-config.json")
    if set(manager_template) != {"workspaceRoot", "stateRoot", "control", "history", "limits", "logs"}:
        failures.append("manager template 顶层字段不是 current closed schema")
    if set(manager_template.get("history", {})) != {
        "maxInactive",
        "maxAgeSeconds",
        "maxTombstones",
        "deleteRunDirs",
    }:
        failures.append("manager template history 字段不是 current closed schema")
    if set(manager_template.get("limits", {})) != {
        "maxActiveRuns",
        "maxOpenSessions",
        "maxSessionRecords",
        "maxPendingPrunes",
        "maxConcurrentControlRequests",
        "maxRetainedBytes",
    }:
        failures.append("manager template limits 字段不是 current closed schema")
    forbidden_asset_keys = {"argv", "window", "platform", "backend", "portRetry"}
    asset_failures: list[str] = []
    for path in [*TEMPLATE_DIR.glob("*.json"), *EXAMPLE_DIR.glob("*.json")]:
        text = path.read_text(encoding="utf-8")
        value = load_json(path)
        if forbidden_asset_keys & set(value):
            asset_failures.append(path.relative_to(REPO_ROOT).as_posix())
        if '"argv"' in text or '"cmd-file"' in text or '"powershell-file"' in text:
            asset_failures.append(path.relative_to(REPO_ROOT).as_posix())
    if asset_failures:
        failures.append("模板或示例残留旧契约: " + ", ".join(sorted(set(asset_failures))))
    return {
        "ok": not failures,
        "fixture_count": len(fixtures),
        "help_results": help_results,
        "valid_schema": valid.returncode,
        "legacy_schema": rejected.returncode,
        "manager_init": initialized.returncode,
        "manager_absent": absent.returncode,
        "manager_recommended_action": absent_data.get("recommendedAction"),
        "template_launchers": sorted(template_types),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        result = evaluate(args.work_dir)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        result = {"ok": False, "failures": [f"评测输入或执行环境无效: {exc}"]}
    try:
        write_json(args.work_dir / "process-manager-evals.json", result)
    except OSError as exc:
        result["ok"] = False
        result.setdefault("failures", []).append(f"评测证据写入失败: {exc}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
