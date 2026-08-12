"""Output presets and conservative platform safe-zone metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SafeRect:
    """Pixel coordinates for the critical-text rectangle on an export."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)


@dataclass(frozen=True)
class SafeZone:
    """Normalized UI-clearance metadata for one delivery surface.

    The margins are fractions of the output dimensions rather than fixed
    pixels so the same platform guidance scales to preview and export sizes.
    They are intentionally conservative approximations: platform chrome
    changes by app version, device, and placement.
    """

    label: str
    description: str
    top_fraction: float
    right_fraction: float
    bottom_fraction: float
    left_fraction: float
    source_url: str

    def rect(self, width: int, height: int) -> SafeRect:
        """Return the safe rectangle in output pixels."""
        width = max(1, int(width))
        height = max(1, int(height))
        left = min(width - 1, max(0, round(width * self.left_fraction)))
        top = min(height - 1, max(0, round(height * self.top_fraction)))
        right = max(left + 1, min(width, round(width * (1.0 - self.right_fraction))))
        bottom = max(top + 1, min(height, round(height * (1.0 - self.bottom_fraction))))
        return SafeRect(left=left, top=top, right=right, bottom=bottom)


# These are design-time guides, not platform contracts. Official platform
# guidance describes the UI overlays but does not promise one pixel-perfect
# layout across every phone, app version, or placement. The margins leave
# breathing room around those documented overlays.
TIKTOK_SAFE_ZONE = SafeZone(
    label="TikTok safe zone",
    description="Keep critical text clear of top navigation, the action rail, and captions/CTA chrome.",
    top_fraction=200 / 1920,
    right_fraction=140 / 1080,
    bottom_fraction=380 / 1920,
    left_fraction=60 / 1080,
    source_url="https://ads.tiktok.com/business/library/TikTok_CreativeCodes_May2023.pdf",
)
REELS_SAFE_ZONE = SafeZone(
    label="Instagram Reels safe zone",
    description="Keep critical text clear of the profile header, action rail, and bottom caption/CTA area.",
    top_fraction=220 / 1920,
    right_fraction=120 / 1080,
    bottom_fraction=380 / 1920,
    left_fraction=60 / 1080,
    source_url="https://www.facebook.com/business/ads/facebook-instagram-reels-ads",
)
SHORTS_SAFE_ZONE = SafeZone(
    label="YouTube Shorts safe zone",
    description="Keep critical text clear of Shorts navigation, action buttons, and lower metadata chrome.",
    top_fraction=225 / 1920,
    right_fraction=120 / 1080,
    bottom_fraction=380 / 1920,
    left_fraction=60 / 1080,
    source_url="https://support.google.com/google-ads/answer/13547298",
)
SQUARE_SAFE_ZONE = SafeZone(
    label="Universal title-safe zone",
    description="A modest action/title-safe inset for square exports without one platform-specific overlay layout.",
    top_fraction=60 / 1080,
    right_fraction=60 / 1080,
    bottom_fraction=60 / 1080,
    left_fraction=60 / 1080,
    source_url="https://support.google.com/google-ads/answer/13547298",
)


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    tagline: str
    width: int
    height: int
    fps: int
    max_duration: int  # seconds; 0 = unlimited
    video_bitrate: str
    audio_bitrate: str
    safe_zone: SafeZone

    @property
    def aspect(self) -> float:
        return self.width / self.height

    @property
    def resolution_label(self) -> str:
        return f"{self.width}x{self.height}"


PRESETS: dict[str, Preset] = {
    "shorts": Preset(
        id="shorts",
        label="YouTube Shorts",
        tagline="1080x1920 · 60fps · ≤60s",
        width=1080,
        height=1920,
        fps=60,
        max_duration=60,
        video_bitrate="8M",
        audio_bitrate="192k",
        safe_zone=SHORTS_SAFE_ZONE,
    ),
    "tiktok": Preset(
        id="tiktok",
        label="TikTok",
        tagline="1080x1920 · 60fps · ≤180s",
        width=1080,
        height=1920,
        fps=60,
        max_duration=180,
        video_bitrate="7M",
        audio_bitrate="192k",
        safe_zone=TIKTOK_SAFE_ZONE,
    ),
    "reels": Preset(
        id="reels",
        label="Instagram Reels",
        tagline="1080x1920 · 30fps · ≤90s",
        width=1080,
        height=1920,
        fps=30,
        max_duration=90,
        video_bitrate="6M",
        audio_bitrate="192k",
        safe_zone=REELS_SAFE_ZONE,
    ),
    "square": Preset(
        id="square",
        label="Square (1:1)",
        tagline="1080x1080 · 30fps",
        width=1080,
        height=1080,
        fps=30,
        max_duration=0,
        video_bitrate="6M",
        audio_bitrate="192k",
        safe_zone=SQUARE_SAFE_ZONE,
    ),
}


def default_preset() -> Preset:
    return PRESETS["shorts"]
