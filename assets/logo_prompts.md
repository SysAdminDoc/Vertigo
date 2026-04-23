# ReelForge Logo — Generation Prompts

**Project:** ReelForge — a premium desktop tool that forges horizontal video into vertical 9:16 for YouTube Shorts, TikTok, and Instagram Reels. The brand feels like a professional creator's forge: dark mode first, mauve/pink gradients (Catppuccin Mocha accent `#cba6f7` → `#f5c2e7`), sharp geometric lines, cinematic.

Use these five prompts with your preferred generative image model (Midjourney, DALL·E, Stable Diffusion, Ideogram, Recraft). Pick one to become the primary mark.

---

## 1. Minimal icon (16px–128px favicons, toolbar)
> Minimalist flat icon glyph for a vertical video tool. Abstract rotated letter **R** whose right leg extends down into a long vertical rectangle suggesting a 9:16 frame. Single solid mauve color `#cba6f7` on a transparent background. Geometric sans-serif construction, pixel-grid-aligned, no shading, no gradients, crisp at 16 × 16 pixels. SVG-friendly simple shapes. Centered, generous padding.

## 2. App icon (Chrome Web Store, macOS dock, Windows taskbar, Android adaptive)
> Modern SaaS app icon, 512 × 512, rounded-square container with 22 % corner radius. Center mark: a wide horizontal rectangle being folded / compressed into a tall vertical rectangle, shown as two overlapping frames with a sweeping motion arc between them. Mauve-to-pink diagonal gradient (`#cba6f7` top-left → `#f5c2e7` bottom-right) over a deep charcoal background `#1e1e2e`. Subtle inner glow, soft drop shadow, no text. Flat design with one plane of depth. Premium, confident, minimal.

## 3. Wordmark (README headers, splash, website hero)
> Horizontal wordmark for **REELFORGE**, set in an uppercase geometric sans-serif (Space Grotesk / Satoshi / custom). Letters in near-white `#cdd6f4`, with a thin mauve `#cba6f7` underline extending from the foot of the **R** all the way across the word and terminating in a tiny vertical 9:16 frame glyph. Dark background `#11111b`. Tight letter-spacing, razor-sharp kerning, subtle glow under the underline. Cinematic, editorial, premium.

## 4. Emblem (README header art, installer splash, About dialog)
> Detailed circular emblem badge, 1024 × 1024, dark-mode aesthetic. A forge anvil reinterpreted as a **9:16 vertical phone frame** sitting on a stylized pedestal, struck by a hammer of pure light leaving mauve sparks. Surrounding the center: a thin ring with four small glyphs at the cardinal points — YouTube Shorts play triangle, TikTok musical note, Instagram camera, square 1:1. Gradient plate from deep charcoal `#181825` to black, mauve `#cba6f7` highlight rim, pink `#f5c2e7` spark particles. No text inside the emblem. Slight cinematic film grain. Luxury tech badge feel.

## 5. Abstract (marketing, social, conceptual)
> Abstract conceptual art representing horizontal-to-vertical video transformation. A wide flat plane of cinematic footage (letterbox 16:9) being folded, compressed, and re-poured into a narrow glowing vertical pillar (9:16) that stands tall. Particles of light stream from the wide source into the pillar. Deep matte black background `#11111b`, mauve and pink volumetric light `#cba6f7` / `#f5c2e7`, long soft shadows, a hint of motion blur, high contrast. No text. Premium editorial poster style. 16:9 composition with subject centered.

---

## After selection — integration follow-up

Generate the primary mark, then use this prompt with your coding assistant:

> I've generated the final logo for ReelForge. Please integrate it: (1) save as `assets/icon.svg` and `assets/icon.png` in the repo root and 16/32/48/128/256/512 size variants in `assets/icons/`; (2) reference the emblem or wordmark in README.md as a centered header image above the badges; (3) wire it into PyQt6: load `assets/icon.png` in `reelforge.py` via `QApplication.setWindowIcon(QIcon("assets/icon.png"))`; (4) also set it on the main window (`win.setWindowIcon(...)`) and replace the `REELFORGE` text label in `ui/titlebar.py` with an `QLabel` showing a 20 × 20 scaled `QPixmap` of the icon beside the brand wordmark; (5) update `.github/workflows/build.yml` (when CI is wired in) to bundle `assets/icons/` into the PyInstaller build; (6) embed the 16 × 16 favicon as a base64 data URI in any future web artifacts.

## Palette reference

| Role | Hex |
| --- | --- |
| Accent primary (mauve) | `#cba6f7` |
| Accent secondary (pink) | `#f5c2e7` |
| Background base | `#1e1e2e` |
| Background crust | `#11111b` |
| Text | `#cdd6f4` |
| Surface | `#313244` |
