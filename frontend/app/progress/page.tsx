"use client";

import { Flame, LineChart, Shield } from "lucide-react";
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
  const [error, setError] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    getProgress(token)
      .then((payload) => setProgress(payload))
      .catch((err) => setError(err instanceof Error ? err.message : "Cannot load progress"));
  }, []);

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <section className="grid3">
          <StatWidget label="Стабильность" value={`${progress?.avg_percent ?? 0}%`} icon={<Shield size={16} />} />
          <StatWidget label="Пик" value={`${progress?.best_percent ?? 0}%`} icon={<Flame size={16} />} />
          <StatWidget label="Всего попыток" value={`${progress?.total_tests ?? 0}`} icon={<LineChart size={16} />} />
        </section>

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

        <Card title="Результаты по предметам" subtitle="Средняя успеваемость и количество попыток.">
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
      </AppShell>
    </AuthGuard>
  );
}
