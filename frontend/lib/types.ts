export type UserRole = "student" | "teacher";
export type Difficulty = "easy" | "medium" | "hard";
export type Language = "RU" | "KZ";
export type Mode = "text" | "audio" | "oral";

export type QuestionType =
  | "single_choice"
  | "multi_choice"
  | "short_text"
  | "matching"
  | "oral_answer";

export interface User {
  id: number;
  role: UserRole;
  email: string;
  username: string;
  preferred_language?: Language | null;
  group_id?: number | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Subject {
  id: number;
  name_ru: string;
  name_kz: string;
}

export interface OptionItem {
  id: number;
  text: string;
}

export interface Question {
  id: number;
  type: QuestionType;
  prompt: string;
  options_json?: {
    options?: OptionItem[];
    left?: string[];
    right?: string[];
  } | null;
  tts_text?: string | null;
}

export interface Test {
  id: number;
  student_id: number;
  subject_id: number;
  difficulty: Difficulty;
  language: Language;
  mode: Mode;
  created_at: string;
  questions: Question[];
}

export interface QuestionFeedback {
  question_id: number;
  prompt: string;
  topic: string;
  student_answer: Record<string, unknown>;
  expected_hint: Record<string, unknown>;
  is_correct: boolean;
  score: number;
  explanation: string;
}

export interface Recommendation {
  weak_topics: string[];
  advice_text: string;
  generated_tasks: Array<{ topic: string; task: string; difficulty: string }>;
}

export interface TestResult {
  test_id: number;
  submitted_at?: string;
  result: {
    total_score: number;
    max_score: number;
    percent: number;
  };
  feedback: QuestionFeedback[];
  recommendation: Recommendation;
}

export interface HistoryItem {
  test_id: number;
  subject_id: number;
  subject_name: string;
  difficulty: Difficulty;
  language: Language;
  mode: Mode;
  created_at: string;
  percent: number;
  weak_topics: string[];
}

export interface StudentProgress {
  total_tests: number;
  avg_percent: number;
  best_percent: number;
  weak_topics: string[];
  trend: Array<{ date: string; percent: number }>;
  subject_stats: Array<{ subject_id: number; subject_name: string; tests_count: number; avg_percent: number }>;
}

export interface GroupAnalytics {
  group_id: number;
  group_name: string;
  group_avg_percent: number;
  trend: Array<{ date: string; avg_percent: number }>;
  students: Array<{
    student_id: number;
    student_name: string;
    tests_count: number;
    avg_percent: number;
    last_percent: number | null;
  }>;
}

export interface GroupWeakTopics {
  group_id: number;
  group_name: string;
  weak_topics: Array<{ topic: string; count: number }>;
}
