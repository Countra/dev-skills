from __future__ import annotations

import copy
import threading
import time
import unittest
import sys
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, create_service, workspace_directory
from process_manager.bootstrap import BootstrapResult, ManagerBootstrap, write_bootstrap_capture
from process_manager.errors import (
    ConflictError,
    EnvironmentUnverifiableError,
    IdentityError,
    ManagerOfflineError,
    ManagerUnresponsiveError,
    OperationConflictError,
    OperationTimeoutError,
    RestartConfirmationRequiredError,
    RuntimeInsecureError,
    RuntimePermissionDeniedError,
    RuntimeCorruptError,
    RuntimeUninitializedError,
)
from process_manager.manager_lifecycle import ManagerConverger
from process_manager.manager_state import ManagerStateResolver
from process_manager.runtime import (
    OperationStore,
    build_manager_identity,
    initialize_runtime,
    read_manager_identity_record,
    write_manager_identity,
)
from process_manager.runtime_context import resolve_runtime_context
from process_manager.runtime_fingerprint import compute_runtime_fingerprint
from process_manager.state import StateStore


TEST_RUNTIME_FINGERPRINT = compute_runtime_fingerprint()
TEST_OPERATION_ID = "00000000000000000000000000000000"


def operation_id_from_factory(factory) -> str:  # noqa: ANN001
    command = factory("fixture", "fixture")
    return str(command[command.index("--operation-id") + 1])


def operation_store(context, adapter):  # noqa: ANN001,ANN201
    if context.config is None or context.config_digest is None:
        raise AssertionError("fixture runtime 尚未初始化")
    return OperationStore(
        context.config,
        adapter,
        workspace_digest=context.workspace_digest,
        expected_config_digest=context.config_digest,
    )


def create_operation(store, kind, timeout):  # noqa: ANN001,ANN201
    return store.create(
        kind,
        timeout=timeout,
        expected_runtime_fingerprint=(
            TEST_RUNTIME_FINGERPRINT if kind in {"ensure", "restart"} else None
        ),
        expected_work_generation=0 if kind in {"stop", "restart"} else None,
    )


class ReadyClient:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002,ANN003
        del kwargs
        self.config, self.adapter = args[:2]

    def request(self, method, path):  # noqa: ANN001,ANN201
        self.assert_request(method, path)
        identity = read_manager_identity_record(self.config, self.adapter)
        return 200, {
            "ok": True,
            "data": {
                "managerReady": True,
                "instance": {"id": identity["instanceId"]},
                "operationId": identity["operationId"],
                "runtimeFingerprint": identity["runtimeFingerprint"],
            },
        }

    @staticmethod
    def assert_request(method: str, path: str) -> None:
        if (method, path) != ("GET", "/health"):
            raise AssertionError(f"unexpected request: {method} {path}")


class OfflineClient(ReadyClient):
    def request(self, method, path):  # noqa: ANN001,ANN201
        self.assert_request(method, path)
        raise ManagerOfflineError("fixture endpoint offline")


