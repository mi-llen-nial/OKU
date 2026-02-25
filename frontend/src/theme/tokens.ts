import { brandColors } from "@/src/theme/brand.generated";

export const tokens = {
  colors: {
    brand: {
      ...brandColors,
      primary: "#5d6bff",
      secondary: "#7a85ff",
      accent: "#aeb8ff",
      paper: "#f5f7fc",
      ink: "#111827",
      mist: "#eef2ff",
      glow: "#dbe2ff",
    },
    success: "#169f71",
    danger: "#dc3f3f",
    warning: "#f59e0b",
    line: "#e5eaf2",
    panel: "#ffffff",
    panelStrong: "#f9fbff",
    surface: "#f4f7fb",
    muted: "#5d677b",
  },
  radius: {
    sm: "8px",
    md: "12px",
    lg: "16px",
    pill: "999px",
  },
  shadow: {
    soft: "0 1px 2px rgba(15, 23, 42, 0.04), 0 10px 24px rgba(15, 23, 42, 0.06)",
    focus: "0 0 0 3px rgba(93, 107, 255, 0.2)",
    glow: "0 6px 18px rgba(93, 107, 255, 0.28)",
  },
  spacing: {
    xs: "6px",
    sm: "10px",
    md: "14px",
    lg: "20px",
    xl: "28px",
  },
} as const;

export type Tokens = typeof tokens;
