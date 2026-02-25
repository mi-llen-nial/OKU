"use client";

import Link from "next/link";
import { AlertTriangle, BookCheck, Gauge, Target } from "lucide-react";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import SimpleBarChart from "@/components/SimpleBarChart";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import StatWidget from "@/components/ui/StatWidget";
import { getHistory, getProgress } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { HistoryItem, StudentProgress } from "@/lib/types";
import styles from "@/app/history/history.module.css";

export default function HistoryPage() {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [progress, setProgress] = useState<StudentProgress | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    Promise.all([getHistory(token), getProgress(token)])
      .then(([historyData, progressData]) => {
        setHistory(historyData);
        setProgress(progressData);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Cannot load history"))
      .finally(() => setLoading(false));
  }, []);

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
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>История</h2>
              <p className={styles.sectionSubtitle}>Все ваши завершённые попытки и ключевые показатели.</p>
            </div>

            <section className={styles.stats}>
              <StatWidget label="Тестов" value={`${progress?.total_tests ?? 0}`} icon={<BookCheck size={16} />} />
              <StatWidget label="Средний" value={`${progress?.avg_percent ?? 0}%`} icon={<Gauge size={16} />} />
              <StatWidget label="Лучший" value={`${progress?.best_percent ?? 0}%`} icon={<Target size={16} />} />
              <StatWidget label="Предупреждений" value={`${progress?.total_warnings ?? 0}`} icon={<AlertTriangle size={16} />} />
            </section>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Аналитика</h2>
              <p className={styles.sectionSubtitle}>Динамика результатов и ваши слабые темы.</p>
            </div>

            <div className={styles.analyticsGrid}>
              <Card title="Динамика результатов">
                <SimpleBarChart points={(progress?.trend || []).map((point) => ({ label: point.date.slice(5), value: point.percent }))} />
              </Card>
              <Card title="Слабые темы">
                <div className="stack">
                  {(progress?.weak_topics || ["Недостаточно данных"]).map((topic) => (
                    <Badge key={topic}>{topic}</Badge>
                  ))}
                </div>
              </Card>
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>История попыток</h2>
              <p className={styles.sectionSubtitle}>Каждая попытка хранит результат, режим и слабые темы.</p>
            </div>

            <Card>
              {error && <div className="errorText">{error}</div>}
              <div className={styles.list}>
                {history.map((item) => (
                  <article className={styles.attempt} key={item.test_id}>
                    <div className={styles.head}>
                      <div>
                        <strong>{item.subject_name}</strong>
                        <div className={styles.meta}>{new Date(item.created_at).toLocaleString()}</div>
                      </div>
                      <div className="inline">
                        <Badge variant="info">{item.percent}%</Badge>
                        <Badge variant="normal">Warnings: {item.warning_count}</Badge>
                        <Badge>{item.mode}</Badge>
                        <Badge>{item.difficulty}</Badge>
                      </div>
                    </div>

                    <div className="inline" style={{ flexWrap: "wrap" }}>
                      {item.weak_topics.map((topic) => (
                        <Badge key={`${item.test_id}-${topic}`} variant="normal">
                          {topic}
                        </Badge>
                      ))}
                    </div>

                    <Link href={`/results/${item.test_id}`}>Открыть подробный результат</Link>
                  </article>
                ))}
              </div>
            </Card>
          </section>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
