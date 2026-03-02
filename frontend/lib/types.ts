export type UserRole = "student" | "teacher";
export type InvitationStatus = "pending" | "accepted" | "declined";
export type Difficulty = "easy" | "medium" | "hard";
export type Language = "RU" | "KZ";
export type Mode = "text" | "audio" | "oral";
export type EducationLevel = "school" | "college" | "university";
export type ExamKind = "ent" | "ielts";

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
  full_name?: string | null;
  username: string;
  preferred_language?: Language | null;
  education_level?: EducationLevel | null;
  direction?: string | null;
  group_id?: number | null;
}

export interface AuthResponse {
  access_token: string;
  refresh_token?: string | null;
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
  time_limit_seconds?: number | null;
  warning_limit?: number | null;
  exam_kind?: ExamKind | null;
  exam_config_json?: {
    title?: string;
    total_questions?: number;
    max_score?: number;
    pass_score?: number;
    auto_submit_on_warning?: boolean;
    sections?: Array<{
      code: string;
      title: string;
      duration_minutes?: number | null;
      question_count: number;
    }>;
  } | null;
  created_at: string;
  questions: Question[];
}

export interface TestWarningSignal {
  type: string;
  at_seconds: number;
  question_id?: number | null;
  details?: Record<string, unknown>;
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
    elapsed_seconds: number;
    time_limit_seconds?: number | null;
    warning_count: number;
  };
  integrity_warnings: TestWarningSignal[];
  feedback: QuestionFeedback[];
  recommendation: Recommendation;
}

export interface HistoryItem {
  test_id: number;
  subject_id: number;
  subject_name: string;
  exam_kind?: ExamKind | null;
  difficulty: Difficulty;
  language: Language;
  mode: Mode;
  created_at: string;
  percent: number;
  warning_count: number;
  weak_topics: string[];
}

export interface StudentProgress {
  total_tests: number;
  total_warnings: number;
  avg_percent: number;
  best_percent: number;
  weak_topics: string[];
  trend: Array<{ date: string; percent: number }>;
  subject_stats: Array<{ subject_id: number; subject_name: string; tests_count: number; avg_percent: number }>;
}

export interface StudentDashboard {
  progress: StudentProgress;
  history: HistoryItem[];
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

export interface TeacherGroup {
  id: number;
  name: string;
  members_count: number;
}

export interface TeacherGroupMember {
  student_id: number;
  username: string;
  full_name?: string | null;
  tests_count: number;
  avg_percent: number;
  warnings_count: number;
  weak_topic?: string | null;
  last_activity_at?: string | null;
}

export interface TeacherGroupMembers {
  id: number;
  name: string;
  members: TeacherGroupMember[];
}

export interface TeacherInvitation {
  id: number;
  teacher_id: number;
  teacher_name: string;
  student_id: number;
  student_username: string;
  student_name?: string | null;
  group_id?: number | null;
  group_name?: string | null;
  status: InvitationStatus;
  created_at: string;
  responded_at?: string | null;
}

export type TeacherCustomAnswerType = "choice" | "free_text";

export interface TeacherCustomGroupBrief {
  id: number;
  name: string;
}

export interface TeacherCustomQuestionInput {
  prompt: string;
  answer_type: TeacherCustomAnswerType;
  options?: string[];
  correct_option_index?: number | null;
  sample_answer?: string | null;
}

export interface TeacherCustomTest {
  id: number;
  title: string;
  duration_minutes: number;
  warning_limit: number;
  questions_count: number;
  groups: TeacherCustomGroupBrief[];
  created_at: string;
  updated_at: string;
}

export interface TeacherCustomQuestion {
  id: number;
  order_index: number;
  prompt: string;
  answer_type: TeacherCustomAnswerType;
  options: string[];
  correct_option_index?: number | null;
  sample_answer?: string | null;
}

export interface TeacherCustomTestDetails extends TeacherCustomTest {
  questions: TeacherCustomQuestion[];
}

export interface GroupAssignedTest {
  custom_test_id: number;
  title: string;
  questions_count: number;
  duration_minutes: number;
  warning_limit: number;
  teacher_name: string;
  group_id: number;
  group_name: string;
  created_at: string;
}

export interface ProfileInvitation {
  id: number;
  teacher_id: number;
  teacher_name: string;
  group_id?: number | null;
  group_name?: string | null;
  status: InvitationStatus;
  created_at: string;
  responded_at?: string | null;
}

export interface ProfileData {
  id: number;
  role: UserRole;
  email: string;
  full_name?: string | null;
  username: string;
  preferred_language?: Language | null;
  education_level?: EducationLevel | null;
  direction?: string | null;
  group_id?: number | null;
  group_name?: string | null;
  invitations: ProfileInvitation[];
}
