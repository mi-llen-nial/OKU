import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { tokens } from "@/src/theme/tokens";
import "./globals.css";

const bodyFont = Inter({
  subsets: ["latin", "cyrillic"],
  variable: "--font-body",
  display: "swap",
});

export const metadata: Metadata = {
  title: "OKU",
  description: "AI-платформа персонализированного тестирования",
  icons: {
    icon: "/assets/logo/logo.svg",
    shortcut: "/assets/logo/logo.svg",
    apple: "/assets/logo.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const cssVars = {
    "--brand-primary": tokens.colors.brand.primary,
    "--brand-secondary": tokens.colors.brand.secondary,
    "--brand-accent": tokens.colors.brand.accent,
    "--brand-paper": tokens.colors.brand.paper,
    "--brand-ink": tokens.colors.brand.ink,
    "--brand-mist": tokens.colors.brand.mist,
    "--brand-glow": tokens.colors.brand.glow,
    "--ink-strong": tokens.colors.brand.ink,
    "--line-color": tokens.colors.line,
    "--panel-base": tokens.colors.panel,
    "--panel-elevated": tokens.colors.panelStrong,
    "--radius-sm": tokens.radius.sm,
    "--radius-md": tokens.radius.md,
    "--radius-lg": tokens.radius.lg,
    "--radius-pill": tokens.radius.pill,
    "--shadow-soft": tokens.shadow.soft,
    "--shadow-glow": tokens.shadow.glow,
  } as React.CSSProperties;

  return (
    <html lang="ru">
      <body className={bodyFont.variable} style={cssVars}>
        {children}
      </body>
    </html>
  );
}
