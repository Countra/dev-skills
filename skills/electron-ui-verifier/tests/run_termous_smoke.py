#!/usr/bin/env python3
"""通过统一 process-manager 和隔离 profile 验证 Termous 只读工作流。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from public_contract_support import ManagedVerifier, guarded_harness_path, write_json
from termous_contract_support import public_service_smoke, stale_session_smoke


def assert_port_free(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        try:
            handle.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"测试 CDP 端口已被占用：{port}") from exc


def read_endpoint(endpoint: str, timeout: float = 15.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{endpoint}/json/version", timeout=2) as response:
                value = json.loads(response.read().decode("utf-8"))
                if isinstance(value, dict):
                    return value
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(f"Termous CDP endpoint 未在时限内就绪：{last_error}")


def endpoint_closed(endpoint: str, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"{endpoint}/json/version", timeout=1).close()
        except (OSError, urllib.error.URLError):
            return True
        time.sleep(0.2)
    return False


def termous_service_file(
    managed: ManagedVerifier,
    exe: Path,
    profile: Path,
    endpoint: str,
    port: int,
) -> Path:
    service_file = (
        managed.workspace
        / ".harness"
        / "process-manager"
        / "services"
        / "termous-isolated-smoke.json"
    )
    write_json(
        service_file,
        {
            "name": "termous-isolated-smoke",
            "kind": "long-running",
            "cwd": str(managed.workspace),
            "launcher": {
                "type": "direct",
                "executable": str(exe),
                "args": [
                    f"--remote-debugging-port={port}",
                    "--remote-debugging-address=127.0.0.1",
                    "--no-first-run",
                    "--user-data-dir",
                ],
                "pathArgs": [str(profile)],
            },
            "environment": {
                "inherit": [
                    "PATH",
                    "HOME",
                    "USERPROFILE",
                    "SystemRoot",
                    "WINDIR",
                    "TEMP",
                    "TMP",
                    "LANG",
                ],
                "set": {},
                "fromEnv": [],
            },
            "stop": {"graceSeconds": 8},
            "readiness": {
                "type": "http",
                "url": f"{endpoint}/json/version",
                "timeoutSeconds": 45,
            },
            "logs": {"maxBytes": 10_485_760, "backups": 3},
        },
    )
    return service_file


def knowledge_counts(managed: ManagedVerifier) -> dict[str, int]:
    knowledge = managed.workspace / ".harness" / "electron-ui-verifier" / "knowledge"
    return {
        "objects": len(list((knowledge / "objects").glob("*.json"))),
        "decisions": len(list((knowledge / "decisions").glob("*.json"))),
    }


def validate_driver(driver: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    screenshots = driver.get("screenshots", {})
    if screenshots.get("successCount") != 10 or screenshots.get("qualityVerified") is not True:
        failures.append("Termous screenshot 未达到 10/10 quality verified")
    if float(screenshots.get("p95Ms", 999999)) > 2000:
        failures.append("Termous warm screenshot P95 超过 2 秒")
    if driver.get("attach", {}).get("connected") is not True:
        failures.append("Termous public attach 未通过")
    knowledge = driver.get("knowledge", {})
    if knowledge.get("decision") != "abstain" or knowledge.get("candidates"):
        failures.append("空 sealed knowledge 未明确 abstain")
    run = driver.get("run", {})
    if run.get("state") != "passed" or run.get("reportIdempotent") is not True or run.get("pending") is not None:
        failures.append("Termous 只读 run finalize/pending 未闭环")
    if driver.get("diagnostics", {}).get("independentArtifacts") != 3:
        failures.append("Termous console/exception/network 独立诊断证据不完整")
    strict_locator = driver.get("strictLocator", {})
    if (
        strict_locator.get("errorCode") != "ambiguous_locator"
        or strict_locator.get("candidateCount") != 2
        or strict_locator.get("stateUnchanged") is not True
        or strict_locator.get("pending") is not None
    ):
        failures.append("Termous strict locator 歧义零点击门禁未通过")
    navigation = driver.get("navigation", {})
    navigation_screenshots = navigation.get("screenshots", {})
    if (
        navigation.get("state") != "passed"
        or navigation.get("pending") is not None
        or navigation.get("viewsDiffer") is not True
        or navigation_screenshots.get("successCount") != 3
        or navigation_screenshots.get("distinctDigests") is not True
        or navigation_screenshots.get("qualityVerified") is not True
    ):
        failures.append("Termous 只读页面导航与视觉证据门禁未通过")
    return failures


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    exe = Path(args.exe).resolve()
    profile = guarded_harness_path(args.isolated_profile, "--isolated-profile")
    output = guarded_harness_path(args.output, "--output")
    run_root = guarded_harness_path(profile.parent / "termous-smoke", "Termous test root")
    if os.name != "nt" or exe.suffix.lower() != ".exe":
        raise RuntimeError("当前 Termous 实测只接受 Windows .exe")
    if not exe.is_file():
        raise RuntimeError(f"Termous.exe 不存在：{exe}")
    assert_port_free(args.port)
    if profile.exists():
        shutil.rmtree(profile)
    if run_root.exists():
        shutil.rmtree(run_root)
    profile.mkdir(parents=True)
    run_root.mkdir(parents=True)

    managed = ManagedVerifier(run_root / "verifier")
    endpoint = f"http://127.0.0.1:{args.port}"
    checks: dict[str, Any] = {}
    failures: list[str] = []
    termous_process_key: str | None = None
    termous_stopped = False
    try:
        checks["verifierStart"] = managed.start()
        checks["sessionRenew"] = managed.renew_session()
        service_file = termous_service_file(managed, exe, profile, endpoint, args.port)
        termous_start = managed.start_managed_service(service_file, timeout=60)
        checks["termousStart"] = termous_start
        termous_process_key = str(termous_start["processKey"])
        version = read_endpoint(endpoint)
        checks["cdpVersion"] = {
            "Browser": version.get("Browser"),
            "Protocol-Version": version.get("Protocol-Version"),
        }
        driver = public_service_smoke(managed, endpoint, run_root / "contract-data")
        checks["driver"] = driver
        failures.extend(validate_driver(driver))
    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
    finally:
        if termous_process_key:
            try:
                termous_stop = managed.stop_managed_service(termous_process_key)
                checks["termousStop"] = termous_stop
                termous_stopped = (
                    termous_stop.get("cleanupVerified") is True
                    and termous_stop.get("stopResult", {}).get("ownerEmpty") is True
                )
                if not termous_stopped:
                    failures.append("Termous process-manager owner 未清空")
            except Exception as exc:
                failures.append(f"Termous stop 失败：{exc}")
        checks["endpointClosed"] = endpoint_closed(endpoint)
        if not checks["endpointClosed"]:
            failures.append("Termous CDP endpoint 未关闭")
        if termous_stopped:
            try:
                post_exit = stale_session_smoke(managed)
                checks["postExit"] = post_exit
                if (
                    post_exit.get("sessionExisted") is True
                    and post_exit.get("staleAfterAppExit") is not True
                ) or post_exit.get("secondDetach") is not True:
                    failures.append("应用退出后的 stale session/repeat detach 未闭环")
            except Exception as exc:
                failures.append(f"post-exit stale 检查失败：{exc}")
        try:
            checks["knowledge"] = knowledge_counts(managed)
            if any(checks["knowledge"].values()):
                failures.append("Termous 只读 smoke 产生了 knowledge object/decision")
        except OSError as exc:
            failures.append(f"knowledge 写入边界复核失败：{exc}")
        verifier_cleanup, verifier_failures = managed.stop()
        checks["verifierCleanup"] = verifier_cleanup
        failures.extend(verifier_failures)
        try:
            if profile.exists():
                shutil.rmtree(profile)
            checks["isolatedProfileRemoved"] = not profile.exists()
        except OSError as exc:
            checks["isolatedProfileRemoved"] = False
            failures.append(f"隔离 Termous profile 清理失败：{exc}")

    cleanup = checks.get("verifierCleanup", {})
    session_close = cleanup.get("sessionClose", {})
    cleanup_ok = (
        termous_stopped
        and checks.get("endpointClosed") is True
        and checks.get("isolatedProfileRemoved") is True
        and session_close.get("cleanup", {}).get("cleanupVerified") is True
        and session_close.get("cleanup", {}).get("ownerEmpty") is True
        and session_close.get("idleStop", {}).get("cleanup", {}).get("ownersEmpty") is True
        and cleanup.get("installImmutable", {}).get("unchanged") is True
    )
    if not cleanup_ok:
        failures.append("Termous/verifier 统一 process-manager cleanup 未闭环")
    return {
        "ok": not failures,
        "application": {
            "name": "Termous",
            "executable": str(exe),
            "isolatedProfile": str(profile),
            "defaultProfileAccess": False,
        },
        "readOnly": True,
        "knowledgeWrite": False,
        "processOwnership": "process-manager",
        "checks": checks,
        "failures": failures,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--isolated-profile", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--port", type=int, default=19422)
    parser.add_argument("--no-learn", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.no_learn:
        raise SystemExit("必须提供 --no-learn")
    output = guarded_harness_path(args.output, "--output")
    try:
        result = run_smoke(args)
    except Exception as exc:
        result = {"ok": False, "failures": [f"{type(exc).__name__}: {exc}"]}
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
