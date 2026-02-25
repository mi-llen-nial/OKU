"use client";

import Link from "next/link";
import { BookCheck, Gauge, Target } from "lucide-react";
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
          <Card title="История">Загрузка...</Card>
        </AppShell>
      </AuthGuard>
    );
  }

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <section className={styles.stats}>
          <StatWidget label="Тестов" value={`${progress?.total_tests ?? 0}`} icon={<BookCheck size={16} />} />
          <StatWidget label="Средний" value={`${progress?.avg_percent ?? 0}%`} icon={<Gauge size={16} />} />
          <StatWidget label="Лучший" value={`${progress?.best_percent ?? 0}%`} icon={<Target size={16} />} />
        </section>

        <div className="grid2">
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

        <Card title="История попыток" subtitle="Каждая попытка хранит результат, режим и слабые темы.">
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
      </AppShell>
    </AuthGuard>
  );
}
