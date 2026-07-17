from __future__ import annotations

import io
import json
import stat
import sys
import time
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, create_service, workspace_directory, write_json  # noqa: E402
from process_manager.errors import (  # noqa: E402
    EnvironmentUnverifiableError,
    ManagerOfflineError,
    RuntimeInsecureError,
    RuntimePermissionDeniedError,
    SupervisorError,
)
from process_manager.manager_state import (  # noqa: E402
    ManagerStateResolver,
    empty_evidence,
    operation_store,
    runtime_failure_state,
)
from process_manager.platforms.base import PersistedOwnerEvidence  # noqa: E402
from process_manager.platforms.windows_acl import (  # noqa: E402
    FILE_ALL_ACCESS,
    GRANT_ACCESS,
    AclEntry,
    AclSnapshot,
    WindowsAcl,
    validate_acl_snapshot,
)
from process_manager.run_finalization import OwnerFinalizer, RunFinalizationCoordinator  # noqa: E402
from process_manager.runtime import (  # noqa: E402
    build_manager_identity,
    initialize_runtime,
    prepare_runtime_lock,
    write_manager_identity,
)
from process_manager.runtime_context import resolve_runtime_context  # noqa: E402
import process_manager.runtime_fingerprint as fingerprint_module  # noqa: E402
from process_manager.state import StateStore  # noqa: E402
import pm_doctor  # noqa: E402


class InspectionFailureAdapter(FakeAdapter):
    def inspect_persisted_owner(self, evidence: PersistedOwnerEvidence):  # noqa: ANN201
        del evidence
        raise OSError("fixture inspection denied")


