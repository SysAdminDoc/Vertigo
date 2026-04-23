# Kiln Logo — Generation Prompts

**Project:** Kiln — a premium desktop tool that fires raw horizontal footage into polished 9:16 vertical for YouTube Shorts, TikTok, and Instagram Reels. The brand leans into the *kiln* metaphor: a focused chamber where raw material is transformed by heat into a finished, premium object. Dark mode first, mauve→pink gradients (`#cba6f7` → `#f5c2e7`) acting as the heat source, sharp geometric lines, cinematic.

Use these five prompts with your preferred generative image model (Midjourney, DALL·E, Stable Diffusion, Ideogram, Recraft). Pick one to become the primary mark.

---

## 1. Minimal icon (16px–128px favicons, toolbar)
> Minimalist flat icon for a vertical-video tool called **Kiln**. A tall rounded rectangle in 9:16 proportions representing the kiln chamber, with a small flame-like triangle glowing at its center. Single solid mauve color `#cba6f7` on a transparent background. Geometric construction, pixel-grid-aligned, no shading, no gradients, crisp at 16 × 16 pixels. SVG-friendly. Generous padding around the glyph.

## 2. App icon (Chrome Web Store, macOS dock, Windows taskbar, Android adaptive)
> Modern SaaS app icon, 512 × 512, rounded-square container with 22% corner radius. Center mark: a tall 9:16 vertical chamber with a mauve-to-pink gradient (`#cba6f7` top → `#f5c2e7` bottom) filling it from within, radiating soft inner glow like a heated kiln. A faint horizontal ghost frame sits behind the chamber, slightly wider and more muted, suggesting the source footage about to be fired. Subtle warm rim-light at the base. Deep charcoal background `#1e1e2e`. No text. Flat premium design, one plane of depth, confident, cinematic.

## 3. Wordmark (README headers, splash, website hero)
> Horizontal wordmark for **KILN**, set in an uppercase geometric sans-serif (Space Grotesk / Satoshi / custom). Four letters, near-white `#cdd6f4`, tight letter-spacing with razor kerning. A thin mauve `#cba6f7` → pink `#f5c2e7` underline begins at the foot of the **K** and extends past the **N**, terminating in a tiny vertical 9:16 frame glyph containing a play triangle. Dark background `#11111b`. Subtle warm glow under the underline. Editorial, premium, confident.

## 4. Emblem (README header art, installer splash, About dialog)
> Detailed circular emblem badge, 1024 × 1024, dark-mode aesthetic. A stylized kiln chamber sits at the center — a tall 9:16 cavity glowing from within, with embers drifting upward. Behind the kiln, crossed creator tools (a small clapperboard slate and a microphone) flank the cavity. Ring around the emblem carries four small platform glyphs at cardinal points — YouTube Shorts triangle, TikTok note, Instagram camera, square 1:1. Gradient plate from `#181825` to black, mauve `#cba6f7` highlight rim, pink `#f5c2e7` ember particles. No text inside the emblem. Luxury tech badge feel with gentle film grain.

## 5. Abstract (marketing, social, conceptual)
> Abstract conceptual art showing raw horizontal footage being fired into vertical form. A wide 16:9 plane of cinematic film enters a tall glowing chamber on the right; as it passes through, it compresses, heats, and emerges as a polished 9:16 vertical pillar of light. Deep matte black background `#11111b`. Mauve and pink volumetric light `#cba6f7` / `#f5c2e7` pouring from the chamber. Long soft shadows, hint of motion blur, high contrast. No text. Premium editorial poster style. 16:9 composition with the kiln chamber anchored slightly right of center.

---

## After selection — integration follow-up

Generate the primary mark, then use this prompt with your coding assistant:

> I've generated the final logo for Kiln. Please integrate it: (1) save as `assets/icon.svg` and `assets/icon.png` in the repo root plus 16/32/48/128/256/512 size PNG variants; (2) regenerate `assets/icon.ico` as a multi-resolution Windows icon; (3) reference the emblem or wordmark in `README.md` as a centered header image above the badges; (4) wire it into PyQt6 via the existing `ui/assets.icon_path()` resolver — no code change needed if the filename stays `icon.png` / `icon.ico`; (5) regenerate `assets/wordmark.svg` to match the new brand; (6) update `.github/workflows/build.yml` if any artifact names reference old assets; (7) embed the 16 × 16 favicon as a base64 data URI in any future web artifacts.

## Palette reference

| Role | Hex |
| --- | --- |
| Accent primary (mauve) | `#cba6f7` |
| Accent secondary (pink) | `#f5c2e7` |
| Background base | `#1e1e2e` |
| Background crust | `#11111b` |
| Text | `#cdd6f4` |
| Surface | `#313244` |
