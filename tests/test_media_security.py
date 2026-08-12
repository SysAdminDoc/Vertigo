"""Security-version policy tests for the media ingest/export boundary."""

from __future__ import annotations

import unittest


class MediaSecurityPolicyTests(unittest.TestCase):
    def test_parse_version_accepts_tool_and_package_strings(self) -> None:
        from core.preflight import parse_version

        self.assertEqual(parse_version("ffmpeg version 8.1.2-full_build"), (8, 1, 2))
        self.assertEqual(parse_version("Pillow 12.2.0"), (12, 2, 0))
        self.assertEqual(parse_version("v7.1"), (7, 1, 0))
        self.assertIsNone(parse_version("not a version"))

    def test_current_versions_are_exportable(self) -> None:
        from core.preflight import inspect_media_dependencies

        report = inspect_media_dependencies(
            ffmpeg_output="ffmpeg version 8.1.2-full_build",
            pillow_version="12.2.0",
        )

        self.assertTrue(report.can_export)
        self.assertEqual(report.warnings, ())
        self.assertIn("FFmpeg 8.1.2", report.version_summary)
        self.assertIn("Pillow 12.2.0", report.version_summary)

    def test_stale_ffmpeg_branch_warns_before_export(self) -> None:
        from core.preflight import inspect_media_dependencies

        report = inspect_media_dependencies(
            ffmpeg_output="ffmpeg version 8.1.0-full_build",
            pillow_version="12.2.0",
        )

        self.assertTrue(report.can_export)
        self.assertTrue(report.warnings)
        self.assertIn("security floor 8.1.2", report.warnings[0])

    def test_vulnerable_pillow_floor_blocks_export(self) -> None:
        from core.preflight import inspect_media_dependencies

        report = inspect_media_dependencies(
            ffmpeg_output="ffmpeg version 8.1.2-full_build",
            pillow_version="12.1.1",
        )

        self.assertFalse(report.can_export)
        self.assertIn("CVE-2026-42310", report.blocker_summary)
        self.assertIn("12.2.0", report.blocker_summary)

    def test_unparseable_ffmpeg_blocks_export(self) -> None:
        from core.preflight import inspect_media_dependencies

        report = inspect_media_dependencies(
            ffmpeg_output="custom media tool build",
            pillow_version="12.2.0",
        )

        self.assertFalse(report.can_export)
        self.assertIn("could not parse", report.blocker_summary)


if __name__ == "__main__":
    unittest.main()
