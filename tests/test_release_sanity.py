"""Local PyInstaller release-contract checks."""

from __future__ import annotations

import unittest
from pathlib import Path


class ReleaseSanityTests(unittest.TestCase):
    def test_repository_contract_is_clean(self) -> None:
        from scripts.release_sanity import inspect_repository

        self.assertEqual(inspect_repository(Path(__file__).parents[1]), [])

    def test_cli_reports_clean_source_contract(self) -> None:
        from scripts.release_sanity import main

        self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main()
