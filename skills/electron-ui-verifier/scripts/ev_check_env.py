#!/usr/bin/env python3
"""检查 electron-ui-verifier 目标 Python 环境是否满足运行要求。"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import importlib.metadata as importlib_metadata
except Exception:  # pragma: no cover - 兼容过旧 Python 的报错输出
    importlib_metadata = None  # type: ignore[assignment]


MIN_PYTHON = (3, 10)
IMPORT_MODULES = {
    "playwright": ["playwright", "playwright.sync_api"],
}


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_requirements() -> Path:
    return skill_root() / "requirements.txt"


def version_text() -> str:
    return ".".join(str(part) for part in sys.version_info[:3])


def parse_version(value: str) -> tuple[int, ...]:
    parts = [int(item) for item in re.findall(r"\d+", value)]
    return tuple(parts) if parts else (0,)


def compare_versions(left: str, operator: str, right: str) -> bool:
    left_parts = parse_version(left)
    right_parts = parse_version(right)
    length = max(len(left_parts), len(right_parts))
    left_parts = left_parts + (0,) * (length - len(left_parts))
    right_parts = right_parts + (0,) * (length - len(right_parts))
    if operator == ">=":
        return left_parts >= right_parts
    if operator == ">":
        return left_parts > right_parts
    if operator == "==":
        return left_parts == right_parts
    if operator == "<=":
        return left_parts <= right_parts
    if operator == "<":
        return left_parts < right_parts
    return True


def parse_requirement(line: str) -> Optional[dict[str, str]]:
    clean = line.split("#", 1)[0].strip()
    if not clean or clean.startswith(("-", "--")):
        return None
    clean = clean.split(";", 1)[0].strip()
    match = re.match(r"^([A-Za-z0-9_.-]+)\s*([<>=!~].*)?$", clean)
    if not match:
        return {"raw": clean, "name": clean, "specifier": ""}
    return {"raw": clean, "name": match.group(1), "specifier": (match.group(2) or "").strip()}


def read_requirements(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"requirements file does not exist: {path}")
    requirements: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        item = parse_requirement(line)
        if item:
            requirements.append(item)
    return requirements


def distribution_version(name: str) -> str:
    if importlib_metadata is None:
        raise RuntimeError("当前 Python 缺少 importlib.metadata，无法检查已安装包")
    return importlib_metadata.version(name)  # type: ignore[union-attr]


def specifiers(specifier: str) -> list[tuple[str, str]]:
    checks: list[tuple[str, str]] = []
    for part in specifier.split(","):
        clean = part.strip()
        if not clean:
            continue
        match = re.match(r"^(>=|<=|==|>|<)\s*([A-Za-z0-9_.!*+-]+)$", clean)
        if match:
            checks.append((match.group(1), match.group(2).replace(".*", "")))
    return checks


def import_targets(package_name: str) -> list[str]:
    normalized = package_name.lower().replace("_", "-")
    if normalized in IMPORT_MODULES:
        return IMPORT_MODULES[normalized]
    return [package_name.replace("-", "_")]


def check_requirement(item: dict[str, str]) -> dict[str, Any]:
    raw = item["raw"]
    name = item["name"]
    result: dict[str, Any] = {"requirement": raw, "package": name, "ok": True}
    try:
        installed = distribution_version(name)
        result["installedVersion"] = installed
    except Exception as exc:
        return {
            "requirement": raw,
            "package": name,
            "ok": False,
            "reason": f"未安装 Python 包：{name}",
            "detail": str(exc),
        }

    failed_specs = []
    for operator, expected in specifiers(item.get("specifier", "")):
        if not compare_versions(installed, operator, expected):
            failed_specs.append(f"{operator}{expected}")
    if failed_specs:
        return {
            "requirement": raw,
            "package": name,
            "installedVersion": installed,
            "ok": False,
            "reason": f"版本不满足要求：已安装 {installed}，需要 {', '.join(failed_specs)}",
        }

    missing_imports = []
    for module_name in import_targets(name):
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            missing_imports.append({"module": module_name, "error": str(exc)})
    if missing_imports:
        return {
            "requirement": raw,
            "package": name,
            "installedVersion": installed,
            "ok": False,
            "reason": "包已安装但无法导入运行模块",
            "missingImports": missing_imports,
        }

    result["imports"] = import_targets(name)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查 electron-ui-verifier 的 Python 依赖环境。")
    parser.add_argument("--requirements", help="requirements.txt 绝对路径；未指定时使用 skill 内置文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    return parser


def run_check(requirements_file: Path) -> dict[str, Any]:
    python_ok = sys.version_info[:2] >= MIN_PYTHON
    requirements = read_requirements(requirements_file)
    results = [check_requirement(item) for item in requirements]
    failures = [item for item in results if not item.get("ok")]
    python_failure = None
    if not python_ok:
        python_failure = {
            "required": f">={MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
            "actual": version_text(),
            "reason": "当前 Python 版本过低，无法稳定运行 verifier server",
        }
    ok = python_failure is None and not failures
    return {
        "ok": ok,
        "code": "ok" if ok else "dependency_check_failed",
        "python": sys.executable,
        "pythonVersion": version_text(),
        "requirements": str(requirements_file),
        "pythonFailure": python_failure,
        "packages": results,
        "missing": failures,
        "installCommand": f'"{sys.executable}" -m pip install -r "{requirements_file}"',
    }


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    requirements_file = Path(args.requirements).resolve() if args.requirements else default_requirements()
    try:
        result = run_check(requirements_file)
    except Exception as exc:
        result = {
            "ok": False,
            "code": "dependency_check_failed",
            "python": sys.executable,
            "pythonVersion": version_text(),
            "requirements": str(requirements_file),
            "error": str(exc),
            "missing": [],
            "installCommand": f'"{sys.executable}" -m pip install -r "{requirements_file}"',
        }
    if args.json:
        print_json(result)
    else:
        if result.get("ok"):
            print(f"OK: {result['python']} ({result['pythonVersion']})")
        else:
            print(f"FAILED: {result.get('error') or result.get('code')}")
            print(f"Install: {result['installCommand']}")
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
