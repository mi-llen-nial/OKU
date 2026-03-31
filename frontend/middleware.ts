import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import {
  appHostname,
  appOrigin,
  isAppHostname,
  isPlatformPath,
  isPublicMarketingPath,
  publicSiteOrigin,
} from "@/src/config/domains";

function isLocalDevHost(host: string): boolean {
  const h = host.split(":")[0]?.toLowerCase() || "";
  return h === "localhost" || h === "127.0.0.1";
}

function resolveRequestHost(request: NextRequest): string {
  return request.headers.get("x-forwarded-host") || request.headers.get("host") || "";
}

function resolveProto(request: NextRequest): string {
  const forwarded = request.headers.get("x-forwarded-proto");
  if (forwarded === "http" || forwarded === "https") return forwarded;
  return request.nextUrl.protocol.replace(":", "") || "https";
}

function buildOrigin(proto: string, host: string): string {
  return `${proto}://${host}`;
}

function isSameDestination(request: NextRequest, target: URL): boolean {
  const current = request.nextUrl;
  return (
    current.protocol === target.protocol &&
    current.host === target.host &&
    current.pathname === target.pathname &&
    current.search === target.search
  );
}

export function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  const search = request.nextUrl.search;

  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname === "/favicon.ico" ||
    pathname === "/robots.txt" ||
    pathname === "/sitemap.xml"
  ) {
    return NextResponse.next();
  }

  if (/\.(?:svg|png|jpg|jpeg|gif|webp|ico|txt|xml|webmanifest|pdf)$/i.test(pathname)) {
    return NextResponse.next();
  }

  const host = resolveRequestHost(request);
  const proto = resolveProto(request);
  const onApp = isAppHostname(host);

  if (!onApp && isPlatformPath(pathname)) {
    const targetBase = appOrigin || buildOrigin(proto, appHostname);
    const url = new URL(pathname + search, targetBase);
    if (isSameDestination(request, url)) {
      return NextResponse.next();
    }
    return NextResponse.redirect(url);
  }

  if (onApp && isPublicMarketingPath(pathname) && !isLocalDevHost(host)) {
    const pub = publicSiteOrigin;
    const url = new URL(pathname + search, pub);
    if (isSameDestination(request, url)) {
      return NextResponse.next();
    }
    return NextResponse.redirect(url);
  }

  const res = NextResponse.next();
  if (onApp) {
    res.headers.set("X-Robots-Tag", "noindex, nofollow");
  }
  return res;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
