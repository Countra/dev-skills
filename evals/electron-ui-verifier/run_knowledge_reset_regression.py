#!/usr/bin/env python3
"""验证 fresh/current/legacy direct reset 与 sealed rebuild。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "electron-ui-verifier" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from knowledge_fixtures import action_asset  # noqa: E402


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def asset():
    return action_asset("eval-app", "保存设置", ["保存配置"], evidence_digest="b" * 64)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--deny-unconfirmed-live-reset", action="store_true")
    args = parser.parse_args()
    work_dir = Path(args.work_dir).resolve()
    if ROOT not in work_dir.parents:
        raise SystemExit("--work-dir 必须位于当前仓库内")
    if args.deny_unconfirmed_live_reset and ".harness" not in work_dir.parts:
        raise SystemExit("live reset guard 要求隔离 .harness work-dir")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    checks: dict[str, Any] = {}
    failures: list[str] = []
    try:
        fresh_state = work_dir / "fresh" / "state"
        fresh = KnowledgeReset(fresh_state).ensure()
        fresh_verify = CanonicalStore(fresh_state).verify()
        checks["freshInit"] = {
            "status": fresh["status"],
            "assetCount": fresh_verify["activeAssetCount"],
            "journalMode": fresh_verify["derived"]["journalMode"],
        }

        legacy_state = work_dir / "legacy" / "state"
        legacy_root = legacy_state / "knowledge"
        legacy_root.mkdir(parents=True)
        (legacy_root / "knowledge.db").write_bytes(b"legacy-sentinel-not-sqlite")
        (legacy_root / "workflow.json").write_text("{legacy-invalid-json", encoding="utf-8")
        reset = KnowledgeReset(legacy_state)
        rejection_code = None
        try:
            reset.ensure()
        except VerifierError as exc:
            rejection_code = exc.code
        preview = reset.preview()
        wrong_code = None
        try:
            reset.apply("0" * 64)
        except VerifierError as exc:
            wrong_code = exc.code
        remained_after_wrong = (legacy_root / "knowledge.db").exists()
        applied = reset.apply(preview["confirmationFingerprint"])
        retired = Path(str(applied["retired"]))
        retired_sentinel = (retired / "knowledge.db").read_bytes()
        current_empty = CanonicalStore(legacy_state).list_assets() == []
        checks["legacyDirectReset"] = {
            "rejectionCode": rejection_code,
            "wrongFingerprintCode": wrong_code,
            "remainedAfterWrongFingerprint": remained_after_wrong,
            "retiredSentinelPreserved": retired_sentinel == b"legacy-sentinel-not-sqlite",
            "currentEmpty": current_empty,
        }

        crash_retired = legacy_state / "retired" / "crash-window"
        os.replace(legacy_state / "knowledge", crash_retired)
        recovered = reset.ensure()
        checks["crashRecovery"] = {
            "status": recovered["status"],
            "retiredStillPresent": crash_retired.exists(),
            "currentEmpty": CanonicalStore(legacy_state).list_assets() == [],
        }

        rebuild_state = work_dir / "rebuild" / "state"
        KnowledgeReset(rebuild_state).ensure()
        store = CanonicalStore(rebuild_state)
        activation = store.activate([asset()])
        persisted = activation["assets"][0]
        store.paths["index"].write_bytes(b"corrupt-derived-only")
        rebuilt = CanonicalStore(rebuild_state).verify()
        preview_only = KnowledgeReset(rebuild_state).preview()
        still_present = len(CanonicalStore(rebuild_state).list_assets()) == 1
        checks["canonicalRebuild"] = {
            "assetId": persisted["assetId"],
            "assetCount": rebuilt["activeAssetCount"],
            "indexAssetCount": rebuilt["derived"]["assetCount"],
            "quarantined": bool(rebuilt["derived"].get("quarantined")),
            "journalMode": rebuilt["derived"]["journalMode"],
        }
        checks["unconfirmedCurrentReset"] = {
            "previewWritePerformed": preview_only["writePerformed"],
            "assetStillPresent": still_present,
        }
    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
    required = {
        "fresh": checks.get("freshInit", {}).get("journalMode") == "delete",
        "legacyRejected": checks.get("legacyDirectReset", {}).get("rejectionCode") == "knowledge_reinitialize_required",
        "wrongFingerprintSafe": checks.get("legacyDirectReset", {}).get("remainedAfterWrongFingerprint") is True,
        "retiredIsolated": checks.get("legacyDirectReset", {}).get("currentEmpty") is True,
        "crashRecovered": checks.get("crashRecovery", {}).get("currentEmpty") is True,
        "rebuild": checks.get("canonicalRebuild", {}).get("assetCount") == 1,
        "unconfirmedSafe": checks.get("unconfirmedCurrentReset", {}).get("assetStillPresent") is True,
    }
    failures.extend(name for name, passed in required.items() if not passed)
    result = {"ok": not failures, "checks": checks, "required": required, "failures": failures}
    write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
