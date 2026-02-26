"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { generateMistakesTest, getHistory, getProgress } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { HistoryItem, StudentProgress } from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/app/history/history.module.css";

const INITIAL_VISIBLE_TESTS = 5;
const LOAD_MORE_STEP = 10;

interface RecommendationCard {
  id: string;
  label: string;
  title: string;
  text: string;
  action: string;
  icon: string;
  kind: "link" | "mistakes";
  href?: string;
}

export default function HistoryPage() {
  const router = useRouter();

  const [progress, setProgress] = useState<StudentProgress | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE_TESTS);
  const [loading, setLoading] = useState(true);
  const [launchingMistakes, setLaunchingMistakes] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    Promise.all([getProgress(token), getHistory(token)])
      .then(([progressData, historyData]) => {
        setProgress(progressData);
        setHistory(historyData);
        setVisibleCount(INITIAL_VISIBLE_TESTS);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить историю"))
      .finally(() => setLoading(false));
  }, []);

  const sortedByPercent = useMemo(
    () => history.slice().sort((left, right) => right.percent - left.percent),
    [history],
  );
  const bestAttempt = sortedByPercent[0] || null;
  const worstAttempt = sortedByPercent[sortedByPercent.length - 1] || null;

  const favoriteSubject = useMemo(() => {
    if (history.length === 0) return "Нет данных";
    const counter = new Map<string, number>();
    for (const item of history) {
      const title = attemptTitle(item);
      counter.set(title, (counter.get(title) || 0) + 1);
    }
    return [...counter.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] || "Нет данных";
  }, [history]);

  const alignmentPercent = useMemo(() => {
    const avg = progress?.avg_percent ?? 0;
    const warningPenalty = Math.min(progress?.total_warnings ?? 0, 15);
    return Math.max(0, Math.min(100, Math.round(avg * 0.8 + 50 - warningPenalty)));
  }, [progress?.avg_percent, progress?.total_warnings]);

  const visibleHistory = useMemo(() => history.slice(0, visibleCount), [history, visibleCount]);
  const hasMoreHistory = visibleCount < history.length;

  const recommendations = useMemo<RecommendationCard[]>(() => {
    const weakTopic = progress?.weak_topics[0] || "Слабая тема";
    const hasAttempts = history.length > 0;

    return [
      {
        id: "review-errors",
        label: "Приоритет для вас",
        title: "Работа над ошибками",
        text: "Короткая практика по вопросам, где вы ошибались в последних попытках.",
        action: "Начать",
        icon: assetPaths.icons.repeat,
        kind: "mistakes",
      },
      {
        id: "weak-topic",
        label: "Самая слабая тема",
        title: weakTopic,
        text: "Сконцентрируйтесь на самой слабой теме, чтобы поднять общий балл.",
        action: "Начать",
        icon: assetPaths.icons.weakTopic,
        kind: "link",
        href: "/test",
      },
      {
        id: "control",
        label: "Для вас",
        title: hasAttempts ? "Контрольный тест" : "Первый тест",
        text: hasAttempts
          ? "Проверьте прогресс после повторения и сравните результат с предыдущими тестами."
          : "Сделайте первую попытку, чтобы система собрала базовый профиль знаний.",
        action: "Начать",
        icon: assetPaths.icons.lesson,
        kind: "link",
        href: "/test",
      },
    ];
  }, [history.length, progress?.weak_topics]);

  const openMistakesReview = async () => {
    const token = getToken();
    if (!token) return;

    try {
      setLaunchingMistakes(true);
      setError("");
      const test = await generateMistakesTest(token, { num_questions: 10 });
      router.push(`/test/${test.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось подготовить повторение ошибок");
    } finally {
      setLaunchingMistakes(false);
    }
  };

  if (loading) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <div className={styles.page}>
            <Card title="История">Загрузка...</Card>
          </div>
        </AppShell>
      </AuthGuard>
    );
  }

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <div className={styles.page}>
          <section className={`${styles.section} ${styles.primarySection}`}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>История</h2>
              <p className={styles.sectionSubtitle}>Краткий пересказ вашего текущего прогресса</p>
            </div>

            <div className={styles.metricsGrid}>
              <article className={styles.metricItem}>
                <h3 className={styles.metricLabel}>Средняя успеваемость</h3>
                <p className={styles.metricMeta}>По всем попыткам</p>
                <p className={styles.metricValue}>{formatPercent(progress?.avg_percent ?? 0)}</p>
              </article>

              <article className={styles.metricItem}>
                <h3 className={styles.metricLabel}>Лучший результат</h3>
                <p className={styles.metricMeta}>
                  {bestAttempt ? `${attemptTitle(bestAttempt)} (${difficultyLabel(bestAttempt.difficulty)})` : "Пока нет данных"}
                </p>
                <p className={styles.metricValue}>{formatPercent(progress?.best_percent ?? 0)}</p>
              </article>

              <article className={styles.metricItem}>
                <h3 className={styles.metricLabel}>Всего тестов</h3>
                <p className={styles.metricMeta}>За все время</p>
                <p className={styles.metricValue}>{progress?.total_tests ?? 0}</p>
              </article>

              <article className={styles.metricItem}>
                <h3 className={styles.metricLabel}>Соответствие</h3>
                <p className={styles.metricMeta}>Относительно образования</p>
                <p className={styles.metricValue}>{alignmentPercent}%</p>
              </article>

              <article className={styles.metricItem}>
                <h3 className={styles.metricLabel}>Худший результат</h3>
                <p className={styles.metricMeta}>
                  {worstAttempt ? `${attemptTitle(worstAttempt)} (${difficultyLabel(worstAttempt.difficulty)})` : "Пока нет данных"}
                </p>
                <p className={styles.metricValue}>{worstAttempt ? formatPercent(worstAttempt.percent) : "0%"}</p>
              </article>

              <article className={styles.metricItem}>
                <h3 className={styles.metricLabel}>Любимчик</h3>
                <p className={styles.metricMeta}>Наиболее часто проходимый</p>
                <p className={styles.metricValueText}>{formatSubjectTitle(favoriteSubject)}</p>
              </article>
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>История тестов</h2>
              <p className={styles.sectionSubtitle}>Последние попытки и текущий уровень результатов</p>
            </div>

            {error && <div className="errorText">{error}</div>}

            {visibleHistory.length === 0 ? (
              <div className={styles.emptyState}>
                <p className={styles.emptyText}>У вас пока нет завершенных тестов.</p>
                <Button onClick={() => router.push("/test")}>Пройти первый тест</Button>
              </div>
            ) : (
              <>
                <div className={styles.attemptList}>
                  {visibleHistory.map((item) => {
                    const scoreClass = resolveScoreClass(item.percent);
                    const title = attemptTitle(item);

                    return (
                      <article className={styles.attemptCard} key={item.test_id}>
                        <div className={styles.attemptHead}>
                          <p className={styles.attemptDate}>{formatRelativeDate(item.created_at)}</p>
                          <div className={styles.attemptMeta}>
                            <p className={`${styles.attemptScore} ${styles[scoreClass]}`}>{formatPercent(item.percent)}</p>
                            <p className={styles.metaStrong}>{difficultyLabel(item.difficulty)}</p>
                            <p className={styles.metaStrong}>{modeLabel(item.mode)}</p>
                            <p className={styles.metaStrong}>Предупреждений: {item.warning_count}</p>
                          </div>
                        </div>

                        <div className={styles.attemptBody}>
                          <img className={styles.attemptIcon} src={resolveSubjectIcon(title)} alt={title} />
                          <div className={styles.attemptInfo}>
                            <h3 className={styles.attemptTitle}>{title}</h3>
                            <p className={styles.attemptTopics}>
                              {item.weak_topics.length > 0 ? item.weak_topics.slice(0, 3).join("   ") : "Сильное прохождение"}
                            </p>
                          </div>
                        </div>

                        <Button block className={styles.resultButton} onClick={() => router.push(`/results/${item.test_id}`)}>
                          Результаты
                        </Button>
                      </article>
                    );
                  })}
                </div>

                {hasMoreHistory ? (
                  <button
                    className={styles.showMoreButton}
                    type="button"
                    onClick={() => setVisibleCount((prev) => Math.min(prev + LOAD_MORE_STEP, history.length))}
                  >
                    Показать больше
                  </button>
                ) : null}
              </>
            )}
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>Рекомендуем</h2>
              <p className={styles.sectionSubtitle}>Основаны на ваших тестах и результатах</p>
            </div>

            <div className={styles.recommendGrid}>
              {recommendations.map((item) => (
                <article className={styles.recommendCard} key={item.id}>
                  <p className={styles.recommendLabel}>{item.label}</p>
                  <div className={styles.recommendTop}>
                    <img className={styles.recommendIcon} src={item.icon} alt={item.title} />
                    <div className={styles.recommendInfo}>
                      <h3 className={styles.recommendTitle}>{item.title}</h3>
                      <p className={styles.recommendText}>{item.text}</p>
                    </div>
                  </div>
                  {item.kind === "mistakes" ? (
                    <Button className={styles.recommendAction} disabled={launchingMistakes} block onClick={openMistakesReview}>
                      {launchingMistakes ? "Подготавливаем..." : item.action}
                    </Button>
                  ) : (
                    <Button className={styles.recommendAction} block onClick={() => router.push(item.href || "/test")}>
                      {item.action}
                    </Button>
                  )}
                </article>
              ))}
            </div>
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
  if (key.includes("ielts")) return assetPaths.icons.ielts;
  if (key.includes("ент") || key.includes("ent")) return assetPaths.icons.ent;
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

function difficultyLabel(value: HistoryItem["difficulty"]): string {
  if (value === "easy") return "Легкий";
  if (value === "hard") return "Сложный";
  return "Средний";
}

function attemptTitle(item: Pick<HistoryItem, "subject_name" | "exam_kind">): string {
  if (item.exam_kind === "ielts") return "IELTS";
  if (item.exam_kind === "ent") return "ЕНТ";
  return item.subject_name;
}

function modeLabel(value: HistoryItem["mode"]): string {
  if (value === "audio") return "Аудио";
  if (value === "oral") return "Устный";
  return "Стандарт";
}

function formatRelativeDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Недавно";

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(date);
  target.setHours(0, 0, 0, 0);
  const diffDays = Math.round((today.getTime() - target.getTime()) / 86_400_000);

  if (diffDays === 0) return "Сегодня";
  if (diffDays === 1) return "Вчера";
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

function formatPercent(value: number): string {
  const rounded = Math.round((value || 0) * 10) / 10;
  if (Number.isInteger(rounded)) {
    return `${rounded.toFixed(0)}%`;
  }
  return `${rounded.toFixed(1)}%`;
}

function formatSubjectTitle(value: string): string {
  if (!value || value === "Нет данных") return "Нет данных";
  const normalized = normalizeText(value);
  if (normalized.includes("ielts")) return "IELTS";
  if (normalized.includes("ент") || normalized.includes("ent")) return "ЕНТ";
  return value
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function resolveScoreClass(percent: number): "scoreSuccess" | "scoreWarning" | "scoreDanger" {
  if (percent >= 75) return "scoreSuccess";
  if (percent >= 50) return "scoreWarning";
  return "scoreDanger";
}
