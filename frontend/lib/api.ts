import {
  AuthResponse,
  InstitutionAdminBootstrapInviteResponse,
  InstitutionGroup,
  InstitutionGroupDetails,
  InstitutionListItem,
  InstitutionMember,
  ReviewDetails,
  ReviewQueueItem,
  SuperadminInstitutionDetails,
  SuperadminInstitutionListResponse,
  GroupInviteAcceptResponse,
  GroupInvitePreview,
  GroupAssignedTest,
  GroupAnalytics,
  HistoryItem,
  ProfileData,
  ProfileInvitation,
  TeacherCustomMaterialGenerateResponse,
  TeacherCustomMaterialParseResponse,
  TeacherCustomQuestionInput,
  TeacherApplication,
  TeacherApplicationDecisionAction,
  TeacherAssignApprovedTestResponse,
  TeacherCustomTestResultsResponse,
  TeacherSubmitReviewResponse,
  TeacherCustomTest,
  TeacherCustomTestDetails,
  TeacherGroup,
  TeacherGroupInviteLink,
  TeacherGroupMembers,
  TeacherInvitation,
  GroupWeakTopics,
  StudentProgress,
  StudentDashboard,
  Subject,
  Test,
  TestResult,
} from "@/lib/types";
import { getRefreshToken, getUser, updateAccessToken } from "@/lib/auth";
import { getUiLanguage } from "@/lib/i18n";

const RAW_API_URL = (process.env.NEXT_PUBLIC_API_URL || "").trim();
const API_PREFIX = normalizeApiPrefix(process.env.NEXT_PUBLIC_API_PREFIX || "/api/v1");
const API_URL = resolveApiUrl();
const API_BASE = `${API_URL}${API_PREFIX}`;
const API_BASE_FALLBACK = API_PREFIX ? API_URL : null;

const CACHE_NS = "oku_cache";
const CACHE_TTL = {
  subjects: 6 * 60 * 60 * 1000,
  progress: 30 * 1000,
  history: 30 * 1000,
  dashboard: 30 * 1000,
  teacherGroups: 60 * 1000,
  teacherGroupMembers: 45 * 1000,
  teacherInvitations: 30 * 1000,
  teacherGroupAnalytics: 45 * 1000,
  teacherGroupWeakTopics: 45 * 1000,
  teacherStudentProgress: 45 * 1000,
  teacherStudentHistory: 45 * 1000,
  teacherCustomTests: 30 * 1000,
  teacherCustomTestDetails: 30 * 1000,
  teacherCustomTestResults: 60 * 1000,
  studentGroupTests: 30 * 1000,
  profile: 20 * 1000,
} as const;

let refreshPromise: Promise<string | null> | null = null;
const inflightCacheRequests = new Map<string, Promise<unknown>>();

interface ApiRequestConfig {
  timeoutMs?: number;
}

