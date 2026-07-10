"""readiness 日志使用的有界正则子集。"""

from __future__ import annotations

import re
from typing import Any

from .errors import ValidationError


_CONSTANTS = re._constants  # type: ignore[attr-defined]  # stdlib parser 与当前 re 引擎保持一致
_PARSER = re._parser  # type: ignore[attr-defined]
_REPEATS = {
    _CONSTANTS.MAX_REPEAT,
    _CONSTANTS.MIN_REPEAT,
    getattr(_CONSTANTS, "POSSESSIVE_REPEAT", object()),
}
_ATOMS = {
    _CONSTANTS.LITERAL,
    _CONSTANTS.NOT_LITERAL,
    _CONSTANTS.ANY,
    _CONSTANTS.IN,
    _CONSTANTS.CATEGORY,
}
_IN_OPS = {
    _CONSTANTS.LITERAL,
    _CONSTANTS.NOT_LITERAL,
    _CONSTANTS.RANGE,
    _CONSTANTS.NEGATE,
    _CONSTANTS.CATEGORY,
}


def _validate_tokens(tokens: Any) -> None:
    previous_repeat = False
    for operation, argument in tokens:
        if operation in _REPEATS:
            repeated = argument[2]
            if previous_repeat or len(repeated) != 1 or repeated[0][0] not in _ATOMS:
                raise ValidationError("readiness.pattern 不允许嵌套或相邻的可回溯重复")
            if repeated[0][0] == _CONSTANTS.IN:
                _validate_in(repeated[0][1])
            previous_repeat = True
            continue
        if operation == _CONSTANTS.SUBPATTERN:
            _validate_tokens(argument[3])
        elif operation == _CONSTANTS.BRANCH:
            for branch in argument[1]:
                _validate_tokens(branch)
        elif operation == _CONSTANTS.IN:
            _validate_in(argument)
        elif operation not in {
            _CONSTANTS.LITERAL,
            _CONSTANTS.NOT_LITERAL,
            _CONSTANTS.ANY,
            _CONSTANTS.CATEGORY,
            _CONSTANTS.AT,
        }:
            raise ValidationError("readiness.pattern 包含不受支持的回溯构造")
        if operation != _CONSTANTS.AT:
            previous_repeat = False


def _validate_in(tokens: Any) -> None:
    if any(operation not in _IN_OPS for operation, _ in tokens):
        raise ValidationError("readiness.pattern 字符类包含不受支持的构造")


def compile_log_pattern(pattern: str) -> re.Pattern[str]:
    try:
        parsed = _PARSER.parse(pattern, 0)
        compiled = re.compile(pattern)
    except re.error as exc:
        raise ValidationError("readiness.pattern 不是有效正则") from exc
    _validate_tokens(parsed)
    return compiled
