#!/usr/bin/env python3
"""使用隔离 profile 和公共 HTTP/CLI 对 Termous 执行只读验收。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills" / "electron-ui-verifier" / "scripts"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def python_has_playwright(path: Path) -> bool:
    completed = subprocess.run(
        [str(path), "-X", "utf8", "-B", "-c", "import playwright.async_api"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return completed.returncode == 0


def driver_python(work_dir: Path) -> Path:
    explicit = os.environ.get("EV_SERVICE_PYTHON")
    candidates = [Path(explicit)] if explicit else []
    candidates.append(Path(sys.executable))
    executable = "python.exe" if os.name == "nt" else "python"
    folder = "Scripts" if os.name == "nt" else "bin"
    candidates.append(work_dir.parent / "fresh-env" / folder / executable)
    for candidate in candidates:
        if candidate.is_absolute() and candidate.exists() and python_has_playwright(candidate):
            return candidate
    raise RuntimeError("未找到安装 locked Playwright 的 verifier Python")


def assert_port_free(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        try:
            handle.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"测试 CDP 端口已被占用：{port}") from exc


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def existing_termous_pids() -> list[int]:
    if os.name != "nt":
        return []
    completed = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Termous.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"无法检查现有 Termous 进程：{completed.stderr.strip()}")
    result = []
    for row in csv.reader(io.StringIO(completed.stdout)):
        if len(row) >= 2 and row[0].lower() == "termous.exe":
            try:
                result.append(int(row[1].replace(",", "")))
            except ValueError:
                continue
    return result


def wait_endpoint(endpoint: str, timeout: float = 45.0) -> dict[str, Any]:
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


def stop_process_tree(process: subprocess.Popen[Any], owned_pids: list[int]) -> dict[str, Any]:
    requested = []
    return_codes = []
    if os.name == "nt":
        for pid in dict.fromkeys([process.pid, *owned_pids]):
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            requested.append(pid)
            return_codes.append(completed.returncode)
    elif process.poll() is None:
        import signal

        os.killpg(process.pid, signal.SIGTERM)
        requested.append(process.pid)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    return {
        "rootExited": process.poll() is not None,
        "treeStopRequested": bool(requested),
        "stopReturnCodes": return_codes,
        "ownedPids": requested,
        "exitCode": process.returncode,
    }


def runtime_config(work_dir: Path) -> Path:
    state = work_dir / "runtime"
    config = state / "config.json"
    if config.exists():
        return config
    state.mkdir(parents=True, exist_ok=True)
    token = state / "token"
    token.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
    write_json(state / "sessions.json", {"schemaVersion": 1, "sessions": []})
    write_json(
        config,
        {
            "host": "127.0.0.1",
            "port": free_port(),
            "portRetry": {"enabled": False, "maxSwitches": 0},
            "workspaceRoot": str(work_dir),
            "stateRoot": str(state),
            "tokenFile": str(token),
            "serverFile": str(state / "server.json"),
            "sessionsFile": str(state / "sessions.json"),
            "reportsDir": str(state / "reports"),
            "pendingDir": str(state / "pending"),
            "workflowsDir": str(state / "workflows"),
            "artifactsDir": str(state / "artifacts"),
            "logsDir": str(state / "logs"),
            "tmpDir": str(state / "tmp"),
            "runsDir": str(state / "runs"),
        },
    )
    return config


def run_cli(config: Path, script: str, arguments: list[str], expected: tuple[int, ...] = (0,), timeout: int = 60) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", str(SCRIPTS / script), "--config", str(config), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{script} 未返回 JSON：rc={completed.returncode} stdout={completed.stdout[:500]} stderr={completed.stderr[:500]}"
        ) from exc
    if completed.returncode not in expected:
        raise RuntimeError(f"{script} 返回码异常：rc={completed.returncode} result={value}")
    return value


def start_service(config_path: Path):
    sys.path.insert(0, str(SCRIPTS))
    from electron_verifier.config import ServiceConfig
    from electron_verifier.service import VerifierApplication, _bind_server

    config = ServiceConfig.load(config_path)
    application = VerifierApplication(config)
    application.start()
    try:
        server = _bind_server(config, application)
    except Exception:
        application.stop()
        raise
    thread = threading.Thread(target=server.serve_forever, name="termous-verifier-http", daemon=False)
    thread.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{application.actual_port}/health", timeout=1).close()
            return application, server, thread
        except (OSError, urllib.error.URLError):
            time.sleep(0.05)
    server.shutdown()
    server.server_close()
    application.stop()
    thread.join(timeout=5)
    raise RuntimeError("临时 verifier HTTP service 未就绪")


def stop_service(application: Any, server: Any, thread: threading.Thread) -> dict[str, Any]:
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)
    application.stop()
    return {"httpThreadAlive": thread.is_alive(), **application.worker.stats()}


def strict_locator_smoke(config: Path) -> dict[str, Any]:
    prepared = run_cli(config, "ev_prepare.py", ["--session", "termous"])
    run_id = str(prepared["runId"])
    before_action = {"id": "strict-before", "type": "snapshot", "options": {"timeoutMs": 10000}}
    before = run_cli(
        config,
        "ev_action.py",
        ["--run-id", run_id, "--action", json.dumps(before_action, ensure_ascii=False)],
    )
    ambiguous_action = {
        "id": "ambiguous-connect",
        "type": "click",
        "locator": {"role": "button", "accessibleName": "连接", "exact": True},
        "options": {"timeoutMs": 10000},
        "postconditions": [{"type": "titleContains", "expected": "Termous", "timeoutMs": 10000}],
    }
    ambiguous = run_cli(
        config,
        "ev_action.py",
        ["--run-id", run_id, "--action", json.dumps(ambiguous_action, ensure_ascii=False)],
        expected=(2,),
    )
    after_action = {"id": "strict-after", "type": "snapshot", "options": {"timeoutMs": 10000}}
    after = run_cli(
        config,
        "ev_action.py",
        ["--run-id", run_id, "--action", json.dumps(after_action, ensure_ascii=False)],
    )
    finalized = run_cli(config, "ev_finalize.py", ["--run-id", run_id], expected=(2,))
    error = ambiguous.get("step", {}).get("error", {})
    details = error.get("details", {}) if isinstance(error, dict) else {}
    before_preview = str(before.get("step", {}).get("result", {}).get("preview") or "")
    after_preview = str(after.get("step", {}).get("result", {}).get("preview") or "")
    return {
        "runId": run_id,
        "errorCode": error.get("code") if isinstance(error, dict) else None,
        "candidateCount": details.get("candidateCount") if isinstance(details, dict) else None,
        "stateUnchanged": bool(before_preview) and before_preview == after_preview,
        "reportStatus": finalized.get("result", {}).get("status"),
        "pending": finalized.get("pending"),
    }


def navigation_smoke(config: Path) -> dict[str, Any]:
    prepared = run_cli(config, "ev_prepare.py", ["--session", "termous"])
    run_id = str(prepared["runId"])
    views = (
        ("hosts", "主机", True),
        ("forwards", "端口转发", True),
        ("workstation", "工作站", False),
        ("settings", "设置", True),
    )
    steps: list[dict[str, Any]] = []
    for slug, accessible_name, capture in views:
        steps.extend(
            [
                {
                    "id": f"navigate-{slug}",
                    "type": "click",
                    "locator": {"role": "button", "accessibleName": accessible_name, "exact": True},
                    "options": {"timeoutMs": 10000},
                    "postconditions": [{"type": "titleContains", "expected": "Termous", "timeoutMs": 10000}],
                },
                {"id": f"snapshot-{slug}", "type": "snapshot", "options": {"timeoutMs": 10000}},
            ]
        )
        if capture:
            steps.append(
                {
                    "id": f"screenshot-{slug}",
                    "type": "screenshot",
                    "options": {"timeoutMs": 10000, "label": f"navigation-{slug}"},
                }
            )
    workflow = {
        "schemaVersion": 1,
        "goal": "验证 Termous 只读页面导航",
        "steps": steps,
    }
    executed = run_cli(
        config,
        "ev_workflow.py",
        ["--run-id", run_id, "--workflow", json.dumps(workflow, ensure_ascii=False), "--no-finalize"],
        timeout=180,
    )
    finalized = run_cli(config, "ev_finalize.py", ["--run-id", run_id])
    snapshot_steps = [
        step
        for step in executed.get("steps", [])
        if step.get("action", {}).get("type") == "snapshot"
    ]
    view_evidence = []
    previews = []
    for step in snapshot_steps:
        preview = str(step.get("result", {}).get("preview") or "")
        previews.append(preview)
        view_evidence.append(
            {
                "label": step.get("label"),
                "characters": len(preview),
                "sha256": hashlib.sha256(preview.encode("utf-8")).hexdigest(),
            }
        )
    artifacts = [
        item
        for item in finalized.get("result", {}).get("artifacts", [])
        if str(item.get("label") or "").startswith("navigation-")
    ]
    return {
        "runId": run_id,
        "state": finalized.get("state"),
        "pending": finalized.get("pending"),
        "views": view_evidence,
        "viewsDiffer": len(previews) == len(views) and len(set(previews)) == len(previews),
        "screenshots": {
            "successCount": len(artifacts),
            "distinctDigests": len({item.get("sha256") for item in artifacts}) == len(artifacts),
            "qualityVerified": bool(artifacts) and all(item.get("quality", {}).get("pixelVariation", 0) > 1 for item in artifacts),
        },
    }


def public_service_smoke(endpoint: str, work_dir: Path) -> dict[str, Any]:
    config = runtime_config(work_dir)
    application, server, thread = start_service(config)
    result: dict[str, Any] = {}
    try:
        health = run_cli(config, "ev_health.py", [])
        probe = run_cli(config, "ev_probe.py", ["--cdp", endpoint])
        targets = probe.get("targets", [])
        if not targets:
            raise RuntimeError("公共 ev_probe 未发现 Termous page target")
        candidates = [item for item in targets if not str(item.get("url", "")).startswith("devtools://")]
        selected = candidates[0] if candidates else targets[0]
        selector = ["--target-id", str(selected["targetId"])] if selected.get("targetId") else ["--target-index", str(targets.index(selected))]
        prepared = run_cli(
            config,
            "ev_prepare.py",
            [
                "--session", "termous", "--cdp", endpoint, "--app-id", "termous-smoke",
                "--goal", "验证当前窗口可稳定只读采集", *selector,
            ],
        )
        run_id = str(prepared["runId"])
        screenshots = [
            {
                "id": f"screenshot-{index + 1}",
                "type": "screenshot",
                "options": {"timeoutMs": 10000, "label": f"shot-{index + 1}"},
            }
            for index in range(10)
        ]
        diagnostics = [
            {"id": "console", "type": "collectConsole", "options": {"maxEvents": 100}, "continueOnFailure": True},
            {"id": "exceptions", "type": "collectExceptions", "options": {"maxEvents": 100}, "continueOnFailure": True},
            {"id": "network", "type": "collectNetwork", "options": {"maxEvents": 100}, "continueOnFailure": True},
        ]
        workflow = {
            "schemaVersion": 1,
            "appId": "termous-smoke",
            "goal": "验证当前窗口可稳定只读采集",
            "steps": [
                {"id": "snapshot", "type": "snapshot", "options": {"timeoutMs": 10000}},
                *screenshots,
                *diagnostics,
            ],
        }
        workflow_result = run_cli(
            config,
            "ev_workflow.py",
            [
                "--run-id", run_id,
                "--workflow", json.dumps(workflow, ensure_ascii=False),
                "--no-finalize",
            ],
            timeout=180,
        )
        steps = workflow_result.get("steps", [])
        if len(steps) != len(workflow["steps"]):
            raise RuntimeError(f"公共 workflow 未执行全部步骤：{workflow_result}")
        durations = [
            float(step["durationMs"])
            for step in steps
            if step.get("action", {}).get("type") == "screenshot"
        ]
        if len(durations) != len(screenshots):
            raise RuntimeError(f"公共 workflow 截图结果不完整：{workflow_result}")
        finalized = run_cli(config, "ev_finalize.py", ["--run-id", run_id])
        finalized_again = run_cli(config, "ev_finalize.py", ["--run-id", run_id])
        report = finalized["result"]
        screenshots = [item for item in report["artifacts"] if item.get("mediaType") == "image/png"]
        ordered = sorted(durations)
        p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
        strict_locator = strict_locator_smoke(config)
        navigation = navigation_smoke(config)
        result = {
            "backend": health.get("backend"),
            "probe": {
                "browserVersion": probe.get("browserVersion"),
                "targetCount": len(targets),
                "ambiguityBlocked": len(targets) > 1 and probe.get("selectionError", {}).get("code") == "ambiguous_target",
                "selectedTarget": selected,
            },
            "attach": {"connected": prepared.get("session", {}).get("status") == "connected", "sessionId": prepared.get("session", {}).get("sessionId")},
            "knowledge": prepared.get("knowledge"),
            "run": {
                "runId": run_id,
                "state": finalized.get("state"),
                "report": finalized.get("report"),
                "reportIdempotent": finalized.get("report") == finalized_again.get("report"),
                "pending": finalized.get("pending"),
                "stepCount": report.get("summary", {}).get("stepCount"),
                "artifactCount": report.get("summary", {}).get("artifactCount"),
            },
            "screenshots": {
                "successCount": len(screenshots),
                "p95Ms": round(p95, 3),
                "maxMs": round(max(durations), 3),
                "minBytes": min(item["bytes"] for item in screenshots),
                "maxBytes": max(item["bytes"] for item in screenshots),
                "qualityVerified": all(item.get("quality", {}).get("pixelVariation", 0) > 1 for item in screenshots),
            },
            "diagnostics": {
                "independentArtifacts": sum(item.get("label") in {"console", "exception", "network"} for item in report["artifacts"]),
            },
            "strictLocator": strict_locator,
            "navigation": navigation,
        }
    finally:
        cleanup = stop_service(application, server, thread)
    result["serviceCleanup"] = cleanup
    return result


def stale_service_smoke(work_dir: Path) -> dict[str, Any]:
    config = runtime_config(work_dir)
    application, server, thread = start_service(config)
    try:
        status = run_cli(config, "ev_sessions.py", ["--session", "termous"], expected=(0, 2))
        first = run_cli(config, "ev_detach.py", ["--session", "termous"])
        second = run_cli(config, "ev_detach.py", ["--session", "termous"])
        result = {
            "staleAfterAppExit": status.get("connected") is False,
            "status": status.get("session", {}).get("status"),
            "firstDetach": first.get("alreadyDetached"),
            "secondDetach": second.get("alreadyDetached"),
        }
    finally:
        cleanup = stop_service(application, server, thread)
    result["serviceCleanup"] = cleanup
    return result


def child_main(args: argparse.Namespace) -> int:
    work_dir = Path(args.work_dir).resolve()
    result = stale_service_smoke(work_dir) if args.stale_child else public_service_smoke(args.endpoint, work_dir)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def parent_main(args: argparse.Namespace) -> int:
    exe = Path(args.exe).resolve()
    profile = Path(args.isolated_profile).resolve()
    work_dir = profile.parent / "termous-smoke"
    output = Path(args.output).resolve() if args.output else profile.parent.parent / "artifacts" / "validation" / "termous-smoke.json"
    if not exe.is_file():
        raise RuntimeError(f"Termous.exe 不存在：{exe}")
    existing = existing_termous_pids()
    if existing:
        raise RuntimeError(f"检测到任务外 Termous 进程，拒绝启动或清理：{existing}")
    assert_port_free(args.port)
    if profile.exists():
        shutil.rmtree(profile)
    if work_dir.exists():
        shutil.rmtree(work_dir)
    profile.mkdir(parents=True)
    work_dir.mkdir(parents=True)
    endpoint = f"http://127.0.0.1:{args.port}"
    stdout_file = (work_dir / "termous.stdout.log").open("wb")
    stderr_file = (work_dir / "termous.stderr.log").open("wb")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        [str(exe), f"--remote-debugging-port={args.port}", f"--user-data-dir={profile}", "--no-first-run"],
        cwd=exe.parent,
        stdout=stdout_file,
        stderr=stderr_file,
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    checks: dict[str, Any] = {}
    failures: list[str] = []
    owned_pids: list[int] = []
    selected_python: Path | None = None
    try:
        version = wait_endpoint(endpoint)
        owned_pids = existing_termous_pids()
        selected_python = driver_python(work_dir)
        child = subprocess.run(
            [
                str(selected_python), "-X", "utf8", "-B", str(Path(__file__).resolve()),
                "--driver-child", "--endpoint", endpoint, "--work-dir", str(work_dir),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if child.returncode != 0:
            raise RuntimeError(f"public HTTP/CLI Termous child 失败：{child.stderr[-1500:]}")
        checks["cdpVersion"] = {"Browser": version.get("Browser"), "Protocol-Version": version.get("Protocol-Version")}
        checks["driver"] = json.loads(child.stdout)
        driver = checks["driver"]
        screenshots = driver["screenshots"]
        if screenshots.get("successCount") != 10 or screenshots.get("qualityVerified") is not True:
            failures.append("Termous screenshot 未达到 10/10 quality verified")
        if float(screenshots.get("p95Ms", 999999)) > 2000:
            failures.append("Termous warm screenshot P95 超过 2 秒")
        if driver.get("attach", {}).get("connected") is not True:
            failures.append("Termous public prepare/attach 未通过")
        if driver.get("knowledge", {}).get("decision") != "abstain" or driver.get("knowledge", {}).get("candidates"):
            failures.append("空 canonical knowledge 未明确 abstain")
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
        if driver.get("serviceCleanup", {}).get("ownerAlive") is not False:
            failures.append("临时 verifier automation owner 未停止")
    except Exception as exc:
        failures.append(str(exc))
    finally:
        cleanup = stop_process_tree(process, owned_pids)
        stdout_file.close()
        stderr_file.close()
        cleanup["endpointClosed"] = endpoint_closed(endpoint)
        cleanup["foreignTermousPidsAfter"] = existing_termous_pids()
        cleanup["cleanupVerified"] = cleanup["rootExited"] and cleanup["endpointClosed"] and not cleanup["foreignTermousPidsAfter"]
        checks["cleanup"] = cleanup
        if not cleanup["cleanupVerified"]:
            failures.append("Termous 测试进程树或 CDP endpoint 未完成清理")
    if selected_python is not None and (work_dir / "runtime" / "config.json").exists():
        stale = subprocess.run(
            [
                str(selected_python), "-X", "utf8", "-B", str(Path(__file__).resolve()),
                "--driver-child", "--stale-child", "--work-dir", str(work_dir),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if stale.returncode == 0:
            checks["postExit"] = json.loads(stale.stdout)
            if checks["postExit"].get("staleAfterAppExit") is not True or checks["postExit"].get("secondDetach") is not True:
                failures.append("应用退出后的 stale session/repeat detach 未闭环")
        else:
            failures.append(f"post-exit stale child 失败：{stale.stderr[-1000:]}")
    result = {
        "ok": not failures,
        "application": {"name": "Termous", "version": "0.1.0", "isolatedProfile": str(profile)},
        "readOnly": True,
        "knowledgeWrite": False,
        "checks": checks,
        "failures": failures,
    }
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe")
    parser.add_argument("--isolated-profile")
    parser.add_argument("--output")
    parser.add_argument("--port", type=int, default=19422)
    parser.add_argument("--no-learn", action="store_true")
    parser.add_argument("--driver-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--stale-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--endpoint", help=argparse.SUPPRESS)
    parser.add_argument("--work-dir", help=argparse.SUPPRESS)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.driver_child:
        return child_main(args)
    if not args.exe or not args.isolated_profile or not args.no_learn:
        raise SystemExit("必须提供 --exe、--isolated-profile 和 --no-learn")
    return parent_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
