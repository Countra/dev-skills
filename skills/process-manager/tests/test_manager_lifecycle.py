from __future__ import annotations

import threading
import time
import unittest
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, workspace_directory
from process_manager.bootstrap import BootstrapResult
from process_manager.errors import (
    EnvironmentUnverifiableError,
    ManagerOfflineError,
    ManagerUnresponsiveError,
    OperationTimeoutError,
    RuntimeInsecureError,
    RuntimePermissionDeniedError,
    RuntimeCorruptError,
    RuntimeUninitializedError,
)
from process_manager.manager_lifecycle import (
    ManagerConverger,
    ManagerStateResolver,
)
from process_manager.runtime import (
    OperationStore,
    build_manager_identity,
    initialize_runtime,
    write_manager_identity,
)
from process_manager.runtime_context import resolve_runtime_context


def operation_store(context, adapter):  # noqa: ANN001,ANN201
    if context.config is None or context.config_digest is None:
        raise AssertionError("fixture runtime 尚未初始化")
    return OperationStore(
        context.config,
        adapter,
        workspace_digest=context.workspace_digest,
        expected_config_digest=context.config_digest,
    )


class ReadyClient:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002,ANN003
        del args, kwargs

    def request(self, method, path):  # noqa: ANN001,ANN201
        self.assert_request(method, path)
        return 200, {"ok": True, "data": {"managerReady": True}}

    @staticmethod
    def assert_request(method: str, path: str) -> None:
        if (method, path) != ("GET", "/health"):
            raise AssertionError(f"unexpected request: {method} {path}")


class OfflineClient(ReadyClient):
    def request(self, method, path):  # noqa: ANN001,ANN201
        self.assert_request(method, path)
        raise ManagerOfflineError("fixture endpoint offline")


class ManagerLifecycleTests(unittest.TestCase):
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
            operation = store.create("ensure", timeout=30)
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

            stopping_operation = store.create("stop", timeout=30)
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
                instance_id="fixture-manager",
                port=32123,
                bootstrap_backend="fixture",
                bootstrap_selection_reason="fixture",
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
            identity = build_manager_identity(
                config,
                adapter,
                instance_id="recovered-manager",
                port=32123,
                bootstrap_backend="fixture",
                bootstrap_selection_reason="fixture",
            )
            write_manager_identity(config, adapter, identity)
            store = operation_store(context, adapter)
            pending = store.create("ensure", timeout=30)
            store.write(pending)

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
            identity = build_manager_identity(
                config,
                adapter,
                instance_id="unexpected-manager",
                port=32123,
                bootstrap_backend="fixture",
                bootstrap_selection_reason="fixture",
            )
            write_manager_identity(config, adapter, identity)
            store = operation_store(context, adapter)
            pending = store.create("ensure", timeout=30)
            pending["expectedInstanceId"] = "expected-manager"
            store.write(pending)
            with self.assertRaises(RuntimeCorruptError):
                ManagerConverger(
                    context,
                    adapter_factory=lambda *_: adapter,
                    client_factory=ReadyClient,
                ).ensure(timeout=1)
            self.assertEqual(store.read(), pending)

    def test_operation_store_rejects_invalid_checkpoint_and_terminal_shape(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            store = operation_store(context, adapter)
            operation = store.create("ensure", timeout=30)
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

    def test_pending_operation_timeout_does_not_launch_or_replace_receipt(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            store = operation_store(context, adapter)
            pending = store.create("ensure", timeout=30)
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

    def test_expired_pending_without_identity_is_stale(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            context = resolve_runtime_context(config=config.config_path)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            store = operation_store(context, adapter)
            operation = store.create("ensure", timeout=0.01)
            store.write(operation)
            time.sleep(0.03)
            status = ManagerStateResolver(
                context,
                adapter_factory=lambda *_: adapter,
            ).resolve()
            self.assertEqual(status.state, "stale")
            self.assertEqual(status.operation["operationId"], operation["operationId"])

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
                    del factory, kwargs
                    with launch_guard:
                        launch_count += 1
                    time.sleep(0.1)
                    identity = build_manager_identity(
                        self.config,
                        self.adapter,
                        instance_id="concurrent-manager",
                        port=32123,
                        bootstrap_backend="fixture",
                        bootstrap_selection_reason="fixture",
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


if __name__ == "__main__":
    unittest.main()
