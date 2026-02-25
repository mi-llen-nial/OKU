import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

type RGB = { r: number; g: number; b: number };

const FALLBACK = ["#6460F2", "#675FD9", "#CFA44E", "#F4EEDA", "#1E1C2E", "#A8B0FF", "#8B84FF"];

function detectRepoRoot(): string {
  const cwd = process.cwd();
  if (fs.existsSync(path.join(cwd, "frontend")) && fs.existsSync(path.join(cwd, "backend"))) {
    return cwd;
  }
  const parent = path.resolve(cwd, "..");
  if (fs.existsSync(path.join(parent, "frontend")) && fs.existsSync(path.join(parent, "backend"))) {
    return parent;
  }
  return cwd;
}

function findLogo(root: string): string | null {
  const candidates = [
    path.join(root, "assets", "logo", "logo.png"),
    path.join(root, "public", "assets", "logo", "logo.png"),
    path.join(root, "frontend", "public", "assets", "logo", "logo.png"),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function quantizeChannel(channel: number, step = 22): number {
  return Math.max(0, Math.min(255, Math.round(channel / step) * step));
}

function toHex({ r, g, b }: RGB): string {
  const hex = [r, g, b].map((item) => item.toString(16).padStart(2, "0")).join("");
  return `#${hex}`.toUpperCase();
}

function fromHex(hex: string): RGB {
  const clean = hex.replace("#", "");
  return {
    r: Number.parseInt(clean.slice(0, 2), 16),
    g: Number.parseInt(clean.slice(2, 4), 16),
    b: Number.parseInt(clean.slice(4, 6), 16),
  };
}

function brightness(color: RGB): number {
  return (color.r + color.g + color.b) / 3;
}

function saturation(color: RGB): number {
  return Math.max(color.r, color.g, color.b) - Math.min(color.r, color.g, color.b);
}

function distance(a: RGB, b: RGB): number {
  const dr = a.r - b.r;
  const dg = a.g - b.g;
  const db = a.b - b.b;
  return Math.sqrt(dr * dr + dg * dg + db * db);
}

function uniqueColors(colors: RGB[], minDistance = 28): RGB[] {
  const output: RGB[] = [];
  for (const color of colors) {
    if (output.every((existing) => distance(existing, color) >= minDistance)) {
      output.push(color);
    }
  }
  return output;
}

function buildSemanticPalette(colors: string[]): string[] {
  const pool = [...colors, ...FALLBACK];
  const used = new Set<string>();

  const pick = (predicate: (color: RGB) => boolean, fallback: string): string => {
    for (const candidate of pool) {
      if (used.has(candidate)) continue;
      if (predicate(fromHex(candidate))) {
        used.add(candidate);
        return candidate;
      }
    }

    if (!used.has(fallback)) {
      used.add(fallback);
      return fallback;
    }

    for (const candidate of pool) {
      if (!used.has(candidate)) {
        used.add(candidate);
        return candidate;
      }
    }

    return fallback;
  };

  const primary = pick((c) => c.b > c.r && c.b >= c.g && saturation(c) > 28, FALLBACK[0]);
  const secondary = pick((c) => c.b >= c.r && c.b >= c.g && saturation(c) > 16, FALLBACK[1]);
  const accent = pick((c) => c.r >= c.g && c.g >= c.b && saturation(c) > 18, FALLBACK[2]);
  const paper = pick((c) => brightness(c) > 185 && saturation(c) < 70, FALLBACK[3]);
  const ink = pick((c) => brightness(c) < 85, FALLBACK[4]);
  const mist = pick((c) => brightness(c) > 130 && saturation(c) < 80, FALLBACK[5]);
  const glow = pick((c) => saturation(c) > 24, FALLBACK[6]);

  return [primary, secondary, accent, paper, ink, mist, glow];
}

function extractFromLogo(root: string, logoPath: string): string[] {
  const requireFromFrontend = createRequire(path.join(root, "frontend", "package.json"));
  const { PNG } = requireFromFrontend("pngjs") as {
    PNG: { sync: { read: (buffer: Buffer) => { width: number; height: number; data: Buffer } } };
  };

  const raw = fs.readFileSync(logoPath);
  const png = PNG.sync.read(raw);

  const buckets = new Map<string, { color: RGB; count: number }>();
  const step = Math.max(1, Math.floor(Math.sqrt((png.width * png.height) / 20000)));

  for (let y = 0; y < png.height; y += step) {
    for (let x = 0; x < png.width; x += step) {
      const index = (png.width * y + x) * 4;
      const alpha = png.data[index + 3];
      if (alpha < 120) continue;

      const color = {
        r: quantizeChannel(png.data[index]),
        g: quantizeChannel(png.data[index + 1]),
        b: quantizeChannel(png.data[index + 2]),
      };

      // Ignore bright neutral background.
      if (saturation(color) < 16 && brightness(color) > 170) continue;

      const key = `${color.r}-${color.g}-${color.b}`;
      const prev = buckets.get(key);
      buckets.set(key, { color, count: (prev?.count || 0) + 1 });
    }
  }

  const ranked = [...buckets.values()]
    .sort((a, b) => b.count - a.count)
    .map((item) => item.color);

  const selected = uniqueColors(ranked).slice(0, 12);
  return selected.map(toHex);
}

function generateFile(root: string, palette: string[], source: string, fallbackUsed: boolean): void {
  const outputPath = path.join(root, "frontend", "src", "theme", "brand.generated.ts");
  const semanticPalette = buildSemanticPalette(palette);
  const content = `// AUTO-GENERATED by scripts/extract-palette.ts
// If logo file is replaced, re-run: npm run extract-palette
${fallbackUsed ? "// TODO: logo not found; fallback palette applied.\n" : ""}

export const brandPalette = ${JSON.stringify(semanticPalette, null, 2)} as const;

export const brandColors = {
  primary: brandPalette[0],
  secondary: brandPalette[1],
  accent: brandPalette[2],
  paper: brandPalette[3],
  ink: brandPalette[4],
  mist: brandPalette[5],
  glow: brandPalette[6],
} as const;

export const brandMeta = {
  generatedAt: "${new Date().toISOString()}",
  source: "${source}",
  fallbackUsed: ${fallbackUsed},
} as const;
`;

  fs.writeFileSync(outputPath, content, "utf8");
  console.log(`Generated palette: ${outputPath}`);
}

function main(): void {
  const root = detectRepoRoot();
  const logoPath = findLogo(root);

  if (!logoPath) {
    generateFile(root, FALLBACK, "not-found", true);
    return;
  }

  try {
    const palette = extractFromLogo(root, logoPath);
    generateFile(root, palette, path.relative(root, logoPath), false);
  } catch (error) {
    console.error("Palette extraction failed, fallback used:", error);
    generateFile(root, FALLBACK, path.relative(root, logoPath), true);
  }
}

main();