class ManagerLifecycleTests(unittest.TestCase):
    def make_control_fixture(self, workspace: Path, *, endpoint_online: bool = True):  # noqa: ANN201
        config = create_config(workspace)
        context = resolve_runtime_context(config=config.config_path)
        adapter = FakeAdapter(workspace, config.state_root)
        initialize_runtime(config, adapter)
        state = StateStore(config, adapter)
        state.load()
        control = {"online": endpoint_online, "launches": 0, "shutdowns": 0}
        old_identity = build_manager_identity(
            config,
            adapter,
            operation_id=TEST_OPERATION_ID,
            instance_id="old-manager",
            port=32123,
            bootstrap_backend="fixture",
            bootstrap_selection_reason="fixture",
            runtime_fingerprint=TEST_RUNTIME_FINGERPRINT,
        )
        write_manager_identity(config, adapter, old_identity)

        class ControlClient:
            def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002,ANN003
                del args, kwargs

            def request(self, method, path, payload=None):  # noqa: ANN001,ANN201
                if (method, path) == ("GET", "/health"):
                    if not control["online"]:
                        raise ManagerOfflineError("fixture endpoint offline")
                    identity = read_manager_identity_record(config, adapter)
                    return 200, {
                        "ok": True,
                        "data": {
                            "managerReady": True,
                            "instance": {"id": identity["instanceId"]},
                            "operationId": identity["operationId"],
                            "runtimeFingerprint": identity["runtimeFingerprint"],
                        },
                    }
                if (
                    (method, path) == ("POST", "/shutdown")
                    and isinstance(payload, dict)
                    and set(payload) == {"operationId", "timeoutSeconds"}
                    and isinstance(payload["operationId"], str)
                    and isinstance(payload["timeoutSeconds"], float)
                    and payload["timeoutSeconds"] > 0
                ):
                    control["shutdowns"] += 1
                    control["online"] = False
                    adapter.identity_valid = False
                    config.paths.manager.unlink(missing_ok=True)
                    return 200, {
                        "ok": True,
                        "data": {
                            "shutdownAccepted": True,
                            "operationId": payload["operationId"],
                        },
                    }
                raise AssertionError(f"unexpected request: {method} {path}")

        class ControlBootstrap(ManagerBootstrap):
            def start(self, factory, **kwargs):  # noqa: ANN001,ANN201
                del kwargs
                control["launches"] += 1
                control["online"] = True
                adapter.identity_valid = True
                identity = build_manager_identity(
                    config,
                    adapter,
                    operation_id=operation_id_from_factory(factory),
                    instance_id=f"new-manager-{control['launches']}",
                    port=32124,
                    bootstrap_backend="fixture",
                    bootstrap_selection_reason="fixture",
                    runtime_fingerprint=TEST_RUNTIME_FINGERPRINT,
                )
                write_manager_identity(config, adapter, identity)
                return BootstrapResult("fixture", "fixture", None)

            def cleanup(self, backend):  # noqa: ANN001,ANN201
                del backend
                return True

            def residue_present(self) -> bool:
                return False

        converger = ManagerConverger(
            context,
            adapter_factory=lambda *_: adapter,
            client_factory=ControlClient,
            bootstrap_factory=ControlBootstrap,
        )
        return config, context, adapter, state, control, converger

    def test_ensure_rejects_unbounded_timeout_without_runtime_write(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            for timeout in (float("nan"), float("inf"), float("-inf"), 3600.1, True):
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    ManagerConverger(context).ensure(timeout=timeout)
            self.assertFalse(config.paths.operation_lock.exists())
            self.assertFalse(config.paths.operation.exists())

    def test_uninitialized_status_and_ensure_do_not_create_runtime(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            context = resolve_runtime_context(workspace=workspace)
            status = ManagerStateResolver(context).resolve()
            self.assertEqual(status.state, "absent")
            self.assertEqual(status.recommended_action, "init")
            with self.assertRaises(RuntimeUninitializedError):
                ManagerConverger(context).ensure()
            self.assertFalse((workspace / ".harness").exists())

    def test_initialized_absent_and_pending_status_are_pure_reads(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            absent = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
            ).resolve()
            self.assertEqual(absent.state, "absent")
            self.assertEqual(absent.recommended_action, "ensure")

            initialize_runtime(config, adapter)
            store = operation_store(context, adapter)
            operation = create_operation(store, "ensure", 30)
            store.write(operation)
            before = {
                path.relative_to(config.state_root).as_posix(): path.read_bytes()
                for path in config.state_root.rglob("*")
                if path.is_file()
            }
            pending = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
            ).resolve()
            after = {
                path.relative_to(config.state_root).as_posix(): path.read_bytes()
                for path in config.state_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(pending.state, "starting")
            self.assertEqual(pending.operation["checkpoint"], "start-requested")
            self.assertEqual(before, after)

            stopping_operation = create_operation(store, "stop", 30)
            store.write(stopping_operation)
            stopping = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
            ).resolve()
            self.assertEqual(stopping.state, "stopping")
            self.assertEqual(stopping.operation["checkpoint"], "stop-requested")

    def test_exact_identity_distinguishes_ready_stale_and_unresponsive(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            identity = build_manager_identity(
                config,
                adapter,
                operation_id=TEST_OPERATION_ID,
                instance_id="fixture-manager",
                port=32123,
                bootstrap_backend="fixture",
                bootstrap_selection_reason="fixture",
                runtime_fingerprint=TEST_RUNTIME_FINGERPRINT,
            )
            write_manager_identity(config, adapter, identity)
            ready = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
                client_factory=ReadyClient,
            ).resolve()
            self.assertEqual(ready.state, "ready")
            self.assertTrue(ready.evidence["instanceMatched"])

            unresponsive = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
                client_factory=OfflineClient,
            ).resolve()
            self.assertEqual(unresponsive.state, "unresponsive")
            adapter.identity_valid = False
            stale = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
                client_factory=ReadyClient,
            ).resolve()
            self.assertEqual(stale.state, "stale")

    def test_runtime_failures_map_to_closed_states(self) -> None:
        cases = (
            (RuntimeInsecureError("fixture"), "runtime_insecure", False),
            (
                RuntimePermissionDeniedError("fixture"),
                "runtime_permission_denied",
                None,
            ),
            (
                EnvironmentUnverifiableError("fixture"),
                "environment_unverifiable",
                None,
            ),
        )
        for failure, expected_state, expected_secure in cases:
            with self.subTest(expected_state=expected_state), workspace_directory() as directory:
                workspace = Path(directory)
                config = create_config(workspace)

                class FailingAdapter(FakeAdapter):
                    def verify_file(self, path):  # noqa: ANN001,ANN201
                        del path
                        raise failure

                adapter = FailingAdapter(workspace, config.state_root)
                context = resolve_runtime_context(config=config.config_path)
                status = ManagerStateResolver(
                    context,
                    adapter_factory=lambda *_: adapter,
                ).resolve()
                self.assertEqual(status.state, expected_state)
                self.assertEqual(status.evidence["runtimeSecure"], expected_secure)

    def test_bootstrap_residue_without_identity_is_stale_and_read_only(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)

            class ResidueBootstrap:
                def __init__(self, current_config, current_adapter) -> None:  # noqa: ANN001
                    del current_config, current_adapter

                def residue_present(self) -> bool:
                    return True

            before = {
                path.relative_to(config.state_root).as_posix(): path.read_bytes()
                for path in config.state_root.rglob("*")
                if path.is_file()
            }
            status = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
                bootstrap_factory=ResidueBootstrap,
            ).resolve()
            after = {
                path.relative_to(config.state_root).as_posix(): path.read_bytes()
                for path in config.state_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(status.state, "stale")
            self.assertTrue(status.evidence["bootstrapResidue"])
            self.assertEqual(before, after)

    def test_pending_ready_operation_is_reconciled_without_second_launch(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            store = operation_store(context, adapter)
            pending = create_operation(store, "ensure", 30)
            store.write(pending)
            identity = build_manager_identity(
                config,
                adapter,
                operation_id=pending["operationId"],
                instance_id="recovered-manager",
                port=32123,
                bootstrap_backend="fixture",
                bootstrap_selection_reason="fixture",
                runtime_fingerprint=TEST_RUNTIME_FINGERPRINT,
            )
            write_manager_identity(config, adapter, identity)

            class ForbiddenBootstrap:
                def __init__(self, current_config, current_adapter) -> None:  # noqa: ANN001
                    del current_config, current_adapter

                def residue_present(self) -> bool:
                    return False

                def start(self, factory, **kwargs):  # noqa: ANN001,ANN201
                    del factory, kwargs
                    raise AssertionError("pending operation 不得启动第二个 manager")

            result = ManagerConverger(
                context,
                adapter_factory=lambda *_: adapter,
                client_factory=ReadyClient,
                bootstrap_factory=ForbiddenBootstrap,
            ).ensure(timeout=1)
            completed = store.read()
            self.assertFalse(result["changed"])
            self.assertEqual(result["operationId"], pending["operationId"])
            self.assertEqual(completed["state"], "succeeded")
            self.assertEqual(completed["checkpoint"], "endpoint-ready")
            self.assertEqual(completed["expectedInstanceId"], "recovered-manager")

    def test_pending_operation_rejects_different_ready_instance(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            store = operation_store(context, adapter)
            pending = create_operation(store, "ensure", 30)
            pending["expectedInstanceId"] = "expected-manager"
            store.write(pending)
            identity = build_manager_identity(
                config,
                adapter,
                operation_id=pending["operationId"],
                instance_id="unexpected-manager",
                port=32123,
                bootstrap_backend="fixture",
                bootstrap_selection_reason="fixture",
                runtime_fingerprint=TEST_RUNTIME_FINGERPRINT,
            )
            write_manager_identity(config, adapter, identity)
            with self.assertRaises(RuntimeCorruptError):
                ManagerConverger(
                    context,
                    adapter_factory=lambda *_: adapter,
                    client_factory=ReadyClient,
                ).ensure(timeout=1)
            self.assertEqual(store.read(), pending)

    def test_expired_start_receipt_never_terminates_a_foreign_instance(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            identity = build_manager_identity(
                config,
                adapter,
                operation_id=TEST_OPERATION_ID,
                instance_id="foreign-manager",
                port=32123,
                bootstrap_backend="fixture",
                bootstrap_selection_reason="fixture",
                runtime_fingerprint=TEST_RUNTIME_FINGERPRINT,
            )
            write_manager_identity(config, adapter, identity)
            store = operation_store(context, adapter)
            pending = create_operation(store, "ensure", 30)
            pending["expectedInstanceId"] = "expected-manager"
            store.write(pending)
            with (
                mock.patch.object(OperationStore, "expired", return_value=True),
                self.assertRaisesRegex(IdentityError, "operation|instance"),
            ):
                ManagerConverger(
                    context,
                    adapter_factory=lambda *_: adapter,
                    client_factory=ReadyClient,
                ).ensure(timeout=1)
            self.assertEqual(adapter.manager_terminations, 0)
            self.assertTrue(config.paths.manager.exists())
            self.assertEqual(store.read(), pending)

    def test_operation_store_rejects_invalid_checkpoint_and_terminal_shape(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            store = operation_store(context, adapter)
            operation = create_operation(store, "ensure", 30)
            invalid_checkpoint = {**operation, "checkpoint": "unknown"}
            invalid_terminal = {**operation, "state": "succeeded"}
            premature_success = {
                **operation,
                "state": "succeeded",
                "outcome": {"state": "ready"},
            }
            conflicting_success = {
                **operation,
                "state": "succeeded",
                "checkpoint": "endpoint-ready",
                "outcome": {"state": "ready"},
                "error": {"code": "unexpected"},
            }
            conflicting_failure = {
                **operation,
                "state": "failed",
                "outcome": {"state": "ready"},
                "error": {"code": "fixture"},
            }
            for invalid in (
                invalid_checkpoint,
                invalid_terminal,
                premature_success,
                conflicting_success,
                conflicting_failure,
            ):
                with self.subTest(invalid=invalid), self.assertRaises(RuntimeCorruptError):
                    store.write(invalid)

    def test_pending_runtime_verified_waits_without_second_launch(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            store = operation_store(context, adapter)
            pending = create_operation(store, "ensure", 30)
            pending["checkpoint"] = "runtime-verified"
            store.write(pending)
            launch_count = 0

            class NoLaunchBootstrap:
                def __init__(self, current_config, current_adapter) -> None:  # noqa: ANN001
                    del current_config, current_adapter

                def residue_present(self) -> bool:
                    return False

                def start(self, factory, **kwargs):  # noqa: ANN001,ANN201
                    nonlocal launch_count
                    del factory, kwargs
                    launch_count += 1
                    raise AssertionError("等待 pending operation 时不得重新启动")

            with self.assertRaises(OperationTimeoutError):
                ManagerConverger(
                    context,
                    adapter_factory=lambda *_: adapter,
                    client_factory=OfflineClient,
                    bootstrap_factory=NoLaunchBootstrap,
                ).ensure(timeout=0.03)
            self.assertEqual(launch_count, 0)
            self.assertEqual(store.read(), pending)

    def test_pending_start_requested_resumes_same_receipt_once(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            store = operation_store(context, adapter)
            pending = create_operation(store, "ensure", 30)
            store.write(pending)
            launches = 0

            class ResumingBootstrap:
                def __init__(self, current_config, current_adapter) -> None:  # noqa: ANN001
                    self.config = current_config
                    self.adapter = current_adapter

                def start(self, factory, **kwargs):  # noqa: ANN001,ANN201
                    nonlocal launches
                    del kwargs
                    launches += 1
                    identity = build_manager_identity(
                        self.config,
                        self.adapter,
                        operation_id=operation_id_from_factory(factory),
                        instance_id="resumed-manager",
                        port=32123,
                        bootstrap_backend="fixture",
                        bootstrap_selection_reason="fixture",
                        runtime_fingerprint=TEST_RUNTIME_FINGERPRINT,
                    )
                    write_manager_identity(self.config, self.adapter, identity)
                    return BootstrapResult("fixture", "fixture", None)

                def cleanup_residue(self, **kwargs):  # noqa: ANN003,ANN201
                    del kwargs
                    return True

                def residue_present(self) -> bool:
                    return False

            result = ManagerConverger(
                context,
                adapter_factory=lambda *_: adapter,
                client_factory=ReadyClient,
                bootstrap_factory=ResumingBootstrap,
            ).ensure(timeout=1)
            completed = store.read()
            self.assertEqual(launches, 1)
            self.assertEqual(result["operationId"], pending["operationId"])
            self.assertEqual(completed["state"], "succeeded")

    def test_expired_pending_without_identity_is_stale(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            store = operation_store(context, adapter)
            operation = create_operation(store, "ensure", 0.01)
            store.write(operation)
            time.sleep(0.03)
            status = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
            ).resolve()
            self.assertEqual(status.state, "stale")
            self.assertEqual(status.operation["operationId"], operation["operationId"])

    def test_fingerprint_drift_fails_old_receipt_and_cleans_exact_capture(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            store = operation_store(context, adapter)
            old = store.create(
                "ensure",
                timeout=30,
                expected_runtime_fingerprint="a" * 64,
                expected_work_generation=None,
            )
            old["checkpoint"] = "identity-published"
            old["expectedInstanceId"] = "expired-manager"
            store.write(old)
            write_bootstrap_capture(
                config,
                adapter,
                operation_id=old["operationId"],
                backend="fixture",
                runtime_fingerprint="a" * 64,
            )
            writes: list[dict] = []
            original_write = OperationStore.write

            def recording_write(current_store, value):  # noqa: ANN001,ANN201
                writes.append(copy.deepcopy(value))
                return original_write(current_store, value)

            class RecoveryBootstrap(ManagerBootstrap):
                def start(self, factory, **kwargs):  # noqa: ANN001,ANN201
                    del kwargs
                    adapter.identity_valid = True
                    identity = build_manager_identity(
                        config,
                        adapter,
                        operation_id=operation_id_from_factory(factory),
                        instance_id="fresh-manager",
                        port=32123,
                        bootstrap_backend="fixture",
                        bootstrap_selection_reason="fixture",
                        runtime_fingerprint="b" * 64,
                    )
                    write_manager_identity(config, adapter, identity)
                    return BootstrapResult("fixture", "fixture", None)

            with mock.patch.object(OperationStore, "write", recording_write):
                result = ManagerConverger(
                    context,
                    adapter_factory=lambda *_: adapter,
                    client_factory=ReadyClient,
                    bootstrap_factory=RecoveryBootstrap,
                    fingerprint_factory=lambda: "b" * 64,
                ).ensure(timeout=2)
            self.assertEqual(result["state"], "ready")
            self.assertEqual(adapter.manager_terminations, 1)
            self.assertFalse(config.paths.bootstrap.exists())
            self.assertTrue(
                any(
                    value["operationId"] == old["operationId"]
                    and value["state"] == "failed"
                    and value["error"]["code"] == "runtime_contract_changed"
                    for value in writes
                )
            )
            self.assertNotEqual(store.read()["operationId"], old["operationId"])
            self.assertEqual(store.read()["expectedRuntimeFingerprint"], "b" * 64)
            self.assertEqual(store.read()["expectedInstanceId"], "fresh-manager")

    def test_bootstrap_early_exit_records_failure_and_cleans_backend(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            cleaned: list[str] = []

            class FinishedProcess:
                @staticmethod
                def poll() -> int:
                    return 1

            class FailedBootstrap:
                def __init__(self, current_config, current_adapter) -> None:  # noqa: ANN001
                    del current_config, current_adapter

                def residue_present(self) -> bool:
                    return False

                def start(self, factory, **kwargs):  # noqa: ANN001,ANN201
                    del factory, kwargs
                    return BootstrapResult("fixture", "fixture", FinishedProcess())

                def cleanup(self, backend):  # noqa: ANN001,ANN201
                    cleaned.append(backend)
                    return True

                def cleanup_residue(self, *, timeout, preferred_backend=None):  # noqa: ANN001,ANN201
                    del timeout
                    return self.cleanup(preferred_backend)

            with self.assertRaises(ManagerUnresponsiveError):
                ManagerConverger(
                    context,
                    adapter_factory=lambda *_: adapter,
                    client_factory=OfflineClient,
                    bootstrap_factory=FailedBootstrap,
                ).ensure(timeout=1)
            failed = operation_store(context, adapter).read()
            self.assertEqual(failed["state"], "failed")
            self.assertEqual(failed["error"]["code"], "manager_unresponsive")
            self.assertTrue(failed["error"]["cleanupVerified"])
            self.assertEqual(cleaned, ["fixture"])

    def test_concurrent_ensure_launches_one_manager_operation(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            launch_count = 0
            launch_guard = threading.Lock()

            class FakeBootstrap:
                def __init__(self, current_config, current_adapter) -> None:  # noqa: ANN001
                    self.config = current_config
                    self.adapter = current_adapter

                def start(self, factory, **kwargs):  # noqa: ANN001,ANN201
                    nonlocal launch_count
                    del kwargs
                    with launch_guard:
                        launch_count += 1
                    time.sleep(0.1)
                    identity = build_manager_identity(
                        self.config,
                        self.adapter,
                        operation_id=operation_id_from_factory(factory),
                        instance_id="concurrent-manager",
                        port=32123,
                        bootstrap_backend="fixture",
                        bootstrap_selection_reason="fixture",
                        runtime_fingerprint=TEST_RUNTIME_FINGERPRINT,
                    )
                    write_manager_identity(self.config, self.adapter, identity)
                    return BootstrapResult("fixture", "fixture", None)

                def cleanup(self, backend):  # noqa: ANN001,ANN201
                    del backend
                    return True

                def residue_present(self) -> bool:
                    return False

            results: list[dict] = []
            failures: list[BaseException] = []

            def run_ensure() -> None:
                try:
                    results.append(
                        ManagerConverger(
                            context,
                            adapter_factory=lambda *_: adapter,
                            client_factory=ReadyClient,
                            bootstrap_factory=FakeBootstrap,
                        ).ensure(timeout=3)
                    )
                except BaseException as exc:  # noqa: BLE001
                    failures.append(exc)

            callers = [threading.Thread(target=run_ensure) for _ in range(2)]
            for caller in callers:
                caller.start()
            for caller in callers:
                caller.join(timeout=5)

            self.assertFalse(failures)
            self.assertEqual(launch_count, 1)
            self.assertEqual(len(results), 2)
            self.assertEqual(sorted(item["changed"] for item in results), [False, True])
            self.assertEqual(
                {item["manager"]["managerInstanceId"] for item in results},
                {"concurrent-manager"},
            )
            operation = operation_store(context, adapter).read()
            self.assertEqual(operation["state"], "succeeded")
            self.assertEqual(operation["expectedInstanceId"], "concurrent-manager")

    def test_manager_stop_is_idempotent_and_closes_phase_receipt(self) -> None:
        with workspace_directory() as directory:
            config, context, adapter, _, control, converger = self.make_control_fixture(Path(directory))
            stopped = converger.stop(timeout=2)
            self.assertEqual(stopped["state"], "absent")
            self.assertTrue(stopped["cleanup"]["ownersEmpty"])
            self.assertEqual(stopped["oldManagerInstanceId"], "old-manager")
            self.assertEqual(control["shutdowns"], 1)
            receipt = operation_store(context, adapter).read()
            self.assertEqual((receipt["state"], receipt["checkpoint"]), ("succeeded", "bootstrap-cleaned"))
            repeated = converger.stop(timeout=2)
            self.assertFalse(repeated["changed"])
            self.assertEqual(control["shutdowns"], 1)
            self.assertFalse(config.paths.manager.exists())

    def test_manager_stop_forwards_one_deadline_to_owner_reconciliation(self) -> None:
        with workspace_directory() as directory:
            _, _, _, _, _, converger = self.make_control_fixture(Path(directory))
            with mock.patch(
                "process_manager.manager_lifecycle.RunFinalizationCoordinator"
            ) as coordinator_type:
                coordinator_type.return_value.reconcile_manager_loss.return_value = {
                    "pending": [],
                }
                stopped = converger.stop(timeout=2)
            call = coordinator_type.return_value.reconcile_manager_loss.call_args
            self.assertEqual(
                call.kwargs["termination_operation_id"],
                stopped["operationId"],
            )
            self.assertGreater(call.kwargs["deadline"], time.monotonic())

    def test_pending_start_rejects_manager_link_before_recovery(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            store = operation_store(context, adapter)
            store.write(create_operation(store, "ensure", 30))
            original_lstat = Path.lstat

            def fake_lstat(path: Path):
                if path == config.paths.manager:
                    return mock.Mock(st_mode=0o120000, st_file_attributes=0)
                return original_lstat(path)

            with mock.patch.object(Path, "lstat", fake_lstat):
                with self.assertRaises(RuntimeInsecureError):
                    ManagerConverger(
                        context,
                        adapter_factory=lambda *_: adapter,
                    ).ensure(timeout=1)

    def test_manager_start_rejects_log_link_before_bootstrap(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            stdout_path = config.paths.logs / "manager-stdout.log"
            original_lstat = Path.lstat
            launches = 0

            class NoLaunchBootstrap:
                def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002,ANN003
                    del args, kwargs

                def residue_present(self) -> bool:
                    return False

                def start(self, factory, **kwargs):  # noqa: ANN001,ANN201
                    nonlocal launches
                    del factory, kwargs
                    launches += 1
                    raise AssertionError("不安全日志路径不得进入 bootstrap")

            def fake_lstat(path: Path):
                if path == stdout_path:
                    return mock.Mock(st_mode=0o120000, st_file_attributes=0)
                return original_lstat(path)

            with mock.patch.object(Path, "lstat", fake_lstat):
                with self.assertRaises(RuntimeInsecureError):
                    ManagerConverger(
                        context,
                        adapter_factory=lambda *_: adapter,
                        bootstrap_factory=NoLaunchBootstrap,
                    ).ensure(timeout=1)
            self.assertEqual(launches, 0)

    def test_ensure_clears_terminal_restart_fence_after_interruption(self) -> None:
        with workspace_directory() as directory:
            _, context, adapter, state, _, converger = self.make_control_fixture(Path(directory))
            store = operation_store(context, adapter)
            operation = create_operation(store, "restart", 2)
            store.write(operation)
            state.install_intake_fence(
                operation_id=operation["operationId"],
                kind="restart",
                expected_generation=operation["expectedWorkGeneration"],
            )
            operation = store.update(
                operation,
                checkpoint="endpoint-ready",
                expectedInstanceId="old-manager",
            )
            store.update(
                operation,
                state="succeeded",
                outcome={"state": "ready", "newManagerInstanceId": "old-manager"},
            )
            result = converger.ensure(timeout=1)
            self.assertEqual(result["state"], "ready")
            self.assertIsNone(state.work_summary()["intakeFence"])

    def test_manager_restart_does_not_restore_services(self) -> None:
        with workspace_directory() as directory:
            _, context, adapter, _, control, converger = self.make_control_fixture(Path(directory))
            restarted = converger.restart(timeout=2)
            self.assertEqual(restarted["oldManagerInstanceId"], "old-manager")
            self.assertEqual(restarted["newManagerInstanceId"], "new-manager-1")
            self.assertFalse(restarted["servicesRestored"])
            self.assertEqual(restarted["stoppedRunKeys"], [])
            self.assertEqual((control["shutdowns"], control["launches"]), (1, 1))
            receipt = operation_store(context, adapter).read()
            self.assertEqual((receipt["state"], receipt["checkpoint"]), ("succeeded", "endpoint-ready"))

    def test_manager_restart_requires_confirmation_before_mutation(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, _, _, state, control, converger = self.make_control_fixture(workspace)
            service = create_service(workspace, config)
            state.reserve(
                service, manager_instance_id="old-manager", capability_hash="hash",
                ownership={"kind": "persistent", "sessionId": None},
            )
            with self.assertRaises(RestartConfirmationRequiredError) as raised:
                converger.restart(timeout=2)
            self.assertIn("affectedRunKeys", raised.exception.diagnostics)
            self.assertFalse(config.paths.operation.exists())
            self.assertEqual((control["shutdowns"], control["launches"]), (0, 0))

    def test_destructive_confirmation_and_intake_fence_are_one_transaction(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            state = StateStore(config, adapter)
            state.load()
            producer_state = StateStore(config, adapter)
            service = create_service(workspace, config)
            converger = ManagerConverger(
                context,
                adapter_factory=lambda *_: adapter,
            )
            store = operation_store(context, adapter)
            started = threading.Event()
            finished = threading.Event()
            failures: list[BaseException] = []

            def reserve() -> None:
                started.set()
                try:
                    producer_state.reserve(
                        service,
                        manager_instance_id="producer",
                        capability_hash="hash",
                        ownership={"kind": "persistent", "sessionId": None},
                    )
                except BaseException as exc:  # noqa: BLE001
                    failures.append(exc)
                finally:
                    finished.set()

            producer = threading.Thread(target=reserve)
            original_install = state.install_intake_fence

            def install(**kwargs):  # noqa: ANN003,ANN201
                producer.start()
                self.assertTrue(started.wait(timeout=1))
                time.sleep(0.05)
                self.assertFalse(finished.is_set())
                return original_install(**kwargs)

            with mock.patch.object(state, "install_intake_fence", side_effect=install):
                operation, _ = converger._destructive_operation(  # noqa: SLF001
                    "restart",
                    store,
                    state,
                    timeout=2,
                    confirmed=False,
                )
            producer.join(timeout=2)
            self.assertEqual(operation["checkpoint"], "intake-closed")
            self.assertEqual(len(failures), 1)
            self.assertIsInstance(failures[0], ConflictError)

    def test_conditional_idle_stop_retains_manager_when_generation_changes(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, _, _, state, control, converger = self.make_control_fixture(workspace)
            generation = state.work_summary()["workGeneration"]
            state.reserve(
                create_service(workspace, config),
                manager_instance_id="producer",
                capability_hash="hash",
                ownership={"kind": "persistent", "sessionId": None},
            )
            with self.assertRaises(OperationConflictError):
                converger.stop(
                    timeout=2,
                    expected_work_generation=generation,
                    require_idle=True,
                )
            self.assertEqual(control["shutdowns"], 0)
            receipt = operation_store(converger.context, state.adapter).read()
            self.assertEqual(receipt["state"], "failed")

    def test_exact_unresponsive_restart_terminates_only_verified_manager(self) -> None:
        with workspace_directory() as directory:
            _, _, adapter, _, control, converger = self.make_control_fixture(
                Path(directory),
                endpoint_online=False,
            )
            restarted = converger.restart(timeout=2)
            self.assertEqual(adapter.manager_terminations, 1)
            self.assertEqual(control["shutdowns"], 0)
            self.assertEqual(restarted["newManagerInstanceId"], "new-manager-1")

    def test_destructive_operation_refuses_identity_replaced_after_fence(self) -> None:
        with workspace_directory() as directory:
            config, context, adapter, _, control, converger = self.make_control_fixture(Path(directory))
            original_stop_phase = converger._stop_phase  # noqa: SLF001

            def replace_identity(*args, **kwargs):  # noqa: ANN002,ANN003,ANN201
                identity = build_manager_identity(
                    config,
                    adapter,
                    operation_id=TEST_OPERATION_ID,
                    instance_id="foreign-manager",
                    port=32125,
                    bootstrap_backend="fixture",
                    bootstrap_selection_reason="fixture",
                    runtime_fingerprint=TEST_RUNTIME_FINGERPRINT,
                )
                write_manager_identity(config, adapter, identity)
                return original_stop_phase(*args, **kwargs)

            with (
                mock.patch.object(converger, "_stop_phase", side_effect=replace_identity),
                self.assertRaises(IdentityError),
            ):
                converger.stop(timeout=2)
            receipt = operation_store(context, adapter).read()
            self.assertEqual(receipt["expectedInstanceId"], "old-manager")
            self.assertEqual(read_manager_identity_record(config, adapter)["instanceId"], "foreign-manager")
            self.assertEqual((control["shutdowns"], adapter.manager_terminations), (0, 0))

    def test_restart_keeps_pending_receipt_when_owner_cannot_be_verified(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, context, adapter, state, control, converger = self.make_control_fixture(workspace)
            service = create_service(workspace, config)
            record = state.reserve(
                service, manager_instance_id="old-manager", capability_hash="hash",
                ownership={"kind": "persistent", "sessionId": None},
            )
            with self.assertRaises(ManagerUnresponsiveError):
                converger.restart(timeout=2, confirm_stop_owned_runs=True)
            current = state.get(key=record["processKey"])
            self.assertEqual(current["status"], "terminating")
            self.assertIn(record["service"], state.list_records()["active"])
            receipt = operation_store(context, adapter).read()
            self.assertEqual((receipt["state"], receipt["checkpoint"]), ("pending", "runs-terminating"))
            self.assertEqual(control["launches"], 0)

    def test_stop_resumes_interrupted_manager_stopped_phase(self) -> None:
        with workspace_directory() as directory:
            config, context, adapter, state, control, converger = self.make_control_fixture(Path(directory))
            store = operation_store(context, adapter)
            operation = create_operation(store, "stop", 2)
            store.write(operation)
            state.install_intake_fence(
                operation_id=operation["operationId"],
                kind="stop",
                expected_generation=operation["expectedWorkGeneration"],
            )
            store.update(
                operation,
                checkpoint="manager-stopped",
                expectedInstanceId="old-manager",
            )
            adapter.identity_valid = False
            config.paths.manager.unlink()
            stopped = converger.stop(timeout=2)
            self.assertEqual(stopped["state"], "absent")
            self.assertEqual(store.read()["state"], "succeeded")
            self.assertEqual(control["shutdowns"], 0)

    def test_expired_restart_replaces_exact_operation_bound_manager(self) -> None:
        with workspace_directory() as directory:
            config, context, adapter, state, control, converger = self.make_control_fixture(Path(directory))
            store = operation_store(context, adapter)
            operation = create_operation(store, "restart", 2)
            store.write(operation)
            state.install_intake_fence(
                operation_id=operation["operationId"],
                kind="restart",
                expected_generation=operation["expectedWorkGeneration"],
            )
            operation = store.update(
                operation,
                checkpoint="identity-published",
                expectedInstanceId="old-manager",
                replacementInstanceId="abandoned-replacement",
            )
            identity = build_manager_identity(
                config,
                adapter,
                operation_id=operation["operationId"],
                instance_id="abandoned-replacement",
                port=32124,
                bootstrap_backend="fixture",
                bootstrap_selection_reason="fixture",
                runtime_fingerprint=TEST_RUNTIME_FINGERPRINT,
            )
            write_manager_identity(config, adapter, identity)
            with mock.patch.object(OperationStore, "expired", return_value=True):
                restarted = converger.restart(timeout=2)
            self.assertEqual(restarted["oldManagerInstanceId"], "old-manager")
            self.assertEqual(restarted["newManagerInstanceId"], "new-manager-1")
            self.assertEqual((adapter.manager_terminations, control["launches"]), (1, 1))
            receipt = store.read()
            self.assertEqual(receipt["state"], "succeeded")
            self.assertEqual(receipt["replacementInstanceId"], "new-manager-1")

    def test_restart_resumes_identity_published_without_relaunch(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, context, adapter, state, control, converger = self.make_control_fixture(workspace)
            store = operation_store(context, adapter)
            service = create_service(workspace, config)
            record = state.reserve(
                service, manager_instance_id="old-manager", capability_hash="hash",
                ownership={"kind": "persistent", "sessionId": None},
            )
            operation = create_operation(store, "restart", 2)
            operation["expectedWorkGeneration"] = state.work_summary()["workGeneration"]
            store.write(operation)
            state.install_intake_fence(
                operation_id=operation["operationId"],
                kind="restart",
                expected_generation=operation["expectedWorkGeneration"],
            )
            state.update(
                record["processKey"],
                status="stopped",
                public_updates={
                    "terminationOperationId": operation["operationId"],
                    "ownerEmpty": True,
                    "cleanupVerified": True,
                },
                clear_active=True,
            )
            operation = store.update(
                operation,
                checkpoint="identity-published",
                expectedInstanceId="old-manager",
            )
            new_identity = build_manager_identity(
                config,
                adapter,
                operation_id=operation["operationId"],
                instance_id="new-manager-resumed",
                port=32124,
                bootstrap_backend="fixture",
                bootstrap_selection_reason="fixture",
                runtime_fingerprint=TEST_RUNTIME_FINGERPRINT,
            )
            write_manager_identity(config, adapter, new_identity)
            restarted = converger.restart(timeout=2)
            self.assertEqual(restarted["oldManagerInstanceId"], "old-manager")
            self.assertEqual(restarted["newManagerInstanceId"], "new-manager-resumed")
            self.assertEqual(restarted["stoppedRunKeys"], [record["processKey"]])
            self.assertEqual((control["shutdowns"], control["launches"]), (0, 0))

    def test_restart_waits_for_existing_bootstrap_instead_of_relaunching(self) -> None:
        with workspace_directory() as directory:
            config, context, adapter, _, control, converger = self.make_control_fixture(Path(directory))
            store = operation_store(context, adapter)
            operation = create_operation(store, "restart", 2)
            store.write(operation)
            state = StateStore(config, adapter)
            state.install_intake_fence(
                operation_id=operation["operationId"],
                kind="restart",
                expected_generation=operation["expectedWorkGeneration"],
            )
            store.update(
                operation,
                checkpoint="bootstrap-launched",
                expectedInstanceId="old-manager",
            )
            adapter.identity_valid = False
            control["online"] = False
            config.paths.manager.unlink()

            def publish_existing_manager() -> None:
                time.sleep(0.05)
                adapter.identity_valid = True
                control["online"] = True
                identity = build_manager_identity(
                    config,
                    adapter,
                    operation_id=operation["operationId"],
                    instance_id="new-manager-existing",
                    port=32124,
                    bootstrap_backend="fixture",
                    bootstrap_selection_reason="fixture",
                    runtime_fingerprint=TEST_RUNTIME_FINGERPRINT,
                )
                write_manager_identity(config, adapter, identity)

            publisher = threading.Thread(target=publish_existing_manager)
            publisher.start()
            try:
                restarted = converger.restart(timeout=2)
            finally:
                publisher.join(timeout=2)
            self.assertEqual(restarted["oldManagerInstanceId"], "old-manager")
            self.assertEqual(restarted["newManagerInstanceId"], "new-manager-existing")
            self.assertEqual((control["shutdowns"], control["launches"]), (0, 0))

    def test_restart_receipt_reports_stopping_then_starting_checkpoint(self) -> None:
        with workspace_directory() as directory:
            _, context, adapter, _, _, _ = self.make_control_fixture(Path(directory))
            store = operation_store(context, adapter)
            operation = create_operation(store, "restart", 2)
            store.write(operation)
            stopping = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
                client_factory=ReadyClient,
            ).resolve()
            self.assertEqual(stopping.state, "stopping")
            adapter.identity_valid = False
            context.config.paths.manager.unlink()
            store.update(operation, checkpoint="runtime-verified")
            starting = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
                client_factory=ReadyClient,
            ).resolve()
            self.assertEqual(starting.state, "starting")


if __name__ == "__main__":
    unittest.main()
