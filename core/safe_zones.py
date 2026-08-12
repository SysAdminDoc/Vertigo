"""Platform safe-zone geometry and critical-text validation.

Safe zones are advisory guides for changing mobile-app chrome. The same
geometry drives the preview overlay and the export-time warning so users do
not have to translate a visual guide into pixel measurements themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .caption_styles import CaptionPreset, style_for_height
from .overlays import OverlayPosition, TextOverlay
from .presets import Preset, SafeRect


@dataclass(frozen=True)
class TextBounds:
    """An estimated text box in output pixels."""

    left: int
    top: int
    right: int
    bottom: int


@dataclass(frozen=True)
class SafeZoneIssue:
    """One critical text region that crosses the selected safe rectangle."""

    source: str
    label: str
    bounds: TextBounds
    edges: tuple[str, ...]

    @property
    def message(self) -> str:
        edge_text = ", ".join(self.edges)
        return f"{self.label} enters the {edge_text} unsafe area."


@dataclass(frozen=True)
class SafeZoneReport:
    """Validation result for the selected preset and visible text."""

    preset: Preset
    rect: SafeRect
    issues: tuple[SafeZoneIssue, ...] = ()

    @property
    def is_safe(self) -> bool:
        return not self.issues

    def summary(self) -> str:
        if not self.issues:
            return f"{self.preset.safe_zone.label}: critical text is inside the guide."
        return " ".join(issue.message for issue in self.issues)


def validate_safe_zones(
    preset: Preset,
    *,
    overlays: Iterable[TextOverlay] = (),
    caption_preset: CaptionPreset | None = None,
    width: int | None = None,
    height: int | None = None,
) -> SafeZoneReport:
    """Check overlays and a worst-case caption block against a preset guide."""
    out_width = width or preset.width
    out_height = height or preset.height
    safe_rect = preset.safe_zone.rect(out_width, out_height)
    issues: list[SafeZoneIssue] = []

    for overlay in overlays:
        if not overlay.text.strip():
            continue
        bounds = estimate_overlay_bounds(overlay, out_width, out_height)
        edges = _unsafe_edges(bounds, safe_rect)
        if edges:
            preview = " ".join(overlay.text.split())[:36]
            issues.append(
                SafeZoneIssue(
                    source="overlay",
                    label=f"Overlay '{preview}'",
                    bounds=bounds,
                    edges=edges,
                )
            )

    if caption_preset is not None:
        bounds = estimate_caption_bounds(caption_preset, out_width, out_height)
        edges = _unsafe_edges(bounds, safe_rect)
        if edges:
            issues.append(
                SafeZoneIssue(
                    source="captions",
                    label="Caption block",
                    bounds=bounds,
                    edges=edges,
                )
            )

    return SafeZoneReport(preset=preset, rect=safe_rect, issues=tuple(issues))


def estimate_overlay_bounds(overlay: TextOverlay, width: int, height: int) -> TextBounds:
    """Estimate the drawtext box conservatively from the overlay settings."""
    size = max(8, min(512, int(overlay.size)))
    max_chars = max(1, int(width * 0.84 / (size * 0.56)))
    lines: list[str] = []
    for raw_line in overlay.text.splitlines() or [overlay.text]:
        line = raw_line or " "
        while len(line) > max_chars:
            lines.append(line[:max_chars])
            line = line[max_chars:]
        lines.append(line)

    text_width = max(len(line) for line in lines) * size * 0.56
    padding = 36 if overlay.background else 0
    stroke = max(0, min(32, int(overlay.stroke_width))) if overlay.stroke else 0
    box_width = min(width, int(round(text_width + padding + stroke * 2)))
    box_height = min(
        height,
        int(round(len(lines) * size * 1.25 + padding + stroke * 2)),
    )

    position = overlay.position
    if not isinstance(position, OverlayPosition):
        try:
            position = OverlayPosition(str(position))
        except ValueError:
            position = OverlayPosition.TITLE

    if position is OverlayPosition.TITLE:
        left = (width - box_width) // 2
        top = (height - box_height) // 2
    elif position is OverlayPosition.TOP:
        left = (width - box_width) // 2
        top = int(round(height * 0.08))
    elif position is OverlayPosition.LOWER_THIRD:
        left = int(round(width * 0.08))
        top = int(round(height * 0.72))
    else:
        left = (width - box_width) // 2
        top = height - box_height - int(round(height * 0.06))

    return TextBounds(left=left, top=top, right=left + box_width, bottom=top + box_height)


def estimate_caption_bounds(
    preset: CaptionPreset,
    width: int,
    height: int,
) -> TextBounds:
    """Estimate the maximum caption block emitted by the ASS style."""
    style = style_for_height(preset, height)
    font_size = int(style["FontSize"])
    outline = float(style["Outline"])
    line_count = max(1, int(preset.max_lines))
    box_height = int(round(font_size * 1.25 * line_count + outline * 2.0))
    # Caption chunks are centered and wrapped before ASS rendering. Use a
    # centered critical-text block instead of treating the full ASS margins
    # as occupied text; this avoids a false right-rail warning for the
    # bundled styles while still catching genuinely wide caption settings.
    side_margin = max(int(style["MarginL"]), int(round(width * 0.12)))
    left = side_margin
    right = width - side_margin
    alignment = int(style["Alignment"])

    if alignment in (1, 2, 3):
        bottom = height - int(style["MarginV"])
        top = bottom - box_height
    elif alignment in (7, 8, 9):
        top = int(style["MarginV"])
        bottom = top + box_height
    else:
        top = (height - box_height) // 2
        bottom = top + box_height

    return TextBounds(left=left, top=top, right=right, bottom=bottom)


def _unsafe_edges(bounds: TextBounds, safe_rect: SafeRect) -> tuple[str, ...]:
    edges: list[str] = []
    if bounds.left < safe_rect.left:
        edges.append("left")
    if bounds.right > safe_rect.right:
        edges.append("right")
    if bounds.top < safe_rect.top:
        edges.append("top")
    if bounds.bottom > safe_rect.bottom:
        edges.append("bottom")
    return tuple(edges)