function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const name = (error as { name?: string }).name || "";
  return name === "AbortError" || name === "TimeoutError";
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
  config?: ApiRequestConfig,
): Promise<T> {
  const headers = new Headers(options.headers || {});
  const hasFormDataBody = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (!hasFormDataBody && options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (hasFormDataBody) {
    headers.delete("Content-Type");
  }
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const timeoutMs = Math.max(0, Number(config?.timeoutMs || 0));
  const externalSignal = options.signal;
  const timeoutController =
    typeof AbortController !== "undefined" && timeoutMs > 0 ? new AbortController() : null;
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
  let onExternalAbort: (() => void) | null = null;

  if (timeoutController) {
    if (externalSignal?.aborted) {
      timeoutController.abort();
    } else if (externalSignal) {
      onExternalAbort = () => timeoutController.abort();
      externalSignal.addEventListener("abort", onExternalAbort, { once: true });
    }
    timeoutHandle = setTimeout(() => {
      timeoutController.abort();
    }, timeoutMs);
  }

  const performRequest = async (baseUrl: string) =>
    fetch(`${baseUrl}${path}`, {
      ...options,
      headers,
      signal: timeoutController?.signal ?? externalSignal,
      cache: "no-store",
      credentials: "include",
    });

  try {
    const baseCandidates = buildApiBaseCandidates();
    let currentBaseUrl = baseCandidates[0] ?? API_BASE;
    let response: Response | null = null;
    let fallbackHttpResponse: Response | null = null;
    let lastFetchError: unknown = null;

    for (let index = 0; index < baseCandidates.length; index += 1) {
      const baseUrl = baseCandidates[index];
      const hasNextCandidate = index < baseCandidates.length - 1;
      try {
        const attempt = await performRequest(baseUrl);
        if (shouldTryNextCandidate(attempt, hasNextCandidate)) {
          fallbackHttpResponse = attempt;
          continue;
        }
        response = attempt;
        currentBaseUrl = baseUrl;
        break;
      } catch (error) {
        if (isAbortError(error)) {
          throw new Error("Превышено время ожидания ответа сервера. Попробуйте снова.");
        }
        lastFetchError = error;
      }
    }

    if (!response && fallbackHttpResponse) {
      response = fallbackHttpResponse;
    }

    if (!response) {
      if (lastFetchError instanceof Error && lastFetchError.message.trim()) {
        throw new Error(lastFetchError.message);
      }
      throw new Error("NetworkError when attempting to fetch resource.");
    }

    if (
      response.status === 401 &&
      token &&
      !path.startsWith("/auth/login") &&
      !path.startsWith("/auth/register") &&
      !path.startsWith("/auth/refresh")
    ) {
      const refreshedAccessToken = await tryRefreshToken();
      if (refreshedAccessToken) {
        headers.set("Authorization", `Bearer ${refreshedAccessToken}`);
        response = await performRequest(currentBaseUrl);
      }
    }

    if (!response.ok) {
      const detail = await extractErrorFromResponse(
        response,
        `Request failed / Сұрау қатесі: ${response.status}`,
      );
      throw new Error(detail);
    }

    if (response.status === 204) {
      return {} as T;
    }
    const contentLength = response.headers.get("content-length");
    if (contentLength === "0") {
      return {} as T;
    }

    return (await response.json()) as T;
  } finally {
    if (timeoutHandle) {
      clearTimeout(timeoutHandle);
    }
    if (externalSignal && onExternalAbort) {
      externalSignal.removeEventListener("abort", onExternalAbort);
    }
  }
}

function normalizeApiPrefix(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

function userScopedCacheKey(key: string): string | null {
  if (typeof window === "undefined") return null;
  const user = getUser();
  if (!user) return null;
  return `${CACHE_NS}:${user.id}:${key}`;
}

function readCachedJson<T>(key: string, ttlMs: number): T | null {
  if (typeof window === "undefined") return null;
  const scopedKey = userScopedCacheKey(key);
  if (!scopedKey) return null;
  try {
    const raw = localStorage.getItem(scopedKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { ts: number; payload: T };
    if (!parsed || typeof parsed.ts !== "number") return null;
    if (Date.now() - parsed.ts > ttlMs) return null;
    return parsed.payload;
  } catch {
    return null;
  }
}

function writeCachedJson<T>(key: string, payload: T): void {
  if (typeof window === "undefined") return;
  const scopedKey = userScopedCacheKey(key);
  if (!scopedKey) return;
  try {
    localStorage.setItem(
      scopedKey,
      JSON.stringify({
        ts: Date.now(),
        payload,
      }),
    );
  } catch {
    // no-op
  }
}

function clearCachedKey(key: string): void {
  if (typeof window === "undefined") return;
  const scopedKey = userScopedCacheKey(key);
  if (!scopedKey) return;
  localStorage.removeItem(scopedKey);
}

function clearCachedPrefix(prefix: string): void {
  if (typeof window === "undefined") return;
  const user = getUser();
  if (!user) return;
  const scopedPrefix = `${CACHE_NS}:${user.id}:${prefix}`;
  const keysToDelete: string[] = [];
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (key && key.startsWith(scopedPrefix)) {
      keysToDelete.push(key);
    }
  }
  for (const key of keysToDelete) {
    localStorage.removeItem(key);
  }
}

async function cachedRequest<T>(
  key: string,
  ttlMs: number,
  loader: () => Promise<T>,
): Promise<T> {
  const cached = readCachedJson<T>(key, ttlMs);
  if (cached !== null) {
    return cached;
  }

  const inflight = inflightCacheRequests.get(key);
  if (inflight) {
    return inflight as Promise<T>;
  }

  const request = loader()
    .then((payload) => {
      writeCachedJson(key, payload);
      return payload;
    })
    .finally(() => {
      inflightCacheRequests.delete(key);
    });

  inflightCacheRequests.set(key, request as Promise<unknown>);
  return request;
}

async function inflightRequest<T>(key: string, loader: () => Promise<T>): Promise<T> {
  const inflightKey = `inflight:${key}`;
  const inflight = inflightCacheRequests.get(inflightKey);
  if (inflight) {
    return inflight as Promise<T>;
  }

  const request = loader().finally(() => {
    inflightCacheRequests.delete(inflightKey);
  });

  inflightCacheRequests.set(inflightKey, request as Promise<unknown>);
  return request;
}

function invalidateStudentCaches(): void {
  clearCachedPrefix("history:");
  clearCachedPrefix("progress:");
  clearCachedPrefix("dashboard:");
  clearCachedKey("student:group-tests");
}

function languageAwareCacheKey(baseKey: "history" | "progress" | "dashboard"): string {
  return `${baseKey}:${getUiLanguage()}`;
}

function invalidateTeacherCache(options?: {
  groupId?: number;
  studentId?: number;
  clearAllGroups?: boolean;
  clearCustomTests?: boolean;
}): void {
  const groupId = options?.groupId;
  const studentId = options?.studentId;

  if (options?.clearAllGroups) {
    clearCachedPrefix("teacher:group:");
    clearCachedKey("teacher:groups");
  }

  if (options?.clearCustomTests) {
    clearCachedKey("teacher:custom-tests");
    clearCachedPrefix("teacher:custom-test:");
  }

  if (typeof groupId === "number") {
    clearCachedKey(`teacher:group:${groupId}:members`);
    clearCachedKey(`teacher:group:${groupId}:analytics`);
    clearCachedKey(`teacher:group:${groupId}:weak-topics`);
    clearCachedKey("teacher:groups");
  }

  if (typeof studentId === "number") {
    clearCachedKey(`teacher:student:${studentId}:progress`);
    clearCachedKey(`teacher:student:${studentId}:history`);
  }

  clearCachedKey("teacher:invitations");
}

function invalidateProfileCache(): void {
  clearCachedKey("profile:me");
}

function extractErrorDetail(value: unknown): string | null {
  if (typeof value === "string") {
    const normalized = value.trim();
    return normalized.length > 0 ? normalized : null;
  }

  if (Array.isArray(value)) {
    const parts = value
      .map((item) => extractErrorDetail(item))
      .filter((item): item is string => Boolean(item));
    if (parts.length === 0) return null;
    return parts.join("; ");
  }

  if (!value || typeof value !== "object") {
    return null;
  }

  const payload = value as Record<string, unknown>;
  const preferredKeys = [
    "detail",
    "message",
    "msg",
    "error",
    "non_field_errors",
  ] as const;

  for (const key of preferredKeys) {
    const next = extractErrorDetail(payload[key]);
    if (next) return next;
  }

  const loc = Array.isArray(payload.loc)
    ? payload.loc.map((part) => String(part)).join(".")
    : typeof payload.loc === "string"
      ? payload.loc
      : "";
  const msg = extractErrorDetail(payload.msg ?? payload.message ?? payload.error);
  if (msg) {
    return loc ? `${loc}: ${msg}` : msg;
  }

  const nestedParts = Object.values(payload)
    .map((item) => extractErrorDetail(item))
    .filter((item): item is string => Boolean(item));
  if (nestedParts.length === 0) return null;
  return nestedParts.join("; ");
}

async function extractErrorFromResponse(
  response: Response,
  fallback: string,
): Promise<string> {
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    try {
      const payload = await response.json();
      const detail = extractErrorDetail(payload);
      if (detail) return detail;
    } catch {
      // ignore parse errors and continue with fallback
    }
  }

  try {
    const text = (await response.text()).trim();
    if (text.length === 0) return fallback;
    if (looksLikeHtmlPayload(text, contentType)) {
      return fallback;
    }
    return text.length > 280 ? `${text.slice(0, 280)}...` : text;
  } catch {
    // ignore parse errors and continue with fallback
  }

  return fallback;
}

async function tryRefreshToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken();
  }
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();

  const requestRefresh = async (baseUrl: string) =>
    fetch(`${baseUrl}/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: refreshToken ? JSON.stringify({ refresh_token: refreshToken }) : undefined,
    });

  const baseCandidates = buildApiBaseCandidates();
  let response: Response | null = null;
  for (let index = 0; index < baseCandidates.length; index += 1) {
    const baseUrl = baseCandidates[index];
    const hasNextCandidate = index < baseCandidates.length - 1;
    try {
      const attempt = await requestRefresh(baseUrl);
      if (shouldTryNextCandidate(attempt, hasNextCandidate)) {
        continue;
      }
      response = attempt;
      break;
    } catch {
      // try next candidate
    }
  }
  if (!response) return null;
  if (!response.ok) return null;

  const payload = (await response.json()) as { access_token?: string; refresh_token?: string | null };
  if (!payload.access_token) return null;
  updateAccessToken(payload.access_token, payload.refresh_token ?? refreshToken ?? null);
  return payload.access_token;
}

function isLocalHost(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase();
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1";
}

function inferApiUrlFromWindow(): string | null {
  if (typeof window === "undefined") return null;
  const { protocol, hostname } = window.location;
  if (!hostname) return null;

  if (hostname.startsWith("api.")) {
    return `${protocol}//${hostname}`;
  }

  if (isLocalHost(hostname)) {
    return `${protocol}//${hostname}:8000`;
  }

  const baseHostname = hostname.startsWith("www.") ? hostname.slice(4) : hostname;
  return `${protocol}//api.${baseHostname}`;
}

