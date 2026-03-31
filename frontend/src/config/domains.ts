/**
 * Public marketing site vs app platform hostnames (oku.com.kz vs app.oku.com.kz).
 * Used by middleware, server components, and client CTAs.
 */

const DEFAULT_PUBLIC_ORIGIN = "https://oku.com.kz";
const DEFAULT_APP_ORIGIN = "https://app.oku.com.kz";
const DEFAULT_PUBLIC_HOSTNAME = "oku.com.kz";
const DEFAULT_APP_HOSTNAME = "app.oku.com.kz";

function normalizeOrigin(raw: string | undefined, fallback: string): string {
  const value = (raw || "").trim();
  if (!value) return fallback;
  try {
    const parsed = new URL(value);
    const protocol = parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.protocol : "https:";
    return `${protocol}//${parsed.host}`;
  } catch {
    return fallback;
  }
}

/** Canonical public marketing site URL (no trailing slash). */
export const publicSiteOrigin = normalizeOrigin(
  process.env.NEXT_PUBLIC_PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_SITE_URL,
  DEFAULT_PUBLIC_ORIGIN,
);

/** Platform app URL (no trailing slash). */
export const appOrigin = normalizeOrigin(process.env.NEXT_PUBLIC_APP_URL, DEFAULT_APP_ORIGIN);

export const publicSiteHostname = (process.env.NEXT_PUBLIC_PUBLIC_HOSTNAME || DEFAULT_PUBLIC_HOSTNAME).toLowerCase();

export const appHostname = (process.env.NEXT_PUBLIC_APP_HOSTNAME || DEFAULT_APP_HOSTNAME).toLowerCase();

/**
 * Force hosting mode for local testing (optional):
 * - "app" | "public" — override hostname detection
 * - unset — use hostname / localhost defaults
 */
export const siteHostingMode = (process.env.NEXT_PUBLIC_SITE_HOSTING || "").trim().toLowerCase();

function hostnameOnly(host: string): string {
  return host.split(":")[0]?.toLowerCase() || "";
}

/** localhost / 127.0.0.1 — лендинг на `/`, без «корня платформы» как на app.* */
export function isLocalDevHostname(host: string): boolean {
  const h = hostnameOnly(host);
  return h === "localhost" || h === "127.0.0.1";
}

/**
 * Server / middleware: whether the request host is the platform app.
 */
export function isAppHostname(host: string): boolean {
  const h = hostnameOnly(host);
  if (h === "localhost" || h === "127.0.0.1") {
    return true;
  }

  if (siteHostingMode === "app") return true;
  if (siteHostingMode === "public") return false;

  if (!h) return true;

  return h === appHostname || h.endsWith(`.${appHostname}`);
}

/**
 * Whether the request is for the public marketing site host.
 */
export function isPublicHostname(host: string): boolean {
  return !isAppHostname(host);
}

/** Paths that belong only to the platform (app subdomain in production). */
export const PLATFORM_PATH_PREFIXES = [
  "/login",
  "/register",
  "/dashboard",
  "/teacher",
  "/test",
  "/profile",
  "/history",
  "/progress",
  "/results",
  "/my-group",
  "/blitz",
  "/superadmin",
  "/institution-admin",
  "/methodist",
  "/activate",
] as const;

/** Marketing routes served on the public site. */
export const PUBLIC_MARKETING_PATHS = [
  "/students",
  "/teachers",
  "/institutions",
  "/about",
  "/price",
  "/user-agreement",
] as const;

export function isPlatformPath(pathname: string): boolean {
  const path = pathname.startsWith("/") ? pathname : `/${pathname}`;
  if (path === "/login" || path === "/register") return true;
  return PLATFORM_PATH_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`));
}

export function isPublicMarketingPath(pathname: string): boolean {
  const path = pathname.startsWith("/") ? pathname : `/${pathname}`;
  return PUBLIC_MARKETING_PATHS.some((p) => path === p || path.startsWith(`${p}/`));
}

/**
 * На localhost и в `next dev` маркетинг и приложение с одного origin — не уводим на прод-домены из env.
 */
function shouldUseSameOriginLinks(): boolean {
  if (typeof window !== "undefined") {
    return isLocalDevHostname(window.location.hostname);
  }
  if (process.env.NODE_ENV === "development") {
    return true;
  }
  const raw = (process.env.NEXT_PUBLIC_APP_URL || "").trim();
  if (!raw) return false;
  try {
    const u = new URL(raw);
    return u.hostname === "localhost" || u.hostname === "127.0.0.1";
  } catch {
    return false;
  }
}

/**
 * Client: build href for platform routes from the public site (absolute URL if needed).
 */
export function appPath(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (shouldUseSameOriginLinks()) {
    return normalized;
  }
  if (typeof window === "undefined") {
    return `${appOrigin}${normalized}`;
  }
  try {
    const current = window.location.origin;
    const app = new URL(appOrigin);
    if (app.origin !== current) {
      return `${appOrigin}${normalized}`;
    }
  } catch {
    return normalized;
  }
  return normalized;
}

/**
 * Client: link to public marketing site from the platform.
 */
export function publicPath(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (shouldUseSameOriginLinks()) {
    return normalized;
  }
  if (typeof window === "undefined") {
    return `${publicSiteOrigin}${normalized}`;
  }
  try {
    const current = window.location.origin;
    const pub = new URL(publicSiteOrigin);
    if (pub.origin !== current) {
      return `${publicSiteOrigin}${normalized}`;
    }
  } catch {
    return normalized;
  }
  return normalized;
}
