import { brandColors } from "@/src/theme/brand.generated";

export const tokens = {
  colors: {
    brand: {
      ...brandColors,
      primary: "#6A63F5",
      secondary: "#6A63F5",
      accent: "#D9D7FF",
      paper: "#F1F1F7",
      ink: "#262626",
      mist: "#ECECF4",
      glow: "#DDD9FF",
    },
    success: "#169f71",
    danger: "#dc3f3f",
    warning: "#f59e0b",
    line: "#E2E2EB",
    panel: "#ffffff",
    panelStrong: "#f9fbff",
    surface: "#ECECF4",
    muted: "#626262",
  },
  radius: {
    sm: "8px",
    md: "12px",
    lg: "16px",
    pill: "999px",
  },
  shadow: {
    soft: "0 4px 12px rgba(15, 23, 42, 0.07)",
    focus: "0 0 0 3px rgba(106, 99, 245, 0.2)",
    glow: "0 6px 18px rgba(106, 99, 245, 0.28)",
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