function resolveApiUrl(): string {
  const inferredApiUrl = inferApiUrlFromWindow();
  if (RAW_API_URL) {
    try {
      const parsed = new URL(RAW_API_URL);
      if (typeof window !== "undefined" && inferredApiUrl) {
        const browserHost = window.location.hostname;
        if (isLocalHost(parsed.hostname) && !isLocalHost(browserHost)) {
          return inferredApiUrl;
        }
      }
    } catch {
      // keep RAW_API_URL as-is for backward compatibility
    }
    return RAW_API_URL;
  }

  if (inferredApiUrl) {
    return inferredApiUrl;
  }

  if (process.env.NODE_ENV === "production") {
    return "https://api.oku.com.kz";
  }

  return "http://localhost:8000";
}

function buildApiBaseCandidates(): string[] {
  const inferredApiUrl = inferApiUrlFromWindow();
  const candidates: string[] = [API_BASE];

  if (inferredApiUrl) {
    candidates.push(`${inferredApiUrl}${API_PREFIX}`);
  }

  if (API_BASE_FALLBACK) {
    candidates.push(API_BASE_FALLBACK);
  }

  if (inferredApiUrl && API_PREFIX) {
    candidates.push(inferredApiUrl);
  }

  if (typeof window !== "undefined" && window.location.origin) {
    const rawApi = RAW_API_URL.trim();
    const sameOriginApiRequested = rawApi.startsWith("/");
    if (sameOriginApiRequested) {
      const origin = window.location.origin;
      candidates.push(`${origin}${API_PREFIX}`);
      if (API_PREFIX) {
        candidates.push(origin);
      }
    }
  }

  return [...new Set(candidates.filter((value) => value && value.trim().length > 0))];
}

