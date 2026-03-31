import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import Script from "next/script";

import ToastViewport from "@/components/ToastViewport";
import { absoluteUrl, siteConfig, siteUrl } from "@/src/config/site";
import { tokens } from "@/src/theme/tokens";
import "./globals.css";

const bodyFont = Inter({
  subsets: ["latin", "cyrillic"],
  variable: "--font-body",
  display: "swap",
  /** Variable Inter — в CSS можно задавать 350 (regular по макету) и 500 (medium) */
  weight: "variable",
});

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "OKU — образовательная AI-платформа",
    template: "%s | OKU",
  },
  description: siteConfig.description,
  applicationName: siteConfig.name,
  keywords: siteConfig.keywords,
  alternates: {
    canonical: "/",
  },
  robots: {
    index: true,
    follow: true,
    nocache: false,
    googleBot: {
      index: true,
      follow: true,
      "max-snippet": -1,
      "max-image-preview": "large",
      "max-video-preview": -1,
    },
  },
  openGraph: {
    type: "website",
    locale: siteConfig.locale,
    siteName: siteConfig.name,
    title: "OKU — образовательная AI-платформа",
    description: siteConfig.description,
    url: absoluteUrl("/"),
    images: [
      {
        url: siteConfig.ogImage,
        width: 1024,
        height: 1024,
        alt: "Логотип платформы OKU",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "OKU — образовательная AI-платформа",
    description: siteConfig.description,
    images: [siteConfig.ogImage],
  },
  icons: {
    icon: "/assets/logo/logo.svg",
    shortcut: "/assets/logo/logo.svg",
    apple: "/assets/logo/logo.png",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
  themeColor: "#6A63F5",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const websiteJsonLd = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: siteConfig.name,
    url: absoluteUrl("/"),
    description: siteConfig.description,
    inLanguage: ["ru", "kk"],
  };

  const organizationJsonLd = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: siteConfig.name,
    url: absoluteUrl("/"),
    logo: absoluteUrl(siteConfig.ogImage),
    sameAs: [siteConfig.telegram.okuBotUrl, siteConfig.telegram.faqBotUrl],
  };

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
      <body className={`${bodyFont.className} ${bodyFont.variable}`} style={cssVars}>
        <Script id="microsoft-clarity" strategy="afterInteractive">
          {`
            (function(c,l,a,r,i,t,y){
              c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
              t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
              y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
            })(window, document, "clarity", "script", "vu2vopn0lg");
          `}
        </Script>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteJsonLd) }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationJsonLd) }}
        />
        {children}
        <ToastViewport />
      </body>
    </html>
  );
}
