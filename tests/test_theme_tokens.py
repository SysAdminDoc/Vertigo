"""Theme token coverage for ReelForge's PyQt theme system."""

from __future__ import annotations

import unittest

from ui.theme import SYSTEM_THEME_ID, THEMES, qcolor, resolved_theme_id, sanitize_theme_preference
from ui.theme import build_stylesheet


def _rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _linear(channel: float) -> float:
    if channel <= 0.03928:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    r, g, b = (_linear(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(foreground: str, background: str) -> float:
    a = _luminance(foreground)
    b = _luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


class ThemeTokenTests(unittest.TestCase):
    def test_stylesheet_builds_for_every_theme(self) -> None:
        for theme_id, theme in THEMES.items():
            with self.subTest(theme=theme_id):
                stylesheet = build_stylesheet(theme_id)
                self.assertIn(theme.text, stylesheet)
                self.assertIn(theme.accent, stylesheet)
                self.assertIn("QFileDialog", stylesheet)
                self.assertIn("QLineEdit", stylesheet)

    def test_theme_preference_sanitization(self) -> None:
        self.assertEqual(sanitize_theme_preference("mocha"), "mocha")
        self.assertEqual(sanitize_theme_preference("latte"), "latte")
        self.assertEqual(sanitize_theme_preference("missing"), SYSTEM_THEME_ID)
        self.assertEqual(sanitize_theme_preference(None), SYSTEM_THEME_ID)

    def test_explicit_theme_resolution_does_not_need_qapp(self) -> None:
        self.assertEqual(resolved_theme_id("mocha"), "mocha")
        self.assertEqual(resolved_theme_id("graphite"), "graphite")
        self.assertEqual(resolved_theme_id("latte"), "latte")

    def test_rgba_token_parsing(self) -> None:
        color = qcolor("rgba(10, 20, 30, 0.50)")
        self.assertEqual((color.red(), color.green(), color.blue()), (10, 20, 30))
        self.assertIn(color.alpha(), (127, 128))

    def test_core_text_contrast_is_accessible(self) -> None:
        pairs = (
            ("text", "base"),
            ("text", "mantle"),
            ("text", "crust"),
            ("subtext1", "base"),
            ("subtext1", "mantle"),
            ("accent_text", "accent"),
        )
        for theme_id, theme in THEMES.items():
            for fg_name, bg_name in pairs:
                with self.subTest(theme=theme_id, pair=f"{fg_name}/{bg_name}"):
                    fg = getattr(theme, fg_name)
                    bg = getattr(theme, bg_name)
                    self.assertGreaterEqual(_contrast(fg, bg), 4.5)

    def test_status_text_contrast_is_accessible_on_main_surfaces(self) -> None:
        for theme_id, theme in THEMES.items():
            for color_name in ("red", "yellow", "green"):
                with self.subTest(theme=theme_id, color=color_name):
                    self.assertGreaterEqual(_contrast(getattr(theme, color_name), theme.base), 3.0)
                    self.assertGreaterEqual(_contrast(getattr(theme, color_name), theme.mantle), 3.0)


if __name__ == "__main__":
    unittest.main()
