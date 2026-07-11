from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


STOP = False


def request_stop(signum, frame) -> None:  # noqa: ANN001
    del signum, frame
    global STOP
    STOP = True


def install_handlers(*, ignore: bool = False) -> None:
    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        value = getattr(signal, name, None)
        if value is not None:
            signal.signal(value, signal.SIG_IGN if ignore else request_stop)


def child_main(*, ignore: bool) -> int:
    install_handlers(ignore=ignore)
    while not STOP:
        time.sleep(0.1)
    return 0


def spawn_child(*, ignore: bool) -> subprocess.Popen[bytes]:
    command = [sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()), "--child"]
    if ignore:
        command.append("--ignore-signals")
    return subprocess.Popen(command, stdin=subprocess.DEVNULL)


def write_identity(identity_path: Path, child: subprocess.Popen[bytes]) -> None:
    identity_path.write_text(
        json.dumps({"parentPid": os.getpid(), "childPid": child.pid}),
        encoding="utf-8",
    )


def parent_main(identity_path: Path, mode: str) -> int:
    ignore = mode == "ignore-signal"
    install_handlers(ignore=ignore)
    child = spawn_child(ignore=ignore)
    write_identity(identity_path, child)
    if mode == "background-child":
        print("background-child-started", flush=True)
        time.sleep(0.5)
        return 0
    if mode == "exit-failure":
        print("fixture-exit=23", flush=True)
        time.sleep(0.5)
        child.terminate()
        child.wait(timeout=3)
        return 23
    if mode == "large-log":
        for index in range(4096):
            print(f"large-log-{index:05d}-" + ("x" * 96), flush=True)
        print("large-log-ready", flush=True)
    elif mode == "dynamic-port":
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(0.1)
        print(f"service-url=http://127.0.0.1:{listener.getsockname()[1]}", flush=True)
        try:
            while not STOP:
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    continue
                connection.close()
        finally:
            listener.close()
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=3)
        return 0
    else:
        print("service-ready", flush=True)
    print(f"secret={os.environ.get('PM_SMOKE_SECRET', '')}", flush=True)
    try:
        while not STOP:
            time.sleep(0.1)
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("identity", nargs="?", type=Path)
    parser.add_argument(
        "--mode",
        choices=("normal", "ignore-signal", "dynamic-port", "large-log", "exit-failure", "background-child"),
        default="normal",
    )
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--ignore-signals", action="store_true")
    args = parser.parse_args()
    if args.child:
        return child_main(ignore=args.ignore_signals)
    if args.identity is None:
        parser.error("identity is required")
    return parent_main(args.identity.resolve(), args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
