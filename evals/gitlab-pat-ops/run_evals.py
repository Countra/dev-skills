#!/usr/bin/env python3
"""执行 gitlab-pat-ops fixtures 与命令契约检查。"""

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
SCRIPT_DIR = REPO_ROOT / "skills" / "gitlab-pat-ops" / "scripts"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_fixtures() -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate((EVAL_DIR / "prompts.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or not isinstance(value.get("id"), str):
            raise ValueError(f"prompts.jsonl:{line_number} fixture 无效")
        values.append(value)
    return values


def run_command(arguments: list[str], *, clean_gitlab_env: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if clean_gitlab_env:
        for key in list(env):
            if key.startswith("SKILL_GITLAB_") or key == "GITLAB_TOKEN":
                env.pop(key, None)
    command = [sys.executable, "-X", "utf8", "-B", *arguments]
    try:
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124, "", "命令执行超时")


def evaluate() -> dict[str, Any]:
    expected = load_json(EVAL_DIR / "expected.json")
    fixtures = load_fixtures()
    ids = [item["id"] for item in fixtures]
    failures: list[str] = []
    if len(ids) != len(set(ids)):
        failures.append("fixture id 不唯一")
    missing = sorted(set(expected["required_fixture_ids"]) - set(ids))
    if missing:
        failures.append("缺少 fixtures: " + ", ".join(missing))
    behavior_text = json.dumps(fixtures, ensure_ascii=False)
    for term in expected["required_behavior_terms"]:
        if term not in behavior_text:
            failures.append(f"expected behavior 缺少: {term}")
    for term in expected["forbidden_behavior_terms"]:
        if term in behavior_text:
            failures.append(f"expected behavior 残留旧契约: {term}")

    capabilities = run_command([str(SCRIPT_DIR / "gl_capabilities.py"), "--all"])
    try:
        capability_value = json.loads(capabilities.stdout)
    except json.JSONDecodeError:
        capability_value = {}
    if capabilities.returncode != 0 or not capability_value.get("ok"):
        failures.append("gl_capabilities.py --mode write 执行失败")
    else:
        registered = {
            item.get("capability_id")
            for item in capability_value.get("data", {}).get("capabilities", [])
            if isinstance(item, dict)
        }
        missing_capabilities = sorted(set(expected["required_capability_ids"]) - registered)
        if missing_capabilities:
            failures.append("能力注册表缺少: " + ", ".join(missing_capabilities))

    prohibited = run_command(
        [str(SCRIPT_DIR / "gl_capabilities.py"), "--capability", "merge_requests.merge"]
    )
    try:
        prohibited_value = json.loads(prohibited.stdout)
    except json.JSONDecodeError:
        prohibited_value = {}
    if (
        prohibited.returncode != 8
        or prohibited_value.get("error", {}).get("code") != "unsupported_capability"
    ):
        failures.append("禁止能力未返回稳定 unsupported_capability")

    doctor = run_command([str(SCRIPT_DIR / "gl_doctor.py"), "--offline-check"], clean_gitlab_env=True)
    try:
        doctor_value = json.loads(doctor.stdout)
    except json.JSONDecodeError:
        doctor_value = {}
    if doctor.returncode != 2 or doctor_value.get("required") != ["SKILL_GITLAB_BASE_URL", "SKILL_GITLAB_PAT"]:
        failures.append("doctor 缺失环境契约不正确")

    scripts = sorted(path for path in SCRIPT_DIR.glob("gl_*.py") if path.name != "gl_capabilities.py")
    script_names = {path.name for path in scripts}
    missing_scripts = sorted(set(expected["required_scripts"]) - script_names)
    if missing_scripts:
        failures.append("缺少资源脚本: " + ", ".join(missing_scripts))
    if (SCRIPT_DIR / "gl_issue_templates.py").exists():
        failures.append("旧 gl_issue_templates.py 仍存在")
    help_results: dict[str, int] = {}
    for script in scripts:
        result = run_command([str(script), "--help"], clean_gitlab_env=True)
        help_results[script.name] = result.returncode
        if result.returncode != 0:
            failures.append(f"{script.name} --help 失败")
    return {
        "ok": not failures,
        "fixture_count": len(fixtures),
        "capability_query": capabilities.returncode,
        "prohibited_query": prohibited.returncode,
        "doctor_missing_env": doctor.returncode,
        "help_results": help_results,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = evaluate()
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        result = {"ok": False, "failures": [f"评测输入或执行环境无效: {exc}"]}
    try:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        (args.work_dir / "gitlab-evals.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        result["ok"] = False
        result.setdefault("failures", []).append(f"评测证据写入失败: {exc}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
