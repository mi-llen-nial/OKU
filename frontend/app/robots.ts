import type { MetadataRoute } from "next";

import { absoluteUrl, siteUrl } from "@/src/config/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/login", "/register"],
        disallow: [
          "/dashboard",
          "/test",
          "/results",
          "/history",
          "/progress",
          "/profile",
          "/blitz",
          "/my-group",
          "/teacher",
        ],
      },
    ],
    sitemap: absoluteUrl("/sitemap.xml"),
    host: siteUrl,
  };
}
