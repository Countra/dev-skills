#!/usr/bin/env python3
"""执行两个目标 skill 的静态、schema 与旧契约检查。"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
GITLAB_ROOT = REPO_ROOT / "skills" / "gitlab-pat-ops"
PROCESS_ROOT = REPO_ROOT / "skills" / "process-manager"
PROCESS_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "process-manager-platforms.yml"


def source_files(root: Path, suffix: str) -> list[Path]:
    return sorted(path for path in root.rglob(f"*{suffix}") if "__pycache__" not in path.parts)


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def parse_python(paths: list[Path], failures: list[str]) -> int:
    count = 0
    for path in paths:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            count += 1
        except (OSError, UnicodeError, SyntaxError) as exc:
            failures.append(f"Python parse 失败 {relative(path)}: {exc}")
    return count


def parse_json_assets(failures: list[str]) -> int:
    count = 0
    roots = (GITLAB_ROOT, PROCESS_ROOT, REPO_ROOT / "evals" / "gitlab-pat-ops", REPO_ROOT / "evals" / "process-manager")
    for root in roots:
        if not root.exists():
            continue
        for path in source_files(root, ".json"):
            try:
                json.loads(path.read_text(encoding="utf-8"))
                count += 1
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                failures.append(f"JSON parse 失败 {relative(path)}: {exc}")
        for path in source_files(root, ".jsonl"):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError) as exc:
                failures.append(f"JSONL 读取失败 {relative(path)}: {exc}")
                continue
            for line_number, line in enumerate(lines, 1):
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                    count += 1
                except json.JSONDecodeError as exc:
                    failures.append(f"JSONL parse 失败 {relative(path)}:{line_number}: {exc}")
    return count


def check_line_budgets(failures: list[str]) -> dict[str, int]:
    observed: dict[str, int] = {}
    roots = [GITLAB_ROOT / "scripts"]
    if (PROCESS_ROOT / "scripts" / "process_manager").is_dir():
        roots.append(PROCESS_ROOT / "scripts")
    for root in roots:
        if not root.exists():
            continue
        for path in source_files(root, ".py"):
            try:
                lines = len(path.read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeError) as exc:
                failures.append(f"行数检查读取失败 {relative(path)}: {exc}")
                continue
            observed[relative(path)] = lines
            if lines > 500:
                failures.append(f"生产 Python 文件超过 500 行: {relative(path)}={lines}")
    return observed


def check_gitlab_contract(failures: list[str]) -> dict[str, Any]:
    current_files = [GITLAB_ROOT / "SKILL.md", *source_files(GITLAB_ROOT / "references", ".md"), *source_files(GITLAB_ROOT / "scripts", ".py")]
    forbidden = ("SKILL_GITLAB_TOKEN", "TOKEN_ENVS", "gitlab_common", '"version": 1', "version: 1")
    for path in current_files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            failures.append(f"GitLab contract 读取失败 {relative(path)}: {exc}")
            continue
        for token in forbidden:
            if token in text:
                failures.append(f"GitLab current contract 残留 {token}: {relative(path)}")
    scripts_dir = GITLAB_ROOT / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        from gitlab_ops.registry import CAPABILITIES  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        failures.append(f"能力注册表导入失败: {exc}")
        return {"capability_count": 0}
    ids = [item.capability_id for item in CAPABILITIES]
    if len(ids) != len(set(ids)):
        failures.append("能力注册表 capability_id 不唯一")
    missing_scripts = sorted({item.script for item in CAPABILITIES if not (scripts_dir / item.script).is_file()})
    if missing_scripts:
        failures.append("能力注册表引用不存在脚本: " + ", ".join(missing_scripts))
    return {"capability_count": len(CAPABILITIES), "missing_scripts": missing_scripts}


def check_process_contract(failures: list[str]) -> dict[str, Any]:
    package = PROCESS_ROOT / "scripts" / "process_manager"
    if not package.is_dir():
        return {"package_present": False}
    forbidden = (
        "taskkill /F",
        "shell=True",
        "minimumGuarantee",
        "cmd-file",
        "powershell-file",
        "posix-file",
        "start_manager.ps1",
        "stop_manager.ps1",
        "portRetry",
        "maxSwitches",
    )
    for path in source_files(PROCESS_ROOT / "scripts", ".py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            failures.append(f"process-manager contract 读取失败 {relative(path)}: {exc}")
            continue
        for token in forbidden:
            if token in text:
                failures.append(f"process-manager current source 残留 {token}: {relative(path)}")
        if "sys.platform" in text and "platforms" not in path.parts:
            failures.append(f"公共 runtime 散落 sys.platform: {relative(path)}")
    current_docs = [
        PROCESS_ROOT / "SKILL.md",
        *source_files(PROCESS_ROOT / "references", ".md"),
        PROCESS_ROOT / "agents" / "openai.yaml",
    ]
    doc_forbidden = (
        "Support Windows only",
        "Windows only in this version",
        "start_manager.ps1",
        "stop_manager.ps1",
        "default port is 18080",
        "maxSwitches",
        "cmd-file",
        "powershell-file",
    )
    for path in current_docs:
        if not path.is_file():
            failures.append(f"process-manager 必需文档缺失: {relative(path)}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            failures.append(f"process-manager 文档读取失败 {relative(path)}: {exc}")
            continue
        for token in doc_forbidden:
            if token in text:
                failures.append(f"process-manager current docs 残留 {token}: {relative(path)}")

    required_references = {"workflow.md", "service-schema.md", "platform-backends.md", "security.md"}
    observed_references = {path.name for path in (PROCESS_ROOT / "references").glob("*.md")}
    missing_references = sorted(required_references - observed_references)
    if missing_references:
        failures.append("process-manager references 缺失: " + ", ".join(missing_references))
    required_scripts = {
        "pm_manager.py",
        "pm_init.py",
        "pm_health.py",
        "pm_validate.py",
        "pm_start.py",
        "pm_ready.py",
        "pm_status.py",
        "pm_logs.py",
        "pm_list.py",
        "pm_prune.py",
        "pm_stop.py",
        "pm_restart.py",
        "pm_doctor.py",
        "pm_shutdown.py",
    }
    observed_scripts = {path.name for path in (PROCESS_ROOT / "scripts").glob("pm_*.py")}
    missing_scripts = sorted(required_scripts - observed_scripts)
    if missing_scripts:
        failures.append("process-manager 公共脚本缺失: " + ", ".join(missing_scripts))
    for path in (PROCESS_ROOT / "scripts").glob("pm_*.py"):
        text = path.read_text(encoding="utf-8")
        for option in ("--platform", "--backend", "--systemd", "--launchd", "--job-object"):
            if option in text:
                failures.append(f"公共 CLI 暴露平台选项 {option}: {relative(path)}")

    template_names = {path.name for path in (PROCESS_ROOT / "templates").glob("*.json")}
    expected_templates = {"manager-config.json", "service-direct.json", "service-script.json"}
    if template_names != expected_templates:
        failures.append("process-manager template 集合错误: " + ", ".join(sorted(template_names)))
    asset_paths = [
        *(PROCESS_ROOT / "templates").glob("*.json"),
        *(REPO_ROOT / "examples" / "process-manager").glob("*.json"),
    ]
    asset_failures: list[str] = []
    launcher_types: set[str] = set()
    for path in asset_paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            failures.append(f"process-manager asset 无效 {relative(path)}: {exc}")
            continue
        if not isinstance(value, dict):
            asset_failures.append(relative(path))
            continue
        if {"argv", "window", "platform", "backend", "portRetry"} & set(value):
            asset_failures.append(relative(path))
        launcher = value.get("launcher")
        if isinstance(launcher, dict):
            launcher_type = launcher.get("type")
            if launcher_type not in {"direct", "script"}:
                asset_failures.append(relative(path))
            else:
                launcher_types.add(str(launcher_type))
            if "argv" in launcher:
                asset_failures.append(relative(path))
    if asset_failures:
        failures.append("process-manager asset 残留旧 schema: " + ", ".join(sorted(set(asset_failures))))
    return {
        "package_present": True,
        "public_script_count": len(observed_scripts),
        "reference_count": len(observed_references),
        "template_count": len(template_names),
        "asset_launcher_types": sorted(launcher_types),
    }


def check_process_workflow(failures: list[str]) -> dict[str, Any]:
    if not PROCESS_WORKFLOW.is_file():
        failures.append("process-manager 三平台 workflow 缺失")
        return {"present": False}
    try:
        text = PROCESS_WORKFLOW.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        failures.append(f"process-manager workflow 读取失败: {exc}")
        return {"present": True, "readable": False}
    required = (
        "windows-latest",
        "ubuntu-latest",
        "macos-latest",
        "run_platform_smoke.py",
        "run_evals.py",
        "run_static_checks.py",
        "actions/upload-artifact@v4",
        "Delegate=yes",
        "systemd-run",
        "if: always()",
    )
    missing = [token for token in required if token not in text]
    if missing:
        failures.append("process-manager workflow 能力缺失: " + ", ".join(missing))
    lines = [line.strip() for line in text.splitlines()]
    try:
        push_index = lines.index("push:")
    except ValueError:
        all_branch_push = False
    else:
        all_branch_push = lines[push_index + 1 : push_index + 3] == ["branches:", '- "**"']
    if not all_branch_push:
        failures.append("process-manager workflow 必须对所有分支 push 执行")
    forbidden = (
        "secrets.",
        "continue-on-error",
        "rm -rf",
        "taskkill",
        "TerminateProcess",
        "path: .ci-artifacts/",
    )
    present_forbidden = [token for token in forbidden if token in text]
    if present_forbidden:
        failures.append("process-manager workflow 包含禁止行为: " + ", ".join(present_forbidden))
    return {
        "present": True,
        "required_tokens": len(required),
        "missing": missing,
        "forbidden": present_forbidden,
        "all_branch_push": all_branch_push,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    failures: list[str] = []
    python_paths = source_files(GITLAB_ROOT, ".py") + source_files(PROCESS_ROOT, ".py")
    result = {
        "python_files": parse_python(python_paths, failures),
        "json_values": parse_json_assets(failures),
        "line_budgets": check_line_budgets(failures),
        "gitlab": check_gitlab_contract(failures),
        "process_manager": check_process_contract(failures),
        "process_manager_workflow": check_process_workflow(failures),
        "failures": failures,
    }
    result["ok"] = not failures
    output = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
