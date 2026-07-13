"""实验运行目录、case 工作区和本地 Git 基线。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import ExecutionError, SuiteError
from .security import build_child_env
from .snapshots import create_snapshot


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


@dataclass(frozen=True)
class RunLayout:
    """一次实验拥有的全部可写目录。"""

    root: Path
    snapshots: Path
    cases: Path
    artifacts: Path


@dataclass(frozen=True)
class CaseWorkspace:
    """单次 agent run 的隔离工作区。"""

    root: Path
    outputs: Path
    baseline_commit: str
    agent_skill: Path | None = None


def resolve_within(root: Path, raw: str, *, must_exist: bool = False) -> Path:
    """解析工作区相对路径，拒绝绝对路径、父级跳转和解析后逃逸。"""
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise SuiteError(f"不安全的工作区路径：{raw}", path="$.cases")
    root = root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SuiteError(f"工作区路径逃逸：{raw}", path="$.cases") from exc
    if must_exist and not resolved.exists():
        raise SuiteError(f"工作区路径不存在：{raw}", path="$.cases")
    return resolved


def create_run_layout(work_root: Path, suite_id: str, fingerprint: str, *, run_id: str | None = None) -> RunLayout:
    """创建带唯一标识的运行目录，禁止复用已有目录。"""
    safe_suite = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in suite_id)
    identifier = run_id or f"{fingerprint[:12]}-{uuid.uuid4().hex[:12]}"
    if not RUN_ID_PATTERN.fullmatch(identifier):
        raise SuiteError("run_id 只能使用字母、数字、点、下划线和连字符", path="$.run_id")
    root = work_root.resolve() / safe_suite / identifier
    try:
        root.mkdir(parents=True, exist_ok=False)
        snapshots = root / "snapshots"
        cases = root / "cases"
        artifacts = root / "artifacts"
        for path in (snapshots, cases, artifacts):
            path.mkdir()
    except OSError as exc:
        raise ExecutionError(f"无法创建运行目录 {root}：{exc}") from exc
    return RunLayout(root=root, snapshots=snapshots, cases=cases, artifacts=artifacts)


def _reject_links(root: Path) -> None:
    for current, dir_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in [*dir_names, *file_names]:
            path = current_path / name
            is_junction = getattr(path, "is_junction", None)
            if path.is_symlink() or bool(is_junction and is_junction()):
                raise SuiteError(f"输入包含链接或 junction：{path.relative_to(root)}", path="$.cases.inputs")


def _reject_oracle_input(raw: str) -> None:
    """阻止常见 grader-only 路径被声明为 agent 输入。"""
    markers = {"oracle", ".oracle", "grader", "rubric", "expected", "expected-output"}
    parts = [part.lower() for part in Path(raw).parts]
    stems = [Path(part).stem.lower() for part in Path(raw).parts]
    if any(part in markers for part in [*parts, *stems]):
        raise SuiteError(f"grader-only 输入不得复制到 agent workspace：{raw}", path="$.cases.inputs")


def copy_case_inputs(suite_root: Path, inputs: list[str], workspace: Path) -> None:
    """按 suite 相对位置复制输入，不允许覆盖或通过链接穿透边界。"""
    for raw in inputs:
        _reject_oracle_input(raw)
        unresolved = suite_root.resolve() / Path(raw)
        is_junction = getattr(unresolved, "is_junction", None)
        if unresolved.is_symlink() or bool(is_junction and is_junction()):
            raise SuiteError(f"输入不能是链接或 junction：{raw}", path="$.cases.inputs")
        source = resolve_within(suite_root, raw, must_exist=True)
        target = resolve_within(workspace, raw)
        if target.exists():
            raise ExecutionError(f"多个输入发生目标冲突：{raw}")
        if source.is_dir():
            _reject_links(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _git(workspace: Path, *args: str) -> str:
    environment = build_child_env(
        extra={
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=workspace,
            env=environment,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExecutionError(f"Git 基线命令失败：{exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ExecutionError(f"Git {' '.join(args)} 失败：{detail}")
    return completed.stdout.strip()


def initialize_git_baseline(workspace: Path) -> str:
    """创建只用于差异测量的本地仓库和初始提交。"""
    _git(workspace, "init", "--quiet")
    _git(workspace, "config", "user.name", "Skill Evaluation Lab")
    _git(workspace, "config", "user.email", "skill-evaluation-lab@localhost")
    _git(workspace, "add", "--all")
    _git(workspace, "commit", "--quiet", "--allow-empty", "-m", "evaluation baseline")
    return _git(workspace, "rev-parse", "HEAD")


def create_case_workspace(
    layout: RunLayout,
    *,
    case_id: str,
    variant: str,
    repetition: int,
    suite_root: Path,
    inputs: list[str],
    agent_skill: Path | None = None,
    agent_skill_name: str | None = None,
) -> CaseWorkspace:
    """创建 case 工作区、复制输入并冻结 Git 差异基线。"""
    relative = f"{case_id}/{variant}-{repetition}"
    root = resolve_within(layout.cases, relative)
    try:
        root.mkdir(parents=True, exist_ok=False)
        copy_case_inputs(suite_root, inputs, root)
        visible_skill: Path | None = None
        if agent_skill is not None:
            if not agent_skill_name or not RUN_ID_PATTERN.fullmatch(agent_skill_name):
                raise SuiteError("agent_skill_name 无效", path="$.skill_path")
            visible_skill = root / ".agents" / "skills" / agent_skill_name
            create_snapshot(agent_skill, visible_skill)
        outputs = root / "outputs"
        outputs.mkdir()
        baseline = initialize_git_baseline(root)
    except (OSError, shutil.Error) as exc:
        raise ExecutionError(f"创建 case 工作区失败：{exc}") from exc
    return CaseWorkspace(root=root, outputs=outputs, baseline_commit=baseline, agent_skill=visible_skill)
