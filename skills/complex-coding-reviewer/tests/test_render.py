from __future__ import annotations

import unittest
from pathlib import Path

from helpers import (
    create_file_target,
    finding,
    receipt_for_target,
    update_counts_and_verdict,
    writable_tempdir,
)

from complex_coding_reviewer.render import render_receipt


class RenderTests(unittest.TestCase):
    def test_findings_are_rendered_before_lens_summary(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["findings"] = [finding()]
            update_counts_and_verdict(receipt)
            rendered = render_receipt(receipt)
            self.assertLess(rendered.index("## Findings"), rendered.index("## Lens Coverage"))
            self.assertIn("FIND-001 [major]", rendered)
            self.assertIn("`src/example.py:1`", rendered)

    def test_clean_receipt_states_no_findings(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            self.assertIn("No findings.", render_receipt(receipt))


if __name__ == "__main__":
    unittest.main()
