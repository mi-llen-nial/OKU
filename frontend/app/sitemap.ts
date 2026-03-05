import type { MetadataRoute } from "next";

import { absoluteUrl } from "@/src/config/site";

const PUBLIC_ROUTES = ["/", "/login", "/register"] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return PUBLIC_ROUTES.map((route) => ({
    url: absoluteUrl(route),
    lastModified: now,
    changeFrequency: route === "/" ? "weekly" : "monthly",
    priority: route === "/" ? 1 : 0.6,
  }));
}
