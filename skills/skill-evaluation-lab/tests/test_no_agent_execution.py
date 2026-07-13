"""生产代码零派生 Agent、进程与网络能力架构测试。"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from _helpers import SKILL_ROOT


BANNED_IMPORT_ROOTS = {
    "subprocess",
    "socket",
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "openai",
    "anthropic",
    "agents",
}
BANNED_CALLS = {
    "__import__",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "compile",
    "eval",
    "exec",
    "importlib.import_module",
    "multiprocessing.Process",
    "os.popen",
    "os.startfile",
    "os.system",
    "shutil.which",
    "webbrowser.open",
}
BANNED_CALL_PREFIXES = ("os.exec", "os.spawn")
ALLOWED_IMPORT_ROOTS = {
    "__future__",
    "argparse",
    "ast",
    "collections",
    "dataclasses",
    "datetime",
    "hashlib",
    "json",
    "os",
    "pathlib",
    "re",
    "shutil",
    "skill_evaluation_lab",
    "sys",
    "typing",
}
BANNED_ARGUMENT_PARTS = {"--live", "--model", "--runner", "--authorize"}


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


class NoAgentExecutionTests(unittest.TestCase):
    def test_production_python_has_no_process_network_or_agent_runtime(self) -> None:
        violations: list[str] = []
        scripts_root = SKILL_ROOT / "scripts"
        for path in sorted(scripts_root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".", 1)[0]
                        if root in BANNED_IMPORT_ROOTS or root not in ALLOWED_IMPORT_ROOTS:
                            violations.append(f"{path.name}:{node.lineno}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    root = (node.module or "").split(".", 1)[0]
                    if (
                        node.level == 0
                        and root
                        and (root in BANNED_IMPORT_ROOTS or root not in ALLOWED_IMPORT_ROOTS)
                    ):
                        violations.append(f"{path.name}:{node.lineno}: from {node.module}")
                if isinstance(node, ast.Call):
                    call = dotted_name(node.func)
                    if call in BANNED_CALLS or call.startswith(BANNED_CALL_PREFIXES):
                        violations.append(f"{path.name}:{node.lineno}: {call}")
        self.assertEqual(violations, [])

    def test_public_cli_does_not_expose_runtime_authorization_flags(self) -> None:
        violations: list[str] = []
        for path in sorted((SKILL_ROOT / "scripts").glob("se_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or dotted_name(node.func).split(".")[-1] != "add_argument":
                    continue
                for argument in node.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        if any(part in argument.value.lower() for part in BANNED_ARGUMENT_PARTS):
                            violations.append(f"{path.name}:{node.lineno}: {argument.value}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
