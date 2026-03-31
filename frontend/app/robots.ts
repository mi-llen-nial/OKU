import type { MetadataRoute } from "next";

import { absoluteUrl, siteUrl } from "@/src/config/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/students", "/teachers", "/institutions", "/about", "/price", "/user-agreement"],
        disallow: [
          "/login",
          "/register",
          "/dashboard",
          "/test",
          "/results",
          "/history",
          "/progress",
          "/profile",
          "/blitz",
          "/my-group",
          "/teacher",
          "/institution-admin",
          "/methodist",
          "/superadmin",
          "/activate",
        ],
      },
    ],
    sitemap: absoluteUrl("/sitemap.xml"),
    host: siteUrl.replace(/^https?:\/\//, ""),
  };
}
