#!/usr/bin/env python3
"""从 verifier report 和 artifact 中抽取候选知识。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ev_common import EVError, read_json
from ev_knowledge_store import clip_text, stable_id


TEXT_TOKEN_LIMIT = 80
FEATURE_TEXTS = (
    "首页",
    "刷新",
    "导出文件",
    "磁盘信息",
    "修复",
    "分析",
    "OCR识别",
    "时间校正",
    "哈希计算",
    "导出报告",
    "磁盘",
    "镜像文件",
    "视频修复",
    "网络扫描",
    "视频分析",
    "查看",
    "更多",
)


def safe_report_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise EVError("--report must be an absolute path")
    if not path.exists() or not path.is_file():
        raise EVError(f"report does not exist: {path}")
    if path.name != "report.json":
        raise EVError("--report must point to report.json")
    return path.resolve()


def load_json_artifact(path_text: str, report_path: Path) -> dict[str, Any] | None:
    path = Path(path_text)
    if not path.is_absolute() or path.suffix.lower() != ".json":
        return None
    resolved = path.resolve()
    report_root = report_path.parent.resolve()
    if report_root not in resolved.parents and resolved.parent != report_root:
        return None
    if not resolved.exists() or resolved.stat().st_size > 5_000_000:
        return None
    value = read_json(resolved)
    return value if isinstance(value, dict) else None


def target_route(target: dict[str, Any]) -> str:
    url = str(target.get("url") or "")
    if "#" in url:
        return "#" + url.split("#", 1)[1]
    return url


def app_id_from_report(report: dict[str, Any], override: str | None = None) -> str:
    if override:
        return override
    version = report.get("version") if isinstance(report.get("version"), dict) else {}
    user_agent = str(version.get("User-Agent") or "")
    selected = report.get("selectedTarget") if isinstance(report.get("selectedTarget"), dict) else {}
    url = str(selected.get("url") or "")
    if "VideoForensic" in user_agent or "VideoForensic" in url:
        return "videoForensic"
    title = str(selected.get("title") or "electron-app")
    return stable_id("app", title, user_agent, url)


def display_name_from_report(report: dict[str, Any], app_id: str) -> str:
    version = report.get("version") if isinstance(report.get("version"), dict) else {}
    user_agent = str(version.get("User-Agent") or "")
    if "VideoForensic" in user_agent:
        return "VideoForensic"
    selected = report.get("selectedTarget") if isinstance(report.get("selectedTarget"), dict) else {}
    return str(selected.get("title") or app_id)


def product_version_from_report(report: dict[str, Any]) -> str:
    version = report.get("version") if isinstance(report.get("version"), dict) else {}
    user_agent = str(version.get("User-Agent") or "")
    match = re.search(r"(VideoForensic/\d+(?:\.\d+)+)", user_agent)
    if not match:
        match = re.search(r"(Electron/\d+(?:\.\d+)+)", user_agent)
    return match.group(1) if match else str(version.get("Browser") or "")


def artifact_url_title(artifacts: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    for artifact in artifacts:
        url = artifact.get("url")
        title = artifact.get("title")
        if isinstance(url, str) and url:
            return url, title if isinstance(title, str) else None
    return None, None


def collect_artifact_dicts(report: dict[str, Any], report_path: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for path_text in report.get("artifacts") or []:
        if isinstance(path_text, str):
            resolved = str(Path(path_text).resolve()) if Path(path_text).is_absolute() else path_text
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            loaded = load_json_artifact(path_text, report_path)
            if loaded is not None:
                artifacts.append(loaded)
    for step in report.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for path_text in step.get("artifacts") or []:
            if isinstance(path_text, str):
                resolved = str(Path(path_text).resolve()) if Path(path_text).is_absolute() else path_text
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                loaded = load_json_artifact(path_text, report_path)
                if loaded is not None:
                    artifacts.append(loaded)
    return artifacts


def text_from_report(report: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for artifact in artifacts:
        for key in ("bodyText", "text"):
            value = artifact.get(key)
            if isinstance(value, str):
                chunks.append(value)
    for step in report.get("steps") or []:
        if not isinstance(step, dict):
            continue
        data = step.get("data") if isinstance(step.get("data"), dict) else {}
        preview = data.get("valuePreview")
        if isinstance(preview, str):
            chunks.append(preview)
    return clip_text("\n".join(chunks), 12000)


def key_texts_from_text(text: str) -> list[str]:
    found: list[str] = []
    for token in FEATURE_TEXTS:
        if token in text and token not in found:
            found.append(token)
    for match in re.findall(r"\b\d{14}\b", text):
        if match not in found:
            found.append(match)
        if len(found) >= TEXT_TOKEN_LIMIT:
            break
    return found[:TEXT_TOKEN_LIMIT]


def elements_from_artifacts(app_id: str, screen_id: str, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    seen: set[str] = set()
    for artifact in artifacts:
        raw_elements = artifact.get("elements")
        if not isinstance(raw_elements, list):
            continue
        for item in raw_elements:
            if not isinstance(item, dict):
                continue
            text = clip_text(item.get("text"), 300).strip()
            role = clip_text(item.get("role"), 120).strip()
            if not text or len(text) > 80:
                continue
            if text not in FEATURE_TEXTS and role != "button":
                continue
            final_role = role or ("button" if text in {"查看", "更多"} else "")
            key = f"{final_role}:{text}"
            if key in seen:
                continue
            seen.add(key)
            selector = {"type": "text", "value": text}
            rect = {"x": item.get("x"), "y": item.get("y"), "width": item.get("width"), "height": item.get("height")}
            elements.append(
                {
                    "appId": app_id,
                    "screenId": screen_id,
                    "name": text,
                    "role": final_role,
                    "text": text,
                    "selectorCandidates": [selector],
                    "anchors": [rect],
                    "confidence": 0.55 if role == "button" else 0.4,
                    "status": "candidate",
                }
            )
    return elements[:80]


def workflows_from_report(app_id: str, report: dict[str, Any], text: str) -> list[dict[str, Any]]:
    workflows: list[dict[str, Any]] = []
    steps = report.get("steps") if isinstance(report.get("steps"), list) else []
    has_click = any(isinstance(step, dict) and step.get("action") in {"clickText", "clickXY"} for step in steps)
    if has_click:
        workflows.append(
            {
                "appId": app_id,
                "goal": "复用已验证 UI 操作流程",
                "preconditions": ["已 attach 到对应 Electron target"],
                "steps": [{"sourceStep": step.get("id"), "action": step.get("action")} for step in steps if isinstance(step, dict)],
                "assertions": [{"status": report.get("status")}],
                "confidence": 0.45,
                "status": "candidate",
            }
        )
    if "查看" in text and "历史记录" in text:
        workflows.append(
            {
                "appId": app_id,
                "goal": "从历史记录打开案件详情",
                "preconditions": ["位于首页历史记录列表", "目标案件行可见"],
                "steps": [{"clickText": {"text": "查看", "index": 0}}],
                "assertions": [{"waitText": "扫描结果"}],
                "confidence": 0.55,
                "status": "candidate",
            }
        )
    return workflows


def extract_knowledge(report_path: Path, app_id_override: str | None = None, notes: str | None = None) -> dict[str, Any]:
    report = read_json(report_path)
    if not isinstance(report, dict):
        raise EVError("report must be a JSON object")
    artifacts = collect_artifact_dicts(report, report_path)
    app_id = app_id_from_report(report, app_id_override)
    selected = report.get("selectedTarget") if isinstance(report.get("selectedTarget"), dict) else {}
    text = text_from_report(report, artifacts)
    artifact_url, artifact_title = artifact_url_title(artifacts)
    selected_for_route = dict(selected)
    if artifact_url:
        selected_for_route["url"] = artifact_url
    route = target_route(selected_for_route)
    selected_title = str(selected.get("title") or "")
    title = artifact_title or (f"index.html{route}" if route.startswith("#/") else selected_title)
    screen_id = stable_id("screen", app_id, route, title, key_texts_from_text(text))
    app = {
        "appId": app_id,
        "displayName": display_name_from_report(report, app_id),
        "productName": display_name_from_report(report, app_id),
        "version": product_version_from_report(report),
        "status": "observed",
        "data": {
            "cdp": report.get("cdp"),
            "browser": (report.get("version") or {}).get("Browser") if isinstance(report.get("version"), dict) else None,
        },
    }
    screen = {
        "appId": app_id,
        "screenId": screen_id,
        "route": route,
        "title": title,
        "fingerprint": stable_id("fp", route, title, key_texts_from_text(text)),
        "summary": clip_text(text.replace("\n", " "), 1000),
        "keyTexts": key_texts_from_text(text),
        "status": "candidate",
    }
    evidence = {
        "sourceReport": str(report_path),
        "artifactRefs": [str(path) for path in report.get("artifacts") or [] if isinstance(path, str)],
        "notes": notes or "learned from verifier report",
    }
    return {
        "app": app,
        "screens": [screen],
        "elements": elements_from_artifacts(app_id, screen_id, artifacts),
        "workflows": workflows_from_report(app_id, report, text),
        "evidence": evidence,
        "stats": {
            "artifactCount": len(artifacts),
            "textLength": len(text),
            "elementCandidates": len(elements_from_artifacts(app_id, screen_id, artifacts)),
        },
    }
