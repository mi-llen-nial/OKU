import { AuthResponse, User } from "@/lib/types";

const TOKEN_KEY = "oku_token";
const REFRESH_TOKEN_KEY = "oku_refresh_token";
const USER_KEY = "oku_user";
const REMEMBER_ME_KEY = "oku_remember_me";

type StorageKind = "session" | "local";

function getRememberPreference(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(REMEMBER_ME_KEY) === "1";
}

function resolveStorageForRead(): StorageKind | null {
  if (typeof window === "undefined") return null;
  if (sessionStorage.getItem(TOKEN_KEY)) return "session";
  if (localStorage.getItem(TOKEN_KEY)) return "local";
  return getRememberPreference() ? "local" : "session";
}

function readByKey(key: string): string | null {
  if (typeof window === "undefined") return null;
  const sessionValue = sessionStorage.getItem(key);
  if (sessionValue) return sessionValue;
  return localStorage.getItem(key);
}

function clearBoth(key: string): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(key);
  localStorage.removeItem(key);
}

function writeToStorage(kind: StorageKind, key: string, value: string): void {
  if (typeof window === "undefined") return;
  const target = kind === "local" ? localStorage : sessionStorage;
  const secondary = kind === "local" ? sessionStorage : localStorage;
  target.setItem(key, value);
  secondary.removeItem(key);
}

export function saveSession(payload: AuthResponse, options?: { rememberMe?: boolean }) {
  if (typeof window === "undefined") return;
  const rememberMe = Boolean(options?.rememberMe);
  const storage: StorageKind = rememberMe ? "local" : "session";

  localStorage.setItem(REMEMBER_ME_KEY, rememberMe ? "1" : "0");

  writeToStorage(storage, TOKEN_KEY, payload.access_token);
  if (payload.refresh_token) {
    writeToStorage(storage, REFRESH_TOKEN_KEY, payload.refresh_token);
  } else {
    clearBoth(REFRESH_TOKEN_KEY);
  }
  writeToStorage(storage, USER_KEY, JSON.stringify(payload.user));
}

export function clearSession() {
  if (typeof window === "undefined") return;
  clearBoth(TOKEN_KEY);
  clearBoth(REFRESH_TOKEN_KEY);
  clearBoth(USER_KEY);
  localStorage.removeItem(REMEMBER_ME_KEY);
}

export function getToken(): string | null {
  return readByKey(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return readByKey(REFRESH_TOKEN_KEY);
}

export function updateAccessToken(accessToken: string, refreshToken?: string | null) {
  if (typeof window === "undefined") return;
  const storage = resolveStorageForRead() ?? (getRememberPreference() ? "local" : "session");

  writeToStorage(storage, TOKEN_KEY, accessToken);
  if (typeof refreshToken === "string") {
    writeToStorage(storage, REFRESH_TOKEN_KEY, refreshToken);
  } else if (refreshToken === null) {
    clearBoth(REFRESH_TOKEN_KEY);
  }
}

export function getUser(): User | null {
  const raw = readByKey(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function isRememberMeEnabled(): boolean {
  return getRememberPreference();
}
