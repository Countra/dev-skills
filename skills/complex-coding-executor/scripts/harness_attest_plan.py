#!/usr/bin/env python3
"""为 execution-plan.md 生成或校验 SHA-256 证明。"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from harness_task_resolver import ResolverError, resolve_task


ATTESTATION_NAME = "attestation.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def attestation_path(task_dir: Path) -> Path:
    return task_dir / ATTESTATION_NAME


def write_attestation(path: Path, payload: dict[str, object]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"failed to write attestation: {path}: {exc}") from exc


def load_attestation(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("attestation root must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="生成或校验 plan attestation")
    parser.add_argument("--workspace", default=".", help="workspace 根目录")
    parser.add_argument("--task-dir", help="任务目录；省略时读取 active-task.json")
    parser.add_argument("--write", action="store_true", help="写入 attestation.json")
    parser.add_argument("--check", action="store_true", help="校验已有 attestation.json")
    args = parser.parse_args()

    try:
        resolved = resolve_task(args.workspace, args.task_dir)
    except ResolverError as exc:
        print(f"FAIL: {exc}")
        return 1

    digest = sha256_file(resolved.plan_path)
    path = attestation_path(resolved.task_dir)

    if args.check:
        if not path.is_file():
            print(f"FAIL: attestation not found: {path}")
            return 1
        try:
            payload = load_attestation(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"FAIL: invalid attestation: {exc}")
            return 1
        if payload.get("sha256") != digest:
            print("FAIL: plan hash does not match attestation")
            return 1
        print("PASS: attestation matches current plan")
        return 0

    payload = {
        "schema_version": 1,
        "task_id": resolved.active.get("task_id"),
        "plan_path": str(resolved.plan_path),
        "sha256": digest,
        "size_bytes": resolved.plan_path.stat().st_size,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    if args.write:
        write_attestation(path, payload)
        print(f"PASS: wrote attestation: {path}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
