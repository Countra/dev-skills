#!/usr/bin/env python3
"""运行跨应用、中英文 hybrid retrieval 正负例基准。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "electron-ui-verifier" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.knowledge_models import CanonicalAsset  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.retrieval import HybridRetriever  # noqa: E402
from knowledge_fixtures import action_asset, runtime_context  # noqa: E402


TASKS = {
    "editor": [
        ("保存文档", "Save current file"), ("查找文本", "Find in document"),
        ("替换文本", "Replace matching text"), ("打开文件", "Open a local file"),
        ("关闭标签页", "Close active tab"), ("切换主题", "Change color theme"),
        ("调整字号", "Increase editor font"), ("撤销更改", "Undo last edit"),
        ("重做更改", "Redo last edit"), ("导出 PDF", "Export document as PDF"),
        ("打开命令面板", "Show command palette"), ("格式化文档", "Format current document"),
    ],
    "mail": [
        ("撰写邮件", "Compose a new message"), ("发送邮件", "Send current message"),
        ("保存草稿", "Keep message as draft"), ("搜索邮件", "Find messages"),
        ("标记已读", "Mark message as read"), ("添加星标", "Star this message"),
        ("移动到归档", "Archive selected message"), ("删除邮件", "Move message to trash"),
        ("回复邮件", "Reply to sender"), ("转发邮件", "Forward this message"),
        ("添加附件", "Attach a local file"), ("创建标签", "Create a mail label"),
    ],
    "database": [
        ("创建连接", "Add database connection"), ("测试连接", "Verify connection settings"),
        ("打开查询编辑器", "Open SQL editor"), ("执行查询", "Run current query"),
        ("停止查询", "Cancel running query"), ("导出结果", "Export query results"),
        ("导入数据", "Import table data"), ("查看表结构", "Inspect table schema"),
        ("创建表", "Create database table"), ("删除记录", "Delete selected row"),
        ("刷新模式", "Refresh database schema"), ("打开事务日志", "Show transaction log"),
    ],
    "dashboard": [
        ("刷新数据", "Reload dashboard data"), ("切换日期范围", "Change date range"),
        ("添加筛选器", "Add dashboard filter"), ("清除筛选器", "Reset all filters"),
        ("导出图表", "Export selected chart"), ("下载数据", "Download source data"),
        ("打开详情", "View metric details"), ("切换布局", "Change dashboard layout"),
        ("新建仪表板", "Create a dashboard"), ("保存仪表板", "Save dashboard changes"),
        ("分享视图", "Share current view"), ("订阅报告", "Subscribe to report"),
    ],
}


NEGATIVES = {
    "editor": ["预订酒店", "扫描局域网", "创建视频会议", "购买火车票", "同步智能手表", "查看天气雷达"],
    "mail": ["编译源代码", "调整数据库索引", "绘制三维模型", "启动容器集群", "编辑音频波形", "格式化磁盘"],
    "database": ["发送即时消息", "裁剪照片", "播放音乐", "生成字幕", "查看航班状态", "控制屏幕亮度"],
    "dashboard": ["重命名代码符号", "安装打印机驱动", "签署电子合同", "连接蓝牙耳机", "录制语音", "管理游戏存档"],
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_assets() -> tuple[list[CanonicalAsset], list[dict[str, str]]]:
    assets: list[CanonicalAsset] = []
    positives: list[dict[str, str]] = []
    for app_id, tasks in TASKS.items():
        for goal, alias in tasks:
            asset = action_asset(app_id, goal, [alias])
            assets.append(asset)
            positives.append({"appId": app_id, "query": f"Please {alias.lower()}", "assetId": asset.asset_id})
    return assets, positives


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    work_dir = Path(args.work_dir).resolve()
    if ROOT not in work_dir.parents:
        raise SystemExit("--work-dir 必须位于当前仓库内")
    output = Path(args.output).resolve()
    if ROOT not in output.parents:
        raise SystemExit("--output 必须位于当前仓库内")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    state = work_dir / "state"
    KnowledgeReset(state).ensure()
    store = CanonicalStore(state)
    assets, positives = build_assets()
    store.activate(assets)
    hits = 0
    reciprocal = 0.0
    false_positives = 0
    samples: list[dict[str, Any]] = []
    with HybridRetriever(store) as retriever:
        for case in positives:
            result = retriever.search(case["query"], runtime_context(case["appId"]), limit=5)
            ids = [item["assetId"] for item in result["candidates"]]
            rank = ids.index(case["assetId"]) + 1 if case["assetId"] in ids and result["decision"] == "reuse" else None
            hits += int(rank is not None)
            reciprocal += 1.0 / rank if rank else 0.0
            if len(samples) < 8:
                samples.append({"query": case["query"], "decision": result["decision"], "rank": rank})
        negative_count = 0
        for app_id, queries in NEGATIVES.items():
            for query in queries:
                negative_count += 1
                result = retriever.search(query, runtime_context(app_id), limit=5)
                false_positives += int(result["decision"] == "reuse")
    recall = hits / len(positives)
    mrr = reciprocal / len(positives)
    false_positive_rate = false_positives / negative_count
    metrics = {
        "positiveCount": len(positives),
        "negativeCount": negative_count,
        "recallAt5": round(recall, 6),
        "mrrAt5": round(mrr, 6),
        "negativeFalsePositiveRate": round(false_positive_rate, 6),
    }
    gates = {
        "positiveCorpus": len(positives) >= 40,
        "negativeCorpus": negative_count >= 20,
        "recallAt5": recall >= 0.90,
        "mrrAt5": mrr >= 0.80,
        "negativeFalsePositiveRate": false_positive_rate <= 0.05,
    }
    result = {"ok": all(gates.values()), "metrics": metrics, "gates": gates, "samples": samples}
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
