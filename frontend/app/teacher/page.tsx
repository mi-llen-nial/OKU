"use client";

import { Gauge, GraduationCap, Users } from "lucide-react";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import SimpleBarChart from "@/components/SimpleBarChart";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import StatWidget from "@/components/ui/StatWidget";
import { getGroupAnalytics, getGroupWeakTopics, getStudentProgressByTeacher } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { GroupAnalytics, GroupWeakTopics, StudentProgress } from "@/lib/types";
import styles from "@/app/teacher/teacher.module.css";

export default function TeacherPage() {
  const [groupId, setGroupId] = useState(1);
  const [analytics, setAnalytics] = useState<GroupAnalytics | null>(null);
  const [weakTopics, setWeakTopics] = useState<GroupWeakTopics | null>(null);
  const [studentId, setStudentId] = useState<number | null>(null);
  const [studentProgress, setStudentProgress] = useState<StudentProgress | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const loadGroup = async () => {
    const token = getToken();
    if (!token) return;

    try {
      setLoading(true);
      setError("");
      const [analyticsData, weakData] = await Promise.all([
        getGroupAnalytics(token, groupId),
        getGroupWeakTopics(token, groupId),
      ]);
      setAnalytics(analyticsData);
      setWeakTopics(weakData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot load group analytics");
    } finally {
      setLoading(false);
    }
  };

  const loadStudentProgress = async (targetStudentId: number) => {
    const token = getToken();
    if (!token) return;

    try {
      const payload = await getStudentProgressByTeacher(token, targetStudentId);
      setStudentId(targetStudentId);
      setStudentProgress(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot load student progress");
    }
  };

  useEffect(() => {
    loadGroup().catch(() => undefined);
  }, []);

  return (
    <AuthGuard roles={["teacher"]}>
      <AppShell>
        <div className={styles.page}>
          <section className="grid3">
            <StatWidget label="Группа" value={analytics?.group_name || `#${groupId}`} icon={<Users size={16} />} />
            <StatWidget label="Средний балл" value={`${analytics?.group_avg_percent ?? 0}%`} icon={<Gauge size={16} />} />
            <StatWidget label="Студентов" value={`${analytics?.students.length ?? 0}`} icon={<GraduationCap size={16} />} />
          </section>

          <Card title="Управление группой">
            <div className={styles.controls}>
              <label>
                ID группы
                <input
                  onChange={(e) => setGroupId(Number(e.target.value))}
                  style={{ maxWidth: 120 }}
                  type="number"
                  value={groupId}
                />
              </label>
              <Button onClick={() => loadGroup()}>{loading ? "Обновляем..." : "Обновить аналитику"}</Button>
            </div>
            {error && <div className="errorText" style={{ marginTop: 10 }}>{error}</div>}
          </Card>

          <div className={styles.layout}>
            <Card title="Динамика группы">
              <SimpleBarChart points={(analytics?.trend || []).map((point) => ({ label: point.date.slice(5), value: point.avg_percent }))} />
            </Card>

            <Card title="Слабые темы группы">
              <div className={styles.topicCloud}>
                {(weakTopics?.weak_topics || []).map((item) => (
                  <Badge key={item.topic}>{item.topic} ({item.count})</Badge>
                ))}
              </div>
            </Card>
          </div>

          <div className={styles.layout}>
            <Card title="Список студентов" subtitle="Выберите студента для индивидуального прогресса.">
              <div className="tableWrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Имя</th>
                      <th>Тестов</th>
                      <th>Avg</th>
                      <th>Last</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {(analytics?.students || []).map((student) => (
                      <tr key={student.student_id}>
                        <td>{student.student_id}</td>
                        <td>{student.student_name}</td>
                        <td>{student.tests_count}</td>
                        <td>{student.avg_percent}%</td>
                        <td>{student.last_percent ?? "-"}</td>
                        <td>
                          <Button variant="ghost" onClick={() => loadStudentProgress(student.student_id)}>Прогресс</Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title={`Прогресс студента ${studentId ? `#${studentId}` : ""}`}>
              <div className={styles.studentPanel}>
                {studentProgress ? (
                  <>
                    <div className="inline">
                      <Badge variant="info">Avg {studentProgress.avg_percent}%</Badge>
                      <Badge>Best {studentProgress.best_percent}%</Badge>
                    </div>
                    <SimpleBarChart
                      points={studentProgress.trend.map((point) => ({ label: point.date.slice(5), value: point.percent }))}
                    />
                  </>
                ) : (
                  <p className="muted">Выберите студента из таблицы слева.</p>
                )}
              </div>
            </Card>
          </div>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