class RuntimeSecurityTests(unittest.TestCase):
    def test_adapter_preserves_lexical_state_root(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            state_root = workspace / ".harness" / "runtime-link"
            resolved_target = workspace / ".harness" / "runtime-target"
            original_resolve = Path.resolve

            def redirected_resolve(path: Path, *args, **kwargs):  # noqa: ANN002, ANN003
                if path == state_root:
                    return resolved_target
                return original_resolve(path, *args, **kwargs)

            with mock.patch("pathlib.Path.resolve", new=redirected_resolve):
                adapter = FakeAdapter(workspace, state_root)

            self.assertEqual(adapter.state_root, state_root)

    def test_manager_state_classifies_runtime_links_as_insecure(self) -> None:
        for path_kind in ("state-root", "manager", "token"):
            with self.subTest(path_kind=path_kind), workspace_directory() as directory:
                workspace = Path(directory)
                config = create_config(workspace)
                adapter = FakeAdapter(workspace, config.state_root)
                initialize_runtime(config, adapter)
                context = resolve_runtime_context(config=config.config_path)
                if path_kind == "token":
                    identity = build_manager_identity(
                        config,
                        adapter,
                        operation_id="00000000000000000000000000000000",
                        instance_id="fixture-manager",
                        port=32123,
                        bootstrap_backend="fixture",
                        bootstrap_selection_reason="fixture",
                        runtime_fingerprint=fingerprint_module.compute_runtime_fingerprint(),
                    )
                    write_manager_identity(config, adapter, identity)
                unsafe_path = {
                    "state-root": config.state_root,
                    "manager": config.paths.manager,
                    "token": config.paths.token,
                }[path_kind]
                original_lstat = Path.lstat

                def fake_lstat(path: Path):
                    if path == unsafe_path:
                        return types.SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
                    return original_lstat(path)

                with mock.patch.object(Path, "lstat", fake_lstat):
                    status = ManagerStateResolver(
                        context,
                        adapter_factory=lambda *_: adapter,
                    ).resolve()
                self.assertEqual(status.state, "runtime_insecure")

    def test_state_store_validates_process_state_path_before_missing_rebuild(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            adapter.secure_directory(config.state_root)
            original_lstat = Path.lstat

            def fake_lstat(path: Path):
                if path == config.paths.processes:
                    return types.SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)
                return original_lstat(path)

            with mock.patch.object(Path, "lstat", fake_lstat):
                with self.assertRaises(RuntimeInsecureError):
                    StateStore(config, adapter).load()
            self.assertFalse(config.paths.processes.exists())

    def test_initialize_runtime_rejects_legacy_pid_link_before_exists(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            legacy_pid = config.state_root / "manager.pid"
            original_lstat = Path.lstat

            def fake_lstat(path: Path):
                if path == legacy_pid:
                    return types.SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
                return original_lstat(path)

            with mock.patch.object(Path, "lstat", fake_lstat):
                with self.assertRaises(RuntimeInsecureError):
                    initialize_runtime(config, adapter)

    @staticmethod
    def _runtime_tree(workspace: Path) -> tuple[Path, Path, Path]:
        scripts = workspace / "scripts"
        package = scripts / "process_manager"
        package.mkdir(parents=True)
        manager = scripts / "manager_server.py"
        module = package / "__init__.py"
        manager.write_text("VALUE = 1\n", encoding="utf-8")
        module.write_text("PACKAGE = 1\n", encoding="utf-8")
        return scripts, manager, module

    def test_acl_accepts_safe_inherited_equivalent(self) -> None:
        current_sid = "S-1-5-21-1000"
        snapshot = AclSnapshot(
            current_sid,
            (
                AclEntry(current_sid, FILE_ALL_ACCESS, GRANT_ACCESS, 0),
                AclEntry("S-1-5-18", FILE_ALL_ACCESS, GRANT_ACCESS, 3),
                AclEntry("S-1-5-32-544", FILE_ALL_ACCESS, GRANT_ACCESS, 3),
            ),
            FILE_ALL_ACCESS,
        )
        validate_acl_snapshot(snapshot, current_sid)

    def test_acl_accepts_narrow_restricting_sid_but_rejects_broad_one(self) -> None:
        current_sid = "S-1-5-21-1000"
        restricting_sid = "S-1-5-21-2000"
        snapshot = AclSnapshot(
            current_sid,
            (
                AclEntry(current_sid, FILE_ALL_ACCESS, GRANT_ACCESS, 0),
                AclEntry(restricting_sid, FILE_ALL_ACCESS, GRANT_ACCESS, 0),
            ),
            FILE_ALL_ACCESS,
        )
        validate_acl_snapshot(snapshot, current_sid, (restricting_sid,))
        with self.assertRaises(EnvironmentUnverifiableError):
            validate_acl_snapshot(snapshot, current_sid, ("S-1-1-0",))

    def test_acl_rejects_broad_allow_and_insufficient_rights(self) -> None:
        current_sid = "S-1-5-21-1000"
        broad = AclSnapshot(
            current_sid,
            (AclEntry("S-1-1-0", FILE_ALL_ACCESS, GRANT_ACCESS, 0),),
            FILE_ALL_ACCESS,
        )
        insufficient = AclSnapshot(current_sid, (), FILE_ALL_ACCESS & ~1)
        with self.assertRaises(RuntimeInsecureError):
            validate_acl_snapshot(broad, current_sid)
        with self.assertRaises(RuntimeInsecureError):
            validate_acl_snapshot(insufficient, current_sid)

    def test_acl_unknown_evidence_and_access_denied_remain_typed(self) -> None:
        current_sid = "S-1-5-21-1000"
        unknown = AclSnapshot(
            current_sid,
            (AclEntry(current_sid, FILE_ALL_ACCESS, 99, 0),),
            FILE_ALL_ACCESS,
        )
        with self.assertRaises(EnvironmentUnverifiableError):
            validate_acl_snapshot(unknown, current_sid)
        with self.assertRaises(RuntimePermissionDeniedError):
            WindowsAcl._raise_win_error("fixture descriptor", 5)

    def test_acl_verification_is_read_only(self) -> None:
        current_sid = "S-1-5-21-1000"
        snapshot = AclSnapshot(current_sid, (), FILE_ALL_ACCESS)
        events: list[str] = []
        acl = object.__new__(WindowsAcl)
        setattr(
            acl,
            "_validate_path",
            lambda path, *, directory: events.append(f"validate:{path.name}:{directory}"),
        )
        setattr(acl, "_read_snapshot", lambda path: events.append(f"read:{path.name}") or snapshot)
        setattr(acl, "_current_sid", lambda: events.append("sid") or current_sid)
        setattr(acl, "_restricted_sids", lambda: ())
        acl.verify_file(Path("runtime.json"))
        self.assertEqual(events, ["validate:runtime.json:False", "read:runtime.json", "sid"])

    @unittest.skipUnless(sys.platform.startswith("win"), "仅 Windows 验证原生 ACL 生命周期")
    def test_windows_acl_supports_current_restricted_token(self) -> None:
        with workspace_directory() as directory:
            runtime = Path(directory) / "secure-runtime"
            acl = WindowsAcl()
            acl.secure_directory(runtime)
            current_sid = acl._current_sid()
            restricted_sids = acl._restricted_sids()
            snapshot = acl._read_snapshot(runtime)
            validate_acl_snapshot(snapshot, current_sid, restricted_sids)
            granted = {
                entry.sid
                for entry in snapshot.entries
                if entry.access_mode == GRANT_ACCESS and entry.mask
            }
            self.assertTrue({current_sid, *restricted_sids}.issubset(granted))

    def test_acl_classification_never_uses_error_text(self) -> None:
        evidence = empty_evidence()
        state = runtime_failure_state(
            SupervisorError("unrelated command says ACL access denied"),
            evidence,
            default="corrupt",
        )
        self.assertEqual(state, "environment_unverifiable")
        typed_state = runtime_failure_state(
            RuntimePermissionDeniedError("typed"),
            empty_evidence(),
            default="corrupt",
        )
        self.assertEqual(typed_state, "runtime_permission_denied")

    def test_runtime_fingerprint_is_deterministic_and_content_bound(self) -> None:
        with workspace_directory() as directory:
            scripts, _, module = self._runtime_tree(Path(directory))
            first = fingerprint_module.compute_runtime_fingerprint(scripts)
            second = fingerprint_module.compute_runtime_fingerprint(scripts)
            self.assertEqual(first, second)
            module.write_text("PACKAGE = 2\n", encoding="utf-8")
            self.assertNotEqual(first, fingerprint_module.compute_runtime_fingerprint(scripts))

    def test_runtime_fingerprint_rejects_two_pass_drift(self) -> None:
        with workspace_directory() as directory:
            scripts, _, module = self._runtime_tree(Path(directory))
            reads = 0

            def drifting_reader(path: Path) -> bytes:
                nonlocal reads
                reads += 1
                if reads == 3:
                    module.write_text("PACKAGE = 2\n", encoding="utf-8")
                return path.read_bytes()

            with self.assertRaises(EnvironmentUnverifiableError):
                fingerprint_module.compute_runtime_fingerprint(scripts, reader=drifting_reader)

    def test_runtime_fingerprint_rejects_links_and_reparse_points(self) -> None:
        with workspace_directory() as directory:
            scripts, manager, module = self._runtime_tree(Path(directory))
            package = module.parent
            original_lstat = Path.lstat
            cases = (
                (manager, stat.S_IFLNK, 0),
                (package, stat.S_IFDIR, fingerprint_module.FILE_ATTRIBUTE_REPARSE_POINT),
            )
            for unsafe_path, mode, attributes in cases:
                with self.subTest(path=unsafe_path.name):
                    def fake_lstat(path: Path):
                        if path == unsafe_path:
                            return types.SimpleNamespace(
                                st_mode=mode,
                                st_file_attributes=attributes,
                            )
                        return original_lstat(path)

                    with mock.patch.object(Path, "lstat", fake_lstat):
                        with self.assertRaises(EnvironmentUnverifiableError):
                            fingerprint_module.compute_runtime_fingerprint(scripts)

    def test_runtime_fingerprint_enforces_all_bounds(self) -> None:
        with workspace_directory() as directory:
            scripts, _, _ = self._runtime_tree(Path(directory))
            (scripts / "process_manager" / "ignored.txt").write_text("ignored\n", encoding="utf-8")
            limits = (
                ("MAX_FILES", 1),
                ("MAX_DISCOVERED_ENTRIES", 1),
                ("MAX_FILE_BYTES", 1),
                ("MAX_TOTAL_BYTES", 1),
            )
            for name, value in limits:
                with self.subTest(limit=name), mock.patch.object(fingerprint_module, name, value):
                    with self.assertRaises(EnvironmentUnverifiableError):
                        fingerprint_module.compute_runtime_fingerprint(scripts)

    def test_runtime_lock_rejects_reparse_ancestor_before_open(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            config.paths.control.mkdir(parents=True)
            original_lstat = Path.lstat

            def fake_lstat(path: Path):
                if path == config.paths.control:
                    return types.SimpleNamespace(
                        st_mode=stat.S_IFDIR,
                        st_file_attributes=0x400,
                    )
                return original_lstat(path)

            with (
                mock.patch.object(Path, "lstat", fake_lstat),
                mock.patch("process_manager.runtime.os.open") as open_file,
            ):
                with self.assertRaises(RuntimeInsecureError):
                    prepare_runtime_lock(config.paths.operation_lock, adapter)
            open_file.assert_not_called()
            self.assertFalse(config.paths.operation_lock.exists())

    def test_owner_finalizers_share_one_monotonic_deadline(self) -> None:
        class StubbornOwner:
            @staticmethod
            def is_empty() -> bool:
                return False

            @staticmethod
            def graceful_stop() -> bool:
                return False

            @staticmethod
            def force_stop() -> bool:
                return False

            @staticmethod
            def close() -> None:
                return

        with workspace_directory() as directory:
            workspace = Path(directory)
            adapter = FakeAdapter(workspace, workspace / "state")
            finalizer = OwnerFinalizer(adapter)
            deadline = time.monotonic() + 0.05
            started = time.monotonic()
            first = finalizer.finalize_live(StubbornOwner(), grace_seconds=10, deadline=deadline)
            second = finalizer.finalize_live(StubbornOwner(), grace_seconds=10, deadline=deadline)
            elapsed = time.monotonic() - started
            self.assertFalse(first.owner_empty)
            self.assertFalse(second.owner_empty)
            self.assertLess(elapsed, 0.5)

    def test_runtime_fingerprint_drift_closes_operation_identity_and_health(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            context = resolve_runtime_context(config=config.config_path)
            store = operation_store(context, adapter)
            operation = store.create(
                "ensure",
                timeout=30,
                expected_runtime_fingerprint="a" * 64,
                expected_work_generation=None,
            )
            store.write(operation)
            operation_drift = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
                fingerprint_factory=lambda: "b" * 64,
            ).resolve()
            self.assertEqual(operation_drift.state, "stale")

        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            context = resolve_runtime_context(config=config.config_path)
            identity = build_manager_identity(
                config,
                adapter,
                operation_id="00000000000000000000000000000000",
                instance_id="fixture-manager",
                port=32123,
                bootstrap_backend="fixture",
                bootstrap_selection_reason="fixture",
                runtime_fingerprint="a" * 64,
            )
            write_manager_identity(config, adapter, identity)
            identity_drift = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
                fingerprint_factory=lambda: "b" * 64,
            ).resolve()
            self.assertEqual(identity_drift.state, "stale")

            class MismatchedHealthClient:
                def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002,ANN003
                    pass

                def request(self, method, path):  # noqa: ANN001,ANN201
                    return 200, {
                        "ok": True,
                        "data": {
                            "managerReady": True,
                            "instance": {"id": "fixture-manager"},
                            "operationId": identity["operationId"],
                            "runtimeFingerprint": "b" * 64,
                        },
                    }

            health_drift = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
                client_factory=MismatchedHealthClient,
                fingerprint_factory=lambda: "a" * 64,
            ).resolve()
            self.assertEqual(health_drift.state, "corrupt")

    def test_owner_inspection_error_never_commits_terminal_state(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = InspectionFailureAdapter(workspace, config.state_root)
            adapter.secure_directory(config.paths.runs)
            store = StateStore(config, adapter)
            store.load()
            service = create_service(workspace, config)
            record = store.reserve(service, manager_instance_id="old-manager", capability_hash="hash")
            host = types.SimpleNamespace(pid=101, returncode=None)
            owner = adapter.create_run_owner(record["processId"], host, "hash")
            owner.bind_target({"pid": 202})
            store.update(
                record["processKey"],
                status="running",
                internal_updates={
                    "owner": owner.internal_identity(),
                    "hostIdentity": adapter.process_identity(101),
                    "targetIdentity": adapter.process_identity(202),
                },
            )
            result = RunFinalizationCoordinator(store, adapter, "new-manager").reconcile_manager_loss()
            pending = store.get(key=record["processKey"])
            self.assertEqual(result["pending"], [record["processKey"]])
            self.assertEqual(pending["status"], "terminating")
            self.assertEqual(pending["public"]["cleanupError"], "owner_inspection_failed")
            self.assertFalse(pending["public"]["ownerEmpty"])

    def test_host_state_enriches_exact_owner_and_target_evidence(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            adapter.secure_directory(config.paths.runs)
            store = StateStore(config, adapter)
            store.load()
            service = create_service(workspace, config)
            record = store.reserve(service, manager_instance_id="old-manager", capability_hash="hash")
            host = types.SimpleNamespace(pid=101, returncode=None)
            owner = adapter.create_run_owner(record["processId"], host, "hash")
            host_state = Path(record["runDir"]) / "host-state.json"
            persisted_owner = owner.internal_identity()
            exact_owner = {**persisted_owner, "targetProcessGroup": 202}
            store.update(
                record["processKey"],
                status="starting",
                internal_updates={
                    "owner": persisted_owner,
                    "hostIdentity": adapter.process_identity(101),
                    "targetIdentity": None,
                    "hostState": str(host_state),
                },
            )
            write_json(
                host_state,
                {
                    "schema": "process-manager",
                    "runId": record["processId"],
                    "managerInstanceId": "old-manager",
                    "capabilityHash": "hash",
                    "hostPid": 101,
                    "target": {"pid": 202, "pgid": 202},
                    "targetIdentity": adapter.process_identity(202),
                    "ownerIdentity": exact_owner,
                    "state": "running",
                    "startedAt": "2026-07-17T00:00:00+00:00",
                },
            )
            owner.empty = True

            result = RunFinalizationCoordinator(store, adapter, "new-manager").reconcile_manager_loss()
            finalized = store.get(key=record["processKey"])
            self.assertEqual(result["finalized"], [record["processKey"]])
            self.assertEqual(finalized["internal"]["targetIdentity"], adapter.process_identity(202))
            self.assertEqual(finalized["internal"]["owner"], exact_owner)

    def test_doctor_does_not_claim_supervisor_ready_when_manager_is_unavailable(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            output = io.StringIO()
            with (
                mock.patch.object(pm_doctor, "load_manager_config", return_value=config),
                mock.patch.object(pm_doctor, "select_platform_adapter", return_value=adapter),
                mock.patch.object(
                    pm_doctor.ManagerClient,
                    "request",
                    side_effect=ManagerOfflineError("fixture offline"),
                ),
                redirect_stdout(output),
            ):
                result = pm_doctor.main(["--config", str(config.config_path)])
            payload = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertFalse(payload["data"]["managerReady"])
            self.assertFalse(payload["data"]["supervisorReady"])

    def test_exact_manager_termination_refuses_identity_mismatch(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            expected = adapter.process_identity(101)
            adapter.identity_valid = False
            self.assertFalse(adapter.terminate_manager(expected, timeout=1))
            self.assertEqual(adapter.manager_terminations, 0)


if __name__ == "__main__":
    unittest.main()
