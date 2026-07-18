"""安装根分离与引用安全 retention 测试。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _helpers import TestTemporaryDirectory  # noqa: E402
from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from electron_verifier.limits import DEFAULT_LIMITS  # noqa: E402
from electron_verifier.paths import SkillPaths, inspect_skill_install, skill_paths  # noqa: E402
from electron_verifier.retention import RetentionService  # noqa: E402
from electron_verifier.retention_policy import RetentionPolicy  # noqa: E402
from ev_common import paths_for_workspace, write_environment  # noqa: E402
from ev_init import service_config  # noqa: E402
from knowledge_fixtures import action_asset  # noqa: E402


TEST_ROOT = Path(os.environ.get("EV_TEST_ROOT", Path.cwd() / ".harness" / "electron-ui-verifier-test-tmp"))
NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


def timestamp(seconds_ago: int) -> str:
    return (NOW - timedelta(seconds=seconds_ago)).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def create_run(root: Path, *, state: str = "passed", age: int = 100, run_id: str | None = None) -> str:
    run_id = run_id or str(uuid.uuid4())
    run_dir = root / "runs" / run_id
    write_json(
        run_dir / "journal.json",
        {
            "schemaVersion": 1,
            "runId": run_id,
            "state": state,
            "createdAt": timestamp(age + 10),
            "updatedAt": timestamp(age),
            "steps": [],
        },
    )
    (run_dir / "artifacts").mkdir()
    (run_dir / "artifacts" / "sample.txt").write_text("retention-evidence", encoding="utf-8")
    return run_id


def create_operation(root: Path, run_id: str, *, age: int = 100, state: str = "succeeded") -> str:
    operation_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    value = {
        "schemaVersion": 1,
        "operationId": operation_id,
        "requestId": request_id,
        "requestFingerprint": "a" * 64,
        "kind": "action",
        "runId": run_id,
        "state": state,
        "done": state != "running",
        "cancelRequested": False,
        "deadlineAt": timestamp(age - 10),
        "createdAt": timestamp(age + 20),
        "updatedAt": timestamp(age),
        "revision": 2,
    }
    if state in {"queued", "running"}:
        value["startedAt"] = timestamp(age)
    else:
        value["finishedAt"] = timestamp(age)
    write_json(root / "operations" / f"{operation_id}.json", value)
    request_name = hashlib.sha256(request_id.encode("utf-8")).hexdigest() + ".json"
    write_json(
        root / "operations" / "requests" / request_name,
        {
            "schemaVersion": 1,
            "requestId": request_id,
            "requestFingerprint": "a" * 64,
            "operationId": operation_id,
        },
    )
    return operation_id


def immediate_policy(*, include_orphans: bool = False) -> RetentionPolicy:
    return RetentionPolicy(
        terminal_age_seconds=10,
        max_runs=100,
        max_total_bytes=1024 * 1024,
        operation_expiration_seconds=10,
        orphan_grace_seconds=10,
        include_orphans=include_orphans,
    )


class RetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def setUp(self) -> None:
        self.temporary = TestTemporaryDirectory(dir=TEST_ROOT)
        self.root = Path(self.temporary.name) / "state"
        KnowledgeReset(self.root).ensure()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_preview_apply_idempotency_and_reference_protection(self) -> None:
        old_run = create_run(self.root)
        recent_run = create_run(self.root, age=1)
        open_run = create_run(self.root, state="running")
        linked_run = create_run(self.root)
        operation_id = create_operation(self.root, linked_run)
        approved_run = create_run(self.root)
        approved_asset = action_asset("已批准动作")
        CanonicalStore(self.root).activate([approved_asset], run_id=approved_run)
        pending_run = create_run(self.root)
        write_json(
            self.root / "pending" / pending_run / "pending.json",
            {
                "runId": pending_run,
                "bundleFingerprint": "f" * 64,
                "proposals": [{"assetId": "action-" + "1" * 40}],
            },
        )
        orphan = action_asset("未引用动作", evidence_digest="c" * 64)
        CanonicalStore(self.root).stage_objects([orphan])
        service = RetentionService(self.root, now=NOW)

        preview = service.preview(immediate_policy())

        keys = {item["key"] for item in preview["candidates"]}
        self.assertEqual({f"operation:{operation_id}", f"run:{old_run}"}, keys)
        self.assertTrue((self.root / "runs" / old_run).exists())
        protected = {f"{item['kind']}:{item['id']}": set(item["reasons"]) for item in preview["protected"]}
        self.assertIn("within_policy", protected[f"run:{recent_run}"])
        self.assertIn("nonterminal", protected[f"run:{open_run}"])
        self.assertIn("operation_reference", protected[f"run:{linked_run}"])
        self.assertIn("approved_decision_evidence", protected[f"run:{approved_run}"])
        self.assertIn("unsealed_pending", protected[f"run:{pending_run}"])
        self.assertIn("orphans_not_requested", protected[f"orphanObject:{orphan.asset_id}"])
        with self.assertRaises(VerifierError) as confirmation:
            service.apply(immediate_policy(), preview["fingerprint"], confirmed=False)
        self.assertEqual("retention_confirmation_required", confirmation.exception.code)

        applied = service.apply(immediate_policy(), preview["fingerprint"], confirmed=True)
        repeated = service.apply(immediate_policy(), preview["fingerprint"], confirmed=True)

        self.assertTrue(applied["ok"])
        self.assertEqual(2, applied["deletedCount"])
        self.assertFalse((self.root / "runs" / old_run).exists())
        self.assertFalse((self.root / "operations" / f"{operation_id}.json").exists())
        self.assertTrue((self.root / "runs" / linked_run).exists())
        self.assertTrue(repeated["alreadyApplied"])
        next_preview = service.preview(immediate_policy())
        self.assertIn(f"run:{linked_run}", {item["key"] for item in next_preview["candidates"]})

    def test_stale_fingerprint_is_rejected_before_receipt(self) -> None:
        create_run(self.root)
        service = RetentionService(self.root, now=NOW)
        preview = service.preview(immediate_policy())
        create_run(self.root)

        with self.assertRaises(VerifierError) as caught:
            service.apply(immediate_policy(), preview["fingerprint"], confirmed=True)

        self.assertEqual("retention_fingerprint_stale", caught.exception.code)
        self.assertFalse((self.root / "retention" / "applications" / f"{preview['fingerprint']}.json").exists())

    def test_receipt_path_cannot_escape_state_root(self) -> None:
        create_run(self.root)
        service = RetentionService(self.root, now=NOW)
        preview = service.preview(immediate_policy())
        service.receipts_dir = self.root.parent / "outside-receipts"

        with self.assertRaises(VerifierError) as caught:
            service.apply(immediate_policy(), preview["fingerprint"], confirmed=True)

        self.assertEqual("path_outside_runtime", caught.exception.code)
        self.assertFalse(service.receipts_dir.exists())

    def test_fingerprint_remains_stable_as_clock_advances(self) -> None:
        create_run(self.root)
        first = RetentionService(self.root, now=NOW).preview(immediate_policy())
        later_service = RetentionService(self.root, now=NOW + timedelta(seconds=30))

        second = later_service.preview(immediate_policy())
        applied = later_service.apply(immediate_policy(), first["fingerprint"], confirmed=True)

        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertNotIn("ageSeconds", second["candidates"][0])
        self.assertTrue(applied["ok"])

    def test_orphan_requires_explicit_flag_and_grace(self) -> None:
        orphan = action_asset("可清理孤儿", evidence_digest="d" * 64)
        CanonicalStore(self.root).stage_objects([orphan])
        service = RetentionService(self.root, now=NOW)

        default_preview = service.preview(immediate_policy())
        orphan_preview = service.preview(immediate_policy(include_orphans=True))

        self.assertNotIn(orphan.asset_id, {item["id"] for item in default_preview["candidates"]})
        self.assertIn(orphan.asset_id, {item["id"] for item in orphan_preview["candidates"]})
        applied = service.apply(
            immediate_policy(include_orphans=True),
            orphan_preview["fingerprint"],
            confirmed=True,
        )
        self.assertTrue(applied["ok"])
        self.assertFalse((self.root / "knowledge" / "objects" / f"{orphan.asset_id}.json").exists())

    def test_delete_failure_stops_before_later_candidates(self) -> None:
        create_run(self.root, age=200)
        create_run(self.root, age=100)
        service = RetentionService(self.root, now=NOW)
        preview = service.preview(immediate_policy())
        error = VerifierError("retention_delete_failed", "injected", status=500)

        with mock.patch.object(service, "_remove_candidate", side_effect=error) as remove:
            result = service.apply(immediate_policy(), preview["fingerprint"], confirmed=True)

        self.assertFalse(result["ok"])
        self.assertEqual(1, len(result["results"]))
        self.assertEqual(1, remove.call_count)


class InstallPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    def test_install_paths_come_from_module_location(self) -> None:
        paths = skill_paths()
        inspection = inspect_skill_install(paths)
        self.assertTrue(inspection["ok"], inspection)
        self.assertEqual(Path(__file__).resolve().parents[1], paths.root)

    def test_environment_omits_unknown_install_root(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            workspace = Path(folder) / "workspace"
            workspace.mkdir()

            environment = write_environment(paths_for_workspace(workspace), python_path=Path(sys.executable))

            self.assertNotIn("skillRoot", environment)

    def test_service_launcher_uses_explicit_install_root(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            workspace = Path(folder) / "workspace"
            install_root = Path(folder) / "copied-skill"
            workspace.mkdir()
            (install_root / "scripts").mkdir(parents=True)
            server = install_root / "scripts" / "ev_server.py"
            server.write_text("# fixture\n", encoding="utf-8")
            install = SkillPaths(
                root=install_root,
                scripts_dir=install_root / "scripts",
                server_script=server,
                check_script=install_root / "scripts" / "ev_check_env.py",
                requirements_file=install_root / "requirements.txt",
                schemas_dir=install_root / "schemas",
                assets_dir=install_root / "assets",
            )

            value = service_config(workspace, Path(sys.executable), workspace / "config.json", 18180, install)

            self.assertEqual(str(server), value["launcher"]["script"])
            self.assertEqual(str(workspace), value["cwd"])
            self.assertNotIn(str(workspace / "skills"), value["launcher"]["script"])
            self.assertEqual("1", value["environment"]["set"]["PYTHONDONTWRITEBYTECODE"])
            self.assertEqual(
                DEFAULT_LIMITS.service_readiness_timeout_seconds,
                value["readiness"]["timeoutSeconds"],
            )
            self.assertGreater(
                value["readiness"]["timeoutSeconds"],
                DEFAULT_LIMITS.automation_start_timeout_seconds,
            )


if __name__ == "__main__":
    unittest.main()
