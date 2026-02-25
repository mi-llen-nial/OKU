"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import { generateMistakesTest, getHistory, getProgress } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { HistoryItem, StudentProgress } from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/app/dashboard/dashboard.module.css";

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

export default function DashboardPage() {
  const router = useRouter();

  const [progress, setProgress] = useState<StudentProgress | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
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
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Cannot load dashboard data"))
      .finally(() => setLoading(false));
  }, []);

  const recentAttempts = useMemo(() => history.slice(0, 3), [history]);
  const bestAttempt = useMemo(
    () => history.slice().sort((left, right) => right.percent - left.percent)[0] || null,
    [history],
  );

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
          <div className={styles.pageLoading}>Загрузка...</div>
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
              <h2 className={styles.sectionTitle}>Главная</h2>
              <p className={styles.sectionSubtitle}>Краткий пересказ вашего текущего прогресса</p>
            </div>

            <div className={styles.statsRow}>
              <article className={styles.statItem}>
                <h3 className={styles.statLabel}>Средняя успеваемость</h3>
                <p className={styles.statMeta}>По всем попыткам</p>
                <p className={styles.statValue}>{progress?.avg_percent ?? 0}%</p>
              </article>

              <article className={styles.statItem}>
                <h3 className={styles.statLabel}>Лучший результат</h3>
                <p className={styles.statMeta}>
                  {bestAttempt ? `${bestAttempt.subject_name} (${difficultyLabel(bestAttempt.difficulty)})` : "Пока нет данных"}
                </p>
                <p className={styles.statValue}>{progress?.best_percent ?? 0}%</p>
              </article>

              <article className={styles.statItem}>
                <h3 className={styles.statLabel}>Всего тестов</h3>
                <p className={styles.statMeta}>За все время</p>
                <p className={styles.statValue}>{progress?.total_tests ?? 0}</p>
              </article>
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>Недавно вы проходили...</h2>
              <p className={styles.sectionSubtitle}>Последние попытки и текущий уровень результатов</p>
            </div>

            {error && <div className="errorText">{error}</div>}

            {recentAttempts.length === 0 ? (
              <div className={styles.emptyState}>
                <p className={styles.emptyText}>У вас пока нет завершенных тестов.</p>
                <Button onClick={() => router.push("/test")}>Пройти первый тест</Button>
              </div>
            ) : (
              <>
                <div className={styles.cardGrid}>
                  {recentAttempts.map((item) => {
                    const scoreClass = resolveScoreClass(item.percent);

                    return (
                      <article className={styles.recentCard} key={item.test_id}>
                        <p className={styles.cardDate}>{formatRelativeDate(item.created_at)}</p>

                        <div className={styles.cardTop}>
                          <img
                            className={styles.cardIcon}
                            src={resolveSubjectIcon(item.subject_name)}
                            alt={item.subject_name}
                          />
                          <div className={styles.cardInfo}>
                            <h3 className={styles.cardTitle}>{item.subject_name}</h3>
                            <p className={styles.cardMeta}>
                              {difficultyLabel(item.difficulty)}&nbsp;&nbsp;
                              {languageLabel(item.language)}&nbsp;&nbsp;
                              #{item.test_id}
                            </p>
                          </div>
                          <p className={`${styles.scoreValue} ${styles[scoreClass]}`}>{item.percent}%</p>
                        </div>

                        <div className={styles.cardActions}>
                          <Button onClick={() => router.push("/test")}>Повторить</Button>
                          <button
                            type="button"
                            className={styles.linkButton}
                            onClick={() => router.push(`/results/${item.test_id}`)}
                          >
                            Результаты
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>

                <button type="button" className={styles.showAllButton} onClick={() => router.push("/history")}>
                  Показать все
                </button>
              </>
            )}
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>Рекомендуем</h2>
              <p className={styles.sectionSubtitle}>Основаны на ваших тестах и результатах</p>
            </div>

            <div className={styles.cardGrid}>
              {recommendations.map((item) => (
                <article className={styles.recommendCard} key={item.id}>
                  <p className={styles.cardDate}>{item.label}</p>
                  <div className={styles.cardTop}>
                    <img className={styles.cardIcon} src={item.icon} alt={item.title} />
                    <div className={styles.cardInfo}>
                      <h3 className={styles.cardTitle}>{item.title}</h3>
                      <p className={styles.cardMeta}>{item.text}</p>
                    </div>
                  </div>
                  {item.kind === "mistakes" ? (
                    <Button disabled={launchingMistakes} block onClick={openMistakesReview}>
                      {launchingMistakes ? "Подготавливаем..." : item.action}
                    </Button>
                  ) : (
                    <Button block onClick={() => router.push(item.href || "/test")}>
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

function languageLabel(value: HistoryItem["language"]): string {
  return value === "KZ" ? "Каз" : "Рус";
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
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function resolveScoreClass(percent: number): "scoreSuccess" | "scoreWarning" | "scoreDanger" {
  if (percent >= 75) return "scoreSuccess";
  if (percent >= 50) return "scoreWarning";
  return "scoreDanger";
}
