"""公共 CLI 的异常与输出适配。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .errors import LabError
from .output import failure, print_json, success


def run_cli(
    operation: str,
    handler: Callable[[], Any],
    *,
    pretty: bool = False,
) -> int:
    try:
        print_json(success(operation, handler()), pretty=pretty)
        return 0
    except LabError as exc:
        print_json(failure(operation, exc), pretty=pretty)
        return exc.exit_code
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        print_json(failure(operation, exc), pretty=pretty)
        return 1
