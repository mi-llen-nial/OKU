"use client";

import { Activity, Clock3, Target } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import StatWidget from "@/components/ui/StatWidget";
import { generateMistakesTest, getHistory, getProgress } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { HistoryItem, StudentProgress } from "@/lib/types";
import styles from "@/app/dashboard/dashboard.module.css";

interface RecommendationCard {
  id: string;
  title: string;
  text: string;
  badge: string;
  action: string;
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

  const recentAttempts = useMemo(() => history.slice(0, 4), [history]);

  const recommendations = useMemo<RecommendationCard[]>(() => {
    const weakTopic = progress?.weak_topics[0] || "слабым темам";
    const hasAttempts = history.length > 0;

    return [
      {
        id: "review-errors",
        title: "Повторение ошибок",
        text: "Короткая практика по вопросам, где вы ошибались в последних попытках.",
        badge: "Приоритет",
        action: "Открыть тесты",
        kind: "mistakes",
      },
      {
        id: "weak-topic",
        title: `Фокус: ${weakTopic}`,
        text: "Сконцентрируйтесь на самой слабой теме, чтобы поднять общий балл.",
        badge: "Персонально",
        action: "Начать тренировку",
        kind: "link",
        href: "/test",
      },
      {
        id: "control",
        title: hasAttempts ? "Контрольный тест" : "Первый диагностический тест",
        text: hasAttempts
          ? "Проверьте прогресс после повторения и сравните результат с предыдущими тестами."
          : "Сделайте первую попытку, чтобы система собрала базовый профиль знаний.",
        badge: "Рекомендуем",
        action: hasAttempts ? "Пройти тест" : "Запустить первый тест",
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
          <Card title="Главная">Загрузка...</Card>
        </AppShell>
      </AuthGuard>
    );
  }

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <div className={styles.page}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Главная</h2>
              <p className={styles.sectionSubtitle}>Краткий срез вашего текущего прогресса.</p>
            </div>

            <div className={styles.statGrid}>
              <StatWidget
                label="Средний балл"
                value={`${progress?.avg_percent ?? 0}%`}
                meta="по всем попыткам"
                icon={<Activity size={16} />}
              />
              <StatWidget
                label="Лучший результат"
                value={`${progress?.best_percent ?? 0}%`}
                meta="лучший тест"
                icon={<Target size={16} />}
              />
              <StatWidget
                label="Всего тестов"
                value={`${progress?.total_tests ?? 0}`}
                meta="накопленная история"
                icon={<Clock3 size={16} />}
              />
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Недавно вы проходили...</h2>
              <p className={styles.sectionSubtitle}>Последние попытки и текущий уровень результатов.</p>
            </div>

            <Card>
              {error && <div className="errorText">{error}</div>}

              {recentAttempts.length === 0 ? (
                <div className={styles.emptyState}>
                  <p className="muted">У вас пока нет завершённых тестов. Начните первую попытку, чтобы увидеть историю.</p>
                  <Button onClick={() => router.push("/test")}>Пройти первый тест</Button>
                </div>
              ) : (
                <div className={styles.recentList}>
                  {recentAttempts.map((item) => (
                    <article className={styles.recentItem} key={item.test_id}>
                      <div className={styles.recentItemHead}>
                        <strong>{item.subject_name}</strong>
                        <Badge variant="info">{item.percent}%</Badge>
                      </div>
                      <div className={styles.recentMeta}>{new Date(item.created_at).toLocaleString()}</div>
                      <div className="inline" style={{ flexWrap: "wrap" }}>
                        <Badge>{item.mode}</Badge>
                        <Badge>{item.difficulty}</Badge>
                        <Badge>{item.language}</Badge>
                      </div>
                      <Button variant="secondary" onClick={() => router.push(`/results/${item.test_id}`)}>
                        Открыть результат
                      </Button>
                    </article>
                  ))}
                </div>
              )}

              <div className={styles.sectionActions}>
                <Button variant="secondary" onClick={() => router.push("/history")}>Вся история</Button>
                <Button variant="ghost" onClick={() => router.push("/test")}>Перейти к тестам</Button>
              </div>
            </Card>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Рекомендуем</h2>
              <p className={styles.sectionSubtitle}>Что стоит пройти дальше, чтобы улучшить результат.</p>
            </div>

            <div className={styles.recommendGrid}>
              {recommendations.map((item) => (
                <article className={styles.recommendCard} key={item.id}>
                  <Badge variant="normal" className={styles.recommendBadge}>{item.badge}</Badge>
                  <h4 className={styles.recommendTitle}>{item.title}</h4>
                  <p className={styles.recommendText}>{item.text}</p>
                  {item.kind === "mistakes" ? (
                    <Button variant="secondary" disabled={launchingMistakes} onClick={openMistakesReview}>
                      {launchingMistakes ? "Подготавливаем..." : item.action}
                    </Button>
                  ) : (
                    <Button variant="secondary" onClick={() => router.push(item.href || "/test")}>
                      {item.action}
                    </Button>
                  )}
                </article>
              ))}
            </div>
          </section>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
