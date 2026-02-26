"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import { getSubjects, getTest, getTestResult } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { Question, Subject, Test, TestResult } from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/app/results/[id]/results.module.css";

export default function ResultPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const testId = Number(params.id);

  const [data, setData] = useState<TestResult | null>(null);
  const [testMeta, setTestMeta] = useState<Test | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token || Number.isNaN(testId)) {
      setLoading(false);
      setError("Некорректный ID теста.");
      return;
    }

    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError("");

      const [resultResponse, testResponse, subjectsResponse] = await Promise.allSettled([
        getTestResult(token, testId),
        getTest(token, testId),
        getSubjects(token),
      ]);

      if (cancelled) return;

      if (resultResponse.status === "fulfilled") {
        setData(resultResponse.value);
      } else {
        setError(resultResponse.reason instanceof Error ? resultResponse.reason.message : "Не удалось загрузить результат.");
      }

      if (testResponse.status === "fulfilled") {
        setTestMeta(testResponse.value);
      }

      if (subjectsResponse.status === "fulfilled") {
        setSubjects(subjectsResponse.value);
      }

      setLoading(false);
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [testId]);

  const resolvedSubjectName = useMemo(() => {
    if (!testMeta) return "Предмет";
    const subject = subjects.find((item) => item.id === testMeta.subject_id);
    if (!subject) return `Предмет #${testMeta.subject_id}`;
    return testMeta.language === "KZ" ? subject.name_kz : subject.name_ru;
  }, [subjects, testMeta]);

  const examName = useMemo(() => {
    const kind = testMeta?.exam_kind;
    if (!kind) return null;
    return kind === "ent" ? "ЕНТ" : "IELTS";
  }, [testMeta?.exam_kind]);

  const subjectName = examName || resolvedSubjectName;
  const subjectIcon = testMeta?.exam_kind === "ent"
    ? assetPaths.icons.ent
    : testMeta?.exam_kind === "ielts"
      ? assetPaths.icons.ielts
      : resolveSubjectIcon(resolvedSubjectName);
  const subjectLabel = examName ? "Пройденный экзамен" : "Пройденный предмет";
  const subjectMeta = examName
    ? `${languageLabel(testMeta?.language)} · Экзамен`
    : `${difficultyLabel(testMeta?.difficulty)} ${languageLabel(testMeta?.language)}`;
  const modeMetricLabel = examName ? "Формат:" : "Сложность:";
  const modeMetricValue = examName || difficultyLabel(testMeta?.difficulty);
  const recommendationText =
    data?.recommendation.advice_text.trim() || "Рекомендации временно недоступны. Повторите тест или откройте историю попыток.";
  const questionMap = useMemo(() => {
    const map = new Map<number, Question>();
    for (const question of testMeta?.questions || []) {
      map.set(question.id, question);
    }
    return map;
  }, [testMeta?.questions]);

  if (loading) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <div className={styles.page}>
            <section className={styles.stateCard}>Загружаем результаты...</section>
          </div>
        </AppShell>
      </AuthGuard>
    );
  }

  if (!data) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <div className={styles.page}>
            <section className={styles.stateCard}>
              <h2 className={styles.stateTitle}>Результат не найден</h2>
              <p className={styles.stateText}>Проверьте ID теста или откройте историю попыток.</p>
              <Button onClick={() => router.push("/history")}>Открыть историю</Button>
            </section>
          </div>
        </AppShell>
      </AuthGuard>
    );
  }

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <div className={styles.page}>
          <section className={styles.section}>
            <header className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>Итоги теста</h2>
              <p className={styles.sectionSubtitle}>Результат и персональные рекомендации</p>
            </header>

            <div className={styles.summaryGrid}>
              <article className={styles.scoreCard}>
                <p className={styles.scoreLabel}>Ваш результат</p>
                <p className={styles.scorePercent}>{formatPercent(data.result.percent)}</p>

                <div className={styles.metrics}>
                  <p className={styles.metricRow}>
                    <span>Баллы:</span> <b>{formatDecimal(data.result.total_score)} / {formatDecimal(data.result.max_score)}</b>
                  </p>
                  <p className={styles.metricRow}>
                    <span>Время:</span>{" "}
                    <b>
                      {formatDuration(data.result.elapsed_seconds)}
                      {typeof data.result.time_limit_seconds === "number" ? ` / ${formatDuration(data.result.time_limit_seconds)}` : ""}
                    </b>
                  </p>
                  <p className={styles.metricRow}>
                    <span>{modeMetricLabel}</span> <b>{modeMetricValue}</b>
                  </p>
                  <p className={styles.metricRow}>
                    <span>Предупреждений:</span> <b>{data.result.warning_count}</b>
                  </p>
                </div>

                <div className={styles.subjectBlock}>
                  <p className={styles.subjectLabel}>{subjectLabel}</p>
                  <div className={styles.subjectRow}>
                    <img className={styles.subjectIcon} src={subjectIcon} alt={subjectName} />
                    <div className={styles.subjectTextGroup}>
                      <p className={styles.subjectName}>{subjectName}</p>
                      <p className={styles.subjectMeta}>{subjectMeta}</p>
                    </div>
                  </div>
                </div>
              </article>

              <article className={styles.recommendationCard}>
                <h3 className={styles.recommendationTitle}>Рекомендации</h3>
                <p className={styles.recommendationSubtitle}>Что повторить и какие задания выполнить дальше.</p>
                <p className={styles.recommendationText}>{recommendationText}</p>
                {data.recommendation.generated_tasks.length > 0 ? (
                  <div className={styles.taskList}>
                    {data.recommendation.generated_tasks.slice(0, 2).map((task, index) => (
                      <p className={styles.taskItem} key={`${task.topic}-${index}`}>
                        <b>{task.topic}:</b> {task.task}
                      </p>
                    ))}
                  </div>
                ) : null}
              </article>
            </div>

            <div className={styles.actionsRow}>
              <Button className={styles.homeButton} onClick={() => router.push("/dashboard")}>
                На главную
              </Button>
              <button className={styles.retryButton} type="button" onClick={() => router.push("/test")}>
                Пройти заново
              </button>
            </div>

            {error ? <p className={styles.errorText}>{error}</p> : null}
          </section>

          <section className={styles.section}>
            <header className={styles.sectionHeader}>
              <h2 className={styles.sectionTitleLeft}>Ошибки и объяснения</h2>
            </header>

            {data.feedback.length === 0 ? (
              <section className={styles.stateCard}>По этому тесту пока нет данных обратной связи.</section>
            ) : (
              <div className={styles.feedbackGrid}>
                {data.feedback.map((item, index) => (
                  <article className={styles.feedbackCard} key={`${item.question_id}-${index}`}>
                    <p className={styles.fieldLabel}>Вопрос</p>
                    <p className={`${styles.questionNumber} ${item.is_correct ? styles.questionCorrect : styles.questionWrong}`}>
                      {index + 1}
                    </p>
                    <p className={styles.questionText}>{sanitizeQuestionPrompt(item.prompt)}</p>

                    <p className={styles.fieldLabel}>Ответ</p>
                    <p className={styles.answerText}>{formatStudentAnswer(item.student_answer, questionMap.get(item.question_id))}</p>

                    <p className={styles.fieldLabel}>Балл</p>
                    <p className={styles.scoreText}>{formatDecimal(item.score)}</p>
                  </article>
                ))}
              </div>
            )}
          </section>

          <footer className={styles.footer}>OKU.com</footer>
        </div>
      </AppShell>
    </AuthGuard>
  );
}

