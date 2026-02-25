import {
  AuthResponse,
  GroupAnalytics,
  GroupWeakTopics,
  HistoryItem,
  StudentProgress,
  Subject,
  Test,
  TestResult,
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers || {});
  headers.set("Content-Type", "application/json");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // ignore parse error and keep default message
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export function register(body: {
  email: string;
  username: string;
  password: string;
  role: "student" | "teacher";
  preferred_language: "RU" | "KZ";
  group_id?: number | null;
}) {
  return apiRequest<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function login(body: { email: string; password: string }) {
  return apiRequest<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getSubjects(token: string) {
  return apiRequest<Subject[]>("/subjects", {}, token);
}

export function generateTest(
  token: string,
  body: {
    subject_id: number;
    difficulty: "easy" | "medium" | "hard";
    language: "RU" | "KZ";
    mode: "text" | "audio" | "oral";
    num_questions: number;
  },
) {
  return apiRequest<Test>("/tests/generate", {
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

export function getTest(token: string, testId: number) {
  return apiRequest<Test>(`/tests/${testId}`, {}, token);
}

export function submitTest(
  token: string,
  testId: number,
  body: {
    answers: Array<{ question_id: number; student_answer_json: Record<string, unknown> }>;
  },
) {
  return apiRequest<TestResult>(`/tests/${testId}/submit`, {
    method: "POST",
    body: JSON.stringify(body),
  }, token);
}

export function getTestResult(token: string, testId: number) {
  return apiRequest<TestResult>(`/tests/${testId}/result`, {}, token);
}

export function regenerateRecommendation(token: string, testId: number) {
  return apiRequest<TestResult["recommendation"]>(`/tests/${testId}/recommendations/regenerate`, {
    method: "POST",
  }, token);
}

export function getHistory(token: string) {
  return apiRequest<HistoryItem[]>("/students/me/history", {}, token);
}

export function getProgress(token: string) {
  return apiRequest<StudentProgress>("/students/me/progress", {}, token);
}

export function getGroupAnalytics(token: string, groupId: number) {
  return apiRequest<GroupAnalytics>(`/teacher/groups/${groupId}/analytics`, {}, token);
}

export function getGroupWeakTopics(token: string, groupId: number) {
  return apiRequest<GroupWeakTopics>(`/teacher/groups/${groupId}/weak-topics`, {}, token);
}

export function getStudentProgressByTeacher(token: string, studentId: number) {
  return apiRequest<StudentProgress>(`/teacher/students/${studentId}/progress`, {}, token);
}
