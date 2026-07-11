"""Required postcondition 执行器。"""

from __future__ import annotations

from typing import Any

from .errors import VerifierError
from .evidence import validate_png
from .locators import raw_locator, resolve_strict
from .models import AssertionSpec


async def evaluate_assertion(page: Any, assertion: AssertionSpec) -> dict[str, Any]:
    timeout = assertion.timeout_ms
    try:
        if assertion.kind in {"visible", "hidden"}:
            locator = await resolve_strict(page, assertion.locator)
            expected_visible = assertion.kind == "visible"
            if expected_visible:
                await locator.wait_for(state="visible", timeout=timeout)
            else:
                await locator.wait_for(state="hidden", timeout=timeout)
            return {"type": assertion.kind, "passed": True}
        if assertion.kind == "text":
            locator = await resolve_strict(page, assertion.locator)
            actual = await locator.inner_text(timeout=timeout)
            passed = actual == str(assertion.expected)
            result = {"type": "text", "passed": passed, "actual": actual[:1000], "expected": assertion.expected}
        elif assertion.kind == "value":
            locator = await resolve_strict(page, assertion.locator)
            actual = await locator.input_value(timeout=timeout)
            passed = actual == str(assertion.expected)
            result = {"type": "value", "passed": passed, "actual": actual[:1000], "expected": assertion.expected}
        elif assertion.kind == "count":
            locator = raw_locator(page, assertion.locator)
            actual = await locator.count()
            passed = actual == int(assertion.expected)
            result = {"type": "count", "passed": passed, "actual": actual, "expected": assertion.expected}
        elif assertion.kind == "urlContains":
            actual = page.url
            passed = str(assertion.expected) in actual
            result = {"type": "urlContains", "passed": passed, "expected": assertion.expected}
        elif assertion.kind == "titleContains":
            actual = await page.title()
            passed = str(assertion.expected) in actual
            result = {"type": "titleContains", "passed": passed, "actual": actual[:500], "expected": assertion.expected}
        elif assertion.kind == "screenshotQuality":
            metrics = validate_png(await page.screenshot(timeout=timeout))
            passed = True
            result = {"type": "screenshotQuality", "passed": True, "metrics": metrics}
        else:
            raise VerifierError("unsupported_assertion", f"不支持的 postcondition：{assertion.kind}")
    except VerifierError:
        raise
    except Exception as exc:
        raise VerifierError(
            "postcondition_error",
            f"postcondition {assertion.kind} 执行失败：{exc}",
            details={"type": assertion.kind},
        ) from exc
    if not passed:
        raise VerifierError("postcondition_failed", f"required postcondition 未通过：{assertion.kind}", details=result)
    return result


async def evaluate_all(page: Any, assertions: tuple[AssertionSpec, ...]) -> list[dict[str, Any]]:
    results = []
    for assertion in assertions:
        results.append(await evaluate_assertion(page, assertion))
    return results
