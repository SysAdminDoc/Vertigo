"""Platform guide geometry and critical-text validation coverage."""

from __future__ import annotations

import unittest


class SafeZoneTests(unittest.TestCase):
    def test_vertical_guides_are_pinned_at_1080x1920(self) -> None:
        from core.presets import PRESETS

        rect = PRESETS["shorts"].safe_zone.rect(1080, 1920)
        self.assertEqual((rect.left, rect.top, rect.right, rect.bottom), (60, 225, 960, 1540))

    def test_all_presets_expose_platform_metadata(self) -> None:
        from core.presets import PRESETS

        for preset in PRESETS.values():
            self.assertTrue(preset.safe_zone.label)
            self.assertTrue(preset.safe_zone.description)
            self.assertTrue(preset.safe_zone.source_url.startswith("https://"))

    def test_overlay_outside_guide_warns(self) -> None:
        from core.overlays import OverlayPosition, TextOverlay
        from core.presets import PRESETS
        from core.safe_zones import validate_safe_zones

        report = validate_safe_zones(
            PRESETS["shorts"],
            overlays=[
                TextOverlay(
                    text="Follow for more",
                    position=OverlayPosition.CAPTION,
                    size=52,
                    end=5.0,
                )
            ],
        )

        self.assertFalse(report.is_safe)
        self.assertEqual(report.issues[0].source, "overlay")
        self.assertIn("bottom", report.issues[0].edges)

    def test_caption_style_is_checked_against_same_guide(self) -> None:
        from core.caption_styles import resolve
        from core.presets import PRESETS
        from core.safe_zones import validate_safe_zones

        safe = validate_safe_zones(PRESETS["shorts"], caption_preset=resolve("pop"))
        unsafe = validate_safe_zones(PRESETS["shorts"], caption_preset=resolve("classic"))

        self.assertTrue(safe.is_safe)
        self.assertFalse(unsafe.is_safe)
        self.assertEqual(unsafe.issues[0].source, "captions")
        self.assertIn("bottom", unsafe.issues[0].edges)


if __name__ == "__main__":
    unittest.main()