function shouldTryNextCandidate(response: Response, hasNextCandidate: boolean): boolean {
  if (!hasNextCandidate) return false;
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (contentType.includes("text/html")) return true;
  if (response.status === 404 && !contentType.includes("application/json")) return true;
  return false;
}

function looksLikeHtmlPayload(text: string, contentType: string): boolean {
  const normalizedContentType = contentType.toLowerCase();
  if (normalizedContentType.includes("text/html")) return true;
  const probe = text.slice(0, 200).toLowerCase();
  return probe.includes("<!doctype html") || probe.includes("<html");
}

export function register(body: {
  email: string;
  full_name: string;
  username: string;
  password: string;
  email_verification_code: string;
  role: "student" | "teacher";
  preferred_language: "RU" | "KZ";
  education_level?: "school" | "college" | "university" | null;
  direction?: string | null;
  group_id?: number | null;
}) {
  return apiRequest<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function sendRegisterCode(body: { email: string }) {
  return apiRequest<{ message: string; expires_in_seconds: number }>("/auth/register/send-code", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function checkUsernameAvailable(username: string) {
  const q = encodeURIComponent(username.trim());
  return apiRequest<{ available: boolean; reason?: "invalid" | "taken" | null }>(
    `/auth/register/username-available?username=${q}`,
    { method: "GET" },
  );
}

export function checkInstitutionJoinCode(code: string) {
  const q = encodeURIComponent(code.trim());
  return apiRequest<{ valid: boolean; institution_id?: number; name?: string }>(
    `/auth/register/institution-code?code=${q}`,
    { method: "GET" },
  );
}

export function login(body: { email: string; password: string; remember_me?: boolean }) {
  return apiRequest<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function requestPasswordReset(body: { email: string }) {
  return apiRequest<{ message: string }>("/auth/password-reset/request", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function confirmPasswordReset(body: {
  token: string;
  new_password: string;
  confirm_password: string;
}) {
  return apiRequest<{ message: string }>("/auth/password-reset/confirm", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getSubjects(token: string) {
  return cachedRequest(
    "subjects",
    CACHE_TTL.subjects,
    () => apiRequest<Subject[]>("/subjects", {}, token),
  );
}

export function generateTest(
  token: string,
  body: {
    subject_id: number;
    difficulty: "easy" | "medium" | "hard";
    language: "RU" | "KZ";
    mode: "text" | "audio" | "oral";
    num_questions: number;
    time_limit_minutes?: 5 | 10 | 20 | 30 | 60;
  },
) {
  return apiRequest<Test>("/tests/generate", {
    method: "POST",
    body: JSON.stringify(body),
  }, token);
}

export function generateExamTest(
  token: string,
  body: {
    exam_type: "ent" | "ielts";
    language: "RU" | "KZ";
    ent_profile_subject_id?: number;
  },
) {
  return apiRequest<Test>("/tests/generate-exam", {
    method: "POST",
    body: JSON.stringify(body),
  }, token);
}

export function generateMistakesTest(
  token: string,
  body: {
    subject_id?: number;
    difficulty?: "easy" | "medium" | "hard";
    language?: "RU" | "KZ";
    num_questions?: number;
  } = {},
) {
  return apiRequest<Test>("/tests/generate-from-mistakes", {
    method: "POST",
    body: JSON.stringify(body),
  }, token);
}

export function generateGroupAssignedTest(token: string, customTestId: number) {
  return apiRequest<Test>(`/tests/generate-from-custom/${customTestId}`, {
    method: "POST",
  }, token);
}

export function getTest(token: string, testId: number) {
  return inflightRequest(
    `test:${testId}:${token}`,
    () => apiRequest<Test>(`/tests/${testId}`, {}, token),
  );
}

export async function getQuestionTtsAudio(token: string, testId: number, questionId: number) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 20000);

  let response: Response | null = null;
  try {
    const baseCandidates = buildApiBaseCandidates();
    let lastFetchError: unknown = null;
    for (let index = 0; index < baseCandidates.length; index += 1) {
      const baseUrl = baseCandidates[index];
      const hasNextCandidate = index < baseCandidates.length - 1;
      try {
        const attempt = await fetch(`${baseUrl}/tests/${testId}/questions/${questionId}/tts`, {
          method: "GET",
          headers: {
            Authorization: `Bearer ${token}`,
          },
          cache: "no-store",
          credentials: "include",
          signal: controller.signal,
        });
        if (shouldTryNextCandidate(attempt, hasNextCandidate)) {
          continue;
        }
        response = attempt;
        break;
      } catch (error) {
        lastFetchError = error;
      }
    }
    if (!response) {
      if (lastFetchError instanceof Error) {
        throw lastFetchError;
      }
      throw new Error("NetworkError when attempting to fetch resource.");
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Превышено время ожидания серверного TTS.");
    }
    if (error instanceof Error) {
      throw error;
    }
    throw new Error("Не удалось выполнить запрос TTS.");
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response) {
    throw new Error("Не удалось выполнить запрос TTS.");
  }

  if (!response.ok) {
    const detail = await extractErrorFromResponse(
      response,
      `Request failed / Сұрау қатесі: ${response.status}`,
    );
    throw new Error(detail);
  }

  return response.blob();
}

export function submitTest(
  token: string,
  testId: number,
  body: {
    answers: Array<{ question_id: number; student_answer_json: Record<string, unknown> }>;
    telemetry?: {
      elapsed_seconds?: number;
      warnings?: Array<{
        type: string;
        at_seconds: number;
        question_id?: number | null;
        details?: Record<string, unknown>;
      }>;
    };
  },
) {
  return apiRequest<TestResult>(`/tests/${testId}/submit`, {
    method: "POST",
    body: JSON.stringify(body),
  }, token).then((payload) => {
    invalidateStudentCaches();
    return payload;
  });
}

export function getTestResult(token: string, testId: number) {
  return inflightRequest(
    `test-result:${testId}:${token}`,
    () => apiRequest<TestResult>(`/tests/${testId}/result`, {}, token),
  );
}

export function regenerateRecommendation(token: string, testId: number) {
  return apiRequest<TestResult["recommendation"]>(`/tests/${testId}/recommendations/regenerate`, {
    method: "POST",
  }, token).then((payload) => {
    invalidateStudentCaches();
    return payload;
  });
}

export function getHistory(token: string) {
  const cacheKey = languageAwareCacheKey("history");
  return cachedRequest(
    cacheKey,
    CACHE_TTL.history,
    () => apiRequest<HistoryItem[]>("/students/me/history", {}, token),
  );
}

export function getProgress(token: string) {
  const cacheKey = languageAwareCacheKey("progress");
  return cachedRequest(
    cacheKey,
    CACHE_TTL.progress,
    () => apiRequest<StudentProgress>("/students/me/progress", {}, token),
  );
}

export function getDashboard(token: string) {
  const dashboardCacheKey = languageAwareCacheKey("dashboard");
  const progressCacheKey = languageAwareCacheKey("progress");
  const historyCacheKey = languageAwareCacheKey("history");
  return cachedRequest(
    dashboardCacheKey,
    CACHE_TTL.dashboard,
    () => apiRequest<StudentDashboard>("/students/me/dashboard", {}, token).then((payload) => {
      // Keep dedicated caches warm for pages that still call individual endpoints.
      writeCachedJson(progressCacheKey, payload.progress);
      writeCachedJson(historyCacheKey, payload.history);
      return payload;
    }),
  );
}

export async function getStudentGroupTests(token: string, options?: { force?: boolean }) {
  if (options?.force) {
    const payload = await apiRequest<GroupAssignedTest[]>("/students/me/group-tests", {}, token);
    writeCachedJson("student:group-tests", payload);
    return payload;
  }
  return cachedRequest(
    "student:group-tests",
    CACHE_TTL.studentGroupTests,
    () => apiRequest<GroupAssignedTest[]>("/students/me/group-tests", {}, token),
  );
}

export function getGroupAnalytics(token: string, groupId: number) {
  return cachedRequest(
    `teacher:group:${groupId}:analytics`,
    CACHE_TTL.teacherGroupAnalytics,
    () => apiRequest<GroupAnalytics>(`/teacher/groups/${groupId}/analytics`, {}, token),
  );
}

export function getGroupWeakTopics(token: string, groupId: number) {
  return cachedRequest(
    `teacher:group:${groupId}:weak-topics`,
    CACHE_TTL.teacherGroupWeakTopics,
    () => apiRequest<GroupWeakTopics>(`/teacher/groups/${groupId}/weak-topics`, {}, token),
  );
}

export function getStudentProgressByTeacher(token: string, studentId: number) {
  return cachedRequest(
    `teacher:student:${studentId}:progress`,
    CACHE_TTL.teacherStudentProgress,
    () => apiRequest<StudentProgress>(`/teacher/students/${studentId}/progress`, {}, token),
  );
}

export function getStudentHistoryByTeacher(token: string, studentId: number) {
  return cachedRequest(
    `teacher:student:${studentId}:history`,
    CACHE_TTL.teacherStudentHistory,
    () => apiRequest<HistoryItem[]>(`/teacher/students/${studentId}/history`, {}, token),
  );
}

export async function getTeacherGroups(token: string, options?: { force?: boolean }) {
  if (options?.force) {
    const payload = await apiRequest<TeacherGroup[]>("/teacher/groups", {}, token);
    writeCachedJson("teacher:groups", payload);
    return payload;
  }
  return cachedRequest(
    "teacher:groups",
    CACHE_TTL.teacherGroups,
    () => apiRequest<TeacherGroup[]>("/teacher/groups", {}, token),
  );
}

export function createTeacherGroup(
  token: string,
  body: { name: string; student_ids?: number[] },
) {
  return apiRequest<TeacherGroup>("/teacher/groups", {
    method: "POST",
    body: JSON.stringify(body),
  }, token).then((payload) => {
    invalidateTeacherCache({ clearAllGroups: true });
    return payload;
  });
}

export function updateTeacherGroup(
  token: string,
  groupId: number,
  body: { name: string },
) {
  return apiRequest<TeacherGroup>(`/teacher/groups/${groupId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  }, token).then((payload) => {
    invalidateTeacherCache({
      groupId,
      clearAllGroups: true,
    });
    return payload;
  });
}

export function deleteTeacherGroup(token: string, groupId: number) {
  return apiRequest<{}>(`/teacher/groups/${groupId}`, {
    method: "DELETE",
  }, token).then((payload) => {
    invalidateTeacherCache({
      groupId,
      clearAllGroups: true,
    });
    return payload;
  });
}

export function getTeacherGroupMembers(token: string, groupId: number) {
  return cachedRequest(
    `teacher:group:${groupId}:members`,
    CACHE_TTL.teacherGroupMembers,
    () => apiRequest<TeacherGroupMembers>(`/teacher/groups/${groupId}/members`, {}, token),
  );
}

export function sendTeacherInvitation(token: string, body: { username: string; group_id?: number }) {
  return apiRequest<TeacherInvitation>("/teacher/invitations", {
    method: "POST",
    body: JSON.stringify(body),
  }, token).then((payload) => {
    invalidateTeacherCache({
      groupId: typeof body.group_id === "number" ? body.group_id : undefined,
      clearAllGroups: true,
    });
    return payload;
  });
}

export function createTeacherGroupInviteLink(token: string, groupId: number) {
  return apiRequest<TeacherGroupInviteLink>(`/teacher/groups/${groupId}/invite-link`, {
    method: "POST",
  }, token);
}

export function getTeacherInvitations(token: string) {
  return cachedRequest(
    "teacher:invitations",
    CACHE_TTL.teacherInvitations,
    () => apiRequest<TeacherInvitation[]>("/teacher/invitations", {}, token),
  );
}

export function cancelTeacherInvitation(token: string, invitationId: number) {
  return apiRequest<{}>(`/teacher/invitations/${invitationId}`, {
    method: "DELETE",
  }, token).then((payload) => {
    invalidateTeacherCache({ clearAllGroups: true });
    return payload;
  });
}

export function removeTeacherGroupMember(token: string, groupId: number, studentId: number) {
  return apiRequest<{}>(`/teacher/groups/${groupId}/members/${studentId}`, {
    method: "DELETE",
  }, token).then((payload) => {
    invalidateTeacherCache({
      groupId,
      studentId,
      clearAllGroups: true,
    });
    return payload;
  });
}

export function getTeacherCustomTests(token: string) {
  return cachedRequest(
    "teacher:custom-tests",
    CACHE_TTL.teacherCustomTests,
    () => apiRequest<TeacherCustomTest[]>("/teacher/custom-tests", {}, token),
  );
}

export function getTeacherCustomTest(token: string, customTestId: number) {
  return cachedRequest(
    `teacher:custom-test:${customTestId}`,
    CACHE_TTL.teacherCustomTestDetails,
    () => apiRequest<TeacherCustomTestDetails>(`/teacher/custom-tests/${customTestId}`, {}, token),
  );
}

export function createTeacherCustomTest(
  token: string,
  body: {
    title: string;
    duration_minutes: number;
    warning_limit: number;
    due_date?: string | null;
    group_ids: number[];
    questions: TeacherCustomQuestionInput[];
  },
) {
  return apiRequest<TeacherCustomTestDetails>("/teacher/custom-tests", {
    method: "POST",
    body: JSON.stringify(body),
  }, token).then((payload) => {
    invalidateTeacherCache({ clearCustomTests: true });
    return payload;
  });
}

export function updateTeacherCustomTest(
  token: string,
  customTestId: number,
  body: {
    title: string;
    duration_minutes: number;
    warning_limit: number;
    due_date?: string | null;
    group_ids: number[];
    questions: TeacherCustomQuestionInput[];
  },
) {
  return apiRequest<TeacherCustomTestDetails>(`/teacher/custom-tests/${customTestId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  }, token).then((payload) => {
    invalidateTeacherCache({ clearCustomTests: true });
    return payload;
  });
}

export function submitTeacherCustomTestForReview(token: string, customTestId: number) {
  return apiRequest<TeacherSubmitReviewResponse>(`/teacher/custom-tests/${customTestId}/submit-review`, {
    method: "POST",
  }, token).then((payload) => {
    invalidateTeacherCache({ clearCustomTests: true });
    return payload;
  });
}

export function assignTeacherCustomTestToGroups(
  token: string,
  customTestId: number,
  groupIds: number[],
) {
  return apiRequest<TeacherAssignApprovedTestResponse>(`/teacher/custom-tests/${customTestId}/assign`, {
    method: "POST",
    body: JSON.stringify({ group_ids: groupIds }),
  }, token).then((payload) => {
    invalidateTeacherCache({ clearCustomTests: true, clearAllGroups: true });
    invalidateStudentCaches();
    return payload;
  });
}

export function createTeacherApplication(
  token: string,
  body: {
    institution_id?: number;
    institution_name?: string;
    full_name: string;
    email: string;
    subject?: string;
    position?: string;
    additional_info?: string;
  },
) {
  return apiRequest<TeacherApplication>("/teacher-applications", {
    method: "POST",
    body: JSON.stringify(body),
  }, token);
}

export function getMyTeacherApplications(token: string) {
  return apiRequest<TeacherApplication[]>("/teacher-applications/me", {}, token);
}

export function getAdminInstitutions(token: string) {
  return apiRequest<InstitutionListItem[]>("/institution-admin/institutions", {}, token);
}

export function getInstitutionTeacherApplications(
  token: string,
  institutionId: number,
  statusFilter?: "pending" | "approved" | "rejected" | "suspended" | "revoked",
) {
  const params = new URLSearchParams();
  if (statusFilter) {
    params.set("status_filter", statusFilter);
  }
  const suffix = params.toString();
  return apiRequest<TeacherApplication[]>(
    `/institution-admin/institutions/${institutionId}/teacher-applications${suffix ? `?${suffix}` : ""}`,
    {},
    token,
  );
}

export function decideInstitutionTeacherApplication(
  token: string,
  institutionId: number,
  applicationId: number,
  body: {
    action: TeacherApplicationDecisionAction;
    comment?: string;
  },
) {
  return apiRequest<TeacherApplication>(
    `/institution-admin/institutions/${institutionId}/teacher-applications/${applicationId}/decision`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    token,
  );
}

export function getInstitutionStaff(token: string, institutionId: number) {
  return apiRequest<InstitutionMember[]>(
    `/institution-admin/institutions/${institutionId}/staff`,
    {},
    token,
  );
}

export function assignInstitutionMethodist(
  token: string,
  institutionId: number,
  userId: number,
  makePrimary = false,
) {
  return apiRequest<InstitutionMember>(
    `/institution-admin/institutions/${institutionId}/methodists`,
    {
      method: "POST",
      body: JSON.stringify({ user_id: userId, make_primary: makePrimary }),
    },
    token,
  );
}

export function getInstitutionGroups(token: string, institutionId: number) {
  return apiRequest<InstitutionGroup[]>(
    `/institution-admin/institutions/${institutionId}/groups`,
    {},
    token,
  );
}

export function createInstitutionGroup(
  token: string,
  institutionId: number,
  name: string,
) {
  return apiRequest<InstitutionGroup>(
    `/institution-admin/institutions/${institutionId}/groups`,
    {
      method: "POST",
      body: JSON.stringify({ name }),
    },
    token,
  );
}

export function getInstitutionGroupDetails(
  token: string,
  institutionId: number,
  groupId: number,
) {
  return apiRequest<InstitutionGroupDetails>(
    `/institution-admin/institutions/${institutionId}/groups/${groupId}`,
    {},
    token,
  );
}

export function assignTeacherToInstitutionGroup(
  token: string,
  institutionId: number,
  groupId: number,
  teacherMembershipId: number,
) {
  return apiRequest<InstitutionGroup>(
    `/institution-admin/institutions/${institutionId}/groups/${groupId}/teachers`,
    {
      method: "POST",
      body: JSON.stringify({ teacher_membership_id: teacherMembershipId }),
    },
    token,
  );
}

export function addStudentToInstitutionGroup(
  token: string,
  institutionId: number,
  groupId: number,
  studentUserId: number,
) {
  return apiRequest<InstitutionGroupDetails>(
    `/institution-admin/institutions/${institutionId}/groups/${groupId}/students`,
    {
      method: "POST",
      body: JSON.stringify({ student_user_id: studentUserId }),
    },
    token,
  );
}

export function getMethodistInstitutions(token: string) {
  return apiRequest<InstitutionListItem[]>("/methodist/institutions", {}, token);
}

export function getSuperadminInstitutions(token: string) {
  return apiRequest<SuperadminInstitutionListResponse>("/superadmin/institutions", {}, token);
}

export function createSuperadminInstitution(token: string, payload: { name: string }) {
  return apiRequest<SuperadminInstitutionDetails>(
    "/superadmin/institutions",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function getSuperadminInstitution(token: string, institutionId: number) {
  return apiRequest<SuperadminInstitutionDetails>(`/superadmin/institutions/${institutionId}`, {}, token);
}

export function createInstitutionAdminBootstrapInvite(
  token: string,
  institutionId: number,
  payload: { email: string; expires_in_hours?: number; note?: string },
) {
  return apiRequest<InstitutionAdminBootstrapInviteResponse>(
    `/superadmin/institutions/${institutionId}/bootstrap-invites`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function acceptInstitutionAdminBootstrap(payload: {
  token: string;
  email: string;
  full_name: string;
  username: string;
  password: string;
}) {
  return apiRequest<AuthResponse>("/auth/bootstrap/institution-admin/accept", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMethodistReviewQueue(token: string, institutionId: number) {
  return apiRequest<ReviewQueueItem[]>(
    `/methodist/institutions/${institutionId}/reviews`,
    {},
    token,
  );
}

export function getMethodistReviewDetails(
  token: string,
  institutionId: number,
  testId: number,
) {
  return apiRequest<ReviewDetails>(
    `/methodist/institutions/${institutionId}/reviews/${testId}`,
    {},
    token,
  );
}

export function submitMethodistReviewDecision(
  token: string,
  institutionId: number,
  testId: number,
  body: {
    status: "approved" | "rejected" | "needs_revision";
    comment?: string;
  },
) {
  return apiRequest<TeacherSubmitReviewResponse>(
    `/methodist/institutions/${institutionId}/reviews/${testId}/decision`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    token,
  ).then((payload) => {
    invalidateTeacherCache({ clearCustomTests: true, clearAllGroups: true });
    invalidateStudentCaches();
    return payload;
  });
}

export function getTeacherCustomTestResults(
  token: string,
  customTestId: number,
  groupIds: number[] = [],
  options?: { force?: boolean },
) {
  const normalizedGroupIds = [...groupIds]
    .filter((groupId) => Number.isFinite(groupId) && groupId > 0)
    .map((groupId) => Number(groupId))
    .sort((left, right) => left - right);
  const params = new URLSearchParams();
  for (const groupId of normalizedGroupIds) {
    params.append("group_ids", String(groupId));
  }
  const suffix = params.toString();
  const path = `/teacher/custom-tests/${customTestId}/results${suffix ? `?${suffix}` : ""}`;
  const cacheKey = `teacher:custom-test:${customTestId}:results:${suffix || "all"}`;
  if (options?.force) {
    clearCachedKey(cacheKey);
  }
  return cachedRequest(
    cacheKey,
    CACHE_TTL.teacherCustomTestResults,
    () => apiRequest<TeacherCustomTestResultsResponse>(path, {}, token),
  );
}

export async function downloadTeacherCustomTestResultsCsv(
  token: string,
  customTestId: number,
  groupIds: number[] = [],
): Promise<Blob> {
  const params = new URLSearchParams();
  for (const groupId of groupIds) {
    if (Number.isFinite(groupId) && groupId > 0) {
      params.append("group_ids", String(groupId));
    }
  }
  const suffix = params.toString();
  const path = `/teacher/custom-tests/${customTestId}/results.csv${suffix ? `?${suffix}` : ""}`;
  const headers = new Headers({ Authorization: `Bearer ${token}` });

  const baseCandidates = buildApiBaseCandidates();
  let response: Response | null = null;
  let fallbackHttpResponse: Response | null = null;
  let lastFetchError: unknown = null;

  for (let index = 0; index < baseCandidates.length; index += 1) {
    const baseUrl = baseCandidates[index];
    const hasNextCandidate = index < baseCandidates.length - 1;
    try {
      const attempt = await fetch(`${baseUrl}${path}`, {
        method: "GET",
        headers,
        credentials: "include",
        cache: "no-store",
      });
      if (shouldTryNextCandidate(attempt, hasNextCandidate)) {
        fallbackHttpResponse = attempt;
        continue;
      }
      response = attempt;
      break;
    } catch (error) {
      lastFetchError = error;
    }
  }

  if (!response && fallbackHttpResponse) response = fallbackHttpResponse;
  if (!response) {
    if (lastFetchError instanceof Error && lastFetchError.message.trim()) {
      throw new Error(lastFetchError.message);
    }
    throw new Error("NetworkError when attempting to fetch resource.");
  }

  if (!response.ok) {
    const detail = await extractErrorFromResponse(response, `Request failed / Сұрау қатесі: ${response.status}`);
    throw new Error(detail);
  }

  return response.blob();
}

export function generateTeacherCustomTestMaterial(
  token: string,
  body: {
    topic: string;
    difficulty: "easy" | "medium" | "hard";
    questions_count: number;
    language: "RU" | "KZ";
  },
) {
  return apiRequest<TeacherCustomMaterialGenerateResponse>("/teacher/custom-tests/generate-material", {
    method: "POST",
    body: JSON.stringify(body),
  }, token, { timeoutMs: 65_000 });
}

export function parseTeacherCustomTestFile(token: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<TeacherCustomMaterialParseResponse>("/teacher/custom-tests/parse-file", {
    method: "POST",
    body: formData,
  }, token);
}

export function deleteTeacherCustomTest(token: string, customTestId: number) {
  return apiRequest<{}>(`/teacher/custom-tests/${customTestId}`, {
    method: "DELETE",
  }, token).then((payload) => {
    invalidateTeacherCache({ clearCustomTests: true });
    return payload;
  });
}

export function getMyProfile(token: string) {
  return cachedRequest(
    "profile:me",
    CACHE_TTL.profile,
    () => apiRequest<ProfileData>("/profile/me", {}, token),
  );
}

export function respondInvitation(
  token: string,
  invitationId: number,
  action: "accept" | "decline",
) {
  return apiRequest<ProfileInvitation>(`/profile/invitations/${invitationId}/${action}`, {
    method: "POST",
  }, token).then((payload) => {
    invalidateProfileCache();
    invalidateStudentCaches();
    invalidateTeacherCache({ clearAllGroups: true });
    return payload;
  });
}

export function previewGroupInvite(token: string, inviteToken: string) {
  return apiRequest<GroupInvitePreview>(`/profile/group-invites/${encodeURIComponent(inviteToken)}`, {}, token);
}

export function acceptGroupInviteByToken(token: string, inviteToken: string) {
  return apiRequest<GroupInviteAcceptResponse>(`/profile/group-invites/${encodeURIComponent(inviteToken)}/accept`, {
    method: "POST",
  }, token).then((payload) => {
    invalidateProfileCache();
    invalidateStudentCaches();
    invalidateTeacherCache({ clearAllGroups: true });
    return payload;
  });
}
