import type { MetadataRoute } from "next";

import { absoluteUrl } from "@/src/config/site";

/** Public marketing URLs (oku.com.kz). Auth and app live on app.oku.com.kz and are not indexed here. */
const PUBLIC_ROUTES = ["/", "/students", "/teachers", "/institutions", "/about", "/price", "/user-agreement"] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return PUBLIC_ROUTES.map((route) => ({
    url: absoluteUrl(route),
    lastModified: now,
    changeFrequency: route === "/" ? "weekly" : "monthly",
    priority: route === "/" ? 1 : 0.7,
  }));
}
