"use client";

import { AlertTriangle, Flame, LineChart, Shield } from "lucide-react";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import SimpleBarChart from "@/components/SimpleBarChart";
import Badge from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import StatWidget from "@/components/ui/StatWidget";
import { getProgress } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { StudentProgress } from "@/lib/types";
import styles from "@/app/progress/progress.module.css";

export default function ProgressPage() {
  const [progress, setProgress] = useState<StudentProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    getProgress(token)
      .then((payload) => setProgress(payload))
      .catch((err) => setError(err instanceof Error ? err.message : "Cannot load progress"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <div className={styles.page}>
            <Card title="Прогресс">Загрузка...</Card>
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
              <h2 className={styles.sectionTitle}>Прогресс</h2>
              <p className={styles.sectionSubtitle}>Общая динамика и стабильность ваших результатов.</p>
            </div>

            <section className={styles.stats}>
              <StatWidget label="Стабильность" value={`${progress?.avg_percent ?? 0}%`} icon={<Shield size={16} />} />
              <StatWidget label="Пик" value={`${progress?.best_percent ?? 0}%`} icon={<Flame size={16} />} />
              <StatWidget label="Всего попыток" value={`${progress?.total_tests ?? 0}`} icon={<LineChart size={16} />} />
              <StatWidget label="Предупреждения" value={`${progress?.total_warnings ?? 0}`} icon={<AlertTriangle size={16} />} />
            </section>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Аналитика</h2>
              <p className={styles.sectionSubtitle}>Динамика по времени и перечень слабых тем.</p>
            </div>

            <div className={styles.layout}>
              <Card title="Динамика по времени" subtitle="Следите за ростом результата в каждой попытке.">
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
              <h2 className={styles.sectionTitle}>Результаты по предметам</h2>
              <p className={styles.sectionSubtitle}>Средняя успеваемость и количество попыток по каждому предмету.</p>
            </div>

            <Card>
              {error && <div className="errorText">{error}</div>}
              <div className={styles.subjectList}>
                {(progress?.subject_stats || []).map((subject) => (
                  <div className={styles.subjectItem} key={subject.subject_id}>
                    <div>
                      <div className={styles.subjectName}>{subject.subject_name}</div>
                      <div className={styles.subjectMeta}>Попыток: {subject.tests_count}</div>
                    </div>
                    <Badge variant="info">{subject.avg_percent}%</Badge>
                  </div>
                ))}
              </div>
            </Card>
          </section>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