function normalizeText(value: string): string {
  return value
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[^a-zа-я0-9әіңғүұқөһ]/gi, "");
}

function resolveSubjectIcon(subjectName: string): string {
  const key = normalizeText(subjectName);
  if (key.includes("алгебр")) return assetPaths.icons.algebra;
  if (key.includes("геометр")) return assetPaths.icons.geometry;
  if (key.includes("физик")) return assetPaths.icons.physics;
  if (key.includes("русск") || key.includes("орыс")) return assetPaths.icons.russian;
  if (key.includes("англ") || key.includes("агылшын")) return assetPaths.icons.english;
  if (key.includes("биолог")) return assetPaths.icons.biology;
  if (key.includes("хим")) return assetPaths.icons.chemistry;
  if (key.includes("информ")) return assetPaths.icons.informatics;
  if (key.includes("истор") || key.includes("тарих")) return assetPaths.icons.history;
  if (key.includes("матем")) return assetPaths.icons.math;
  return assetPaths.icons.soon;
}

function difficultyLabel(value?: Test["difficulty"]): string {
  if (value === "easy") return "Легкий";
  if (value === "hard") return "Сложный";
  return "Средний";
}

function languageLabel(value?: Test["language"]): string {
  return value === "KZ" ? "Каз" : "Рус";
}

function formatDuration(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds || 0));
  const minutes = Math.floor(safe / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (safe % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function formatPercent(value: number): string {
  const rounded = Math.round((value || 0) * 10) / 10;
  if (Number.isInteger(rounded)) {
    return `${rounded.toFixed(0)}%`;
  }
  return `${rounded.toFixed(1)}%`;
}

function formatDecimal(value: number): string {
  const normalized = Number.isFinite(value) ? value : 0;
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(normalized);
}

function sanitizeQuestionPrompt(prompt: string): string {
  return prompt.replace(/\s*\((вариант|нұсқа)\s*\d+\)\s*$/i, "").trim();
}

function formatStudentAnswer(answer: Record<string, unknown>, question?: Question): string {
  const rawText = [answer.text, answer.spoken_answer_text, answer.transcript].find((value) => typeof value === "string");
  if (typeof rawText === "string" && rawText.trim()) {
    return rawText.trim();
  }

  const optionTexts = answer.selected_option_texts;
  if (Array.isArray(optionTexts)) {
    const textValues = optionTexts.filter((value): value is string => typeof value === "string" && value.trim().length > 0);
    if (textValues.length > 0) return textValues.join(", ");
  }

  const optionIds = answer.selected_option_ids;
  if (Array.isArray(optionIds) && optionIds.length > 0) {
    const options = question?.options_json?.options || [];
    const textById = new Map<number, string>();
    for (const option of options) {
      textById.set(option.id, option.text);
    }
    const selectedTexts = optionIds
      .map((value) => Number(value))
      .map((id) => textById.get(id))
      .filter((value): value is string => typeof value === "string" && value.trim().length > 0);
    if (selectedTexts.length > 0) {
      return selectedTexts.join(", ");
    }
    return optionIds.map((value) => String(value)).join(", ");
  }

  const matches = answer.matches;
  if (matches && typeof matches === "object") {
    const pairs = Object.entries(matches as Record<string, unknown>).map(([left, right]) => `${left} → ${String(right)}`);
    if (pairs.length > 0) return pairs.join("; ");
  }

  return "Ответ не указан";
}
