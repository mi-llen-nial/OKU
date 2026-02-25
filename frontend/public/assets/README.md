# Assets Guide

## Structure
- `icons/` — small UI SVG icons (24x24, stroke-based)
- `images/` — UI textures/background assets (`.png/.jpg/.webp/.svg`)
- `illustrations/` — decorative scene assets and section visuals
- `logo/` — brand logos (`logo.png`, optional `logo.svg`)
- `audio/` — static sound effects or demo audio clips

## Naming Rules
- Use lowercase kebab-case: `arcane-frame.svg`, `magic-book.png`
- Keep semantic prefixes where useful:
  - `icon-*` for shared icons
  - `illus-*` for illustrations
  - `bg-*` for background helpers
- Never use spaces in file names.

## Usage Rules
- In Next.js, assets are served from `/public/assets/...`
- Import paths from `src/assets/index.ts` registry instead of hardcoding URLs.
- SVG icons should keep consistent line style: rounded caps, rounded joins, 1.8-2.2 stroke width.
- Compress large raster images before commit (`.webp` preferred for photos/illustrations).

## Palette Workflow
- Put/update logo at `public/assets/logo/logo.png`
- Run palette extraction:
  - `cd frontend && npm run extract-palette`
- Generated colors are saved to `src/theme/brand.generated.ts`
