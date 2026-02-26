import { AuthResponse, User } from "@/lib/types";

const TOKEN_KEY = "oku_token";
const USER_KEY = "oku_user";

function readSessionValue(key: string): string | null {
  if (typeof window === "undefined") return null;

  const scoped = sessionStorage.getItem(key);
  if (scoped) {
    return scoped;
  }

  // Legacy migration: previous builds used localStorage.
  const legacy = localStorage.getItem(key);
  if (legacy) {
    sessionStorage.setItem(key, legacy);
    localStorage.removeItem(key);
  }
  return legacy;
}

export function saveSession(payload: AuthResponse) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(TOKEN_KEY, payload.access_token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(payload.user));
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function clearSession() {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getToken(): string | null {
  return readSessionValue(TOKEN_KEY);
}

export function getUser(): User | null {
  const raw = readSessionValue(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}
