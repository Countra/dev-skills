from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from helpers import writable_tempdir

from complex_coding_reviewer.io import write_new_bytes


class AtomicWriteTests(unittest.TestCase):
    def test_transient_replace_denial_is_retried_within_bound(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            review_root = root / "reviews"
            output = review_root / "result.json"
            real_replace = os.replace
            attempts = 0

            def flaky_replace(source: Path, destination: Path) -> None:
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError(13, "transient sharing conflict")
                real_replace(source, destination)

            with mock.patch(
                "complex_coding_reviewer.io.os.replace",
                side_effect=flaky_replace,
            ), mock.patch("complex_coding_reviewer.io.time.sleep") as sleep:
                result = write_new_bytes(
                    output,
                    b"{}\n",
                    review_root=review_root,
                )

            self.assertEqual(output, result)
            self.assertEqual(b"{}\n", output.read_bytes())
            self.assertEqual(2, attempts)
            sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
