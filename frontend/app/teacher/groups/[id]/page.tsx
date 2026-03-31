"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import { getTeacherGroupMembers } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { tr, useUiLanguage } from "@/lib/i18n";
import { TeacherGroupMembers } from "@/lib/types";
import styles from "@/app/teacher/groups/[id]/group-detail.module.css";

function buildStudentAnalyticsHref(studentId: number, studentName?: string) {
  const params = new URLSearchParams();
  const normalizedName = (studentName || "").trim();
  if (normalizedName) {
    params.set("name", normalizedName);
  }
  const query = params.toString();
  return query ? `/teacher/students/${studentId}?${query}` : `/teacher/students/${studentId}`;
}

export default function TeacherGroupDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const groupId = Number(params.id);
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [group, setGroup] = useState<TeacherGroupMembers | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    const token = getToken();
    if (!token || !Number.isFinite(groupId)) return;
    setLoading(true);
    try {
      const membersPayload = await getTeacherGroupMembers(token, groupId);
      setGroup(membersPayload);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось загрузить группу", "Топты жүктеу мүмкін болмады"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData().catch((err: unknown) => {
      setLoading(false);
      setError(err instanceof Error ? err.message : t("Не удалось загрузить группу", "Топты жүктеу мүмкін болмады"));
    });
  }, [groupId]);

  return (
    <AuthGuard roles={["teacher"]}>
      <AppShell>
        <div className={styles.page}>
          <header className={styles.header}>
            <div>
              <h2>{group?.name || t("Группа", "Топ")}</h2>
              <p>{t("Назначенная вам группа и аналитика учеников.", "Сізге тағайындалған топ және оқушылар аналитикасы.")}</p>
            </div>
            <Button onClick={() => router.push("/teacher/tests")} className={styles.actionButton}>
              <span>{t("Мои тесты", "Менің тесттерім")}</span>
            </Button>
          </header>
          {group && (
            <p className="muted">
              {t("Участников", "Қатысушы")}: {group.members.length}
            </p>
          )}

          {loading && <p className="muted">{t("Загрузка...", "Жүктелуде...")}</p>}
          {error && <div className="errorText">{error}</div>}

          {!loading && group && (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <colgroup>
                  <col className={styles.colName} />
                  <col className={styles.colScore} />
                  <col className={styles.colWarnings} />
                  <col className={styles.colTopic} />
                  <col className={styles.colActivity} />
                  <col className={styles.colActions} />
                </colgroup>
                <thead>
                  <tr>
                    <th>{t("Имя", "Аты")}</th>
                    <th>{t("Успеваемость", "Үлгерім")}</th>
                    <th>{t("Предупреждения", "Ескертулер")}</th>
                    <th>{t("Слабая тема", "Әлсіз тақырып")}</th>
                    <th>{t("Активность", "Белсенділік")}</th>
                    <th>{t("Детали", "Толығырақ")}</th>
                  </tr>
                </thead>
                <tbody>
                  {group.members.map((member, index) => (
                    <tr key={member.student_id} className={styles.memberRow}>
                      <td>
                        <div className={styles.memberCell}>
                          <span className={styles.rowIndex}>{index + 1}</span>
                          <span>{member.full_name || member.username}</span>
                        </div>
                      </td>
                      <td>{formatPercent(member.avg_percent)}</td>
                      <td>{member.warnings_count}</td>
                      <td>{member.weak_topic || "—"}</td>
                      <td>{formatActivity(member.last_activity_at, uiLanguage)}</td>
                      <td className={styles.rowActions}>
                        <button
                          type="button"
                          className={styles.openLink}
                          onClick={() => router.push(buildStudentAnalyticsHref(member.student_id, member.full_name || member.username))}
                        >
                          {t("Открыть", "Ашу")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!loading && group && group.members.length === 0 && (
            <p className="muted">{t("В этой группе пока нет учеников.", "Бұл топта әзірге оқушылар жоқ.")}</p>
          )}
        </div>
      </AppShell>
    </AuthGuard>
  );
}

function formatPercent(value: number): string {
  const rounded = Number(value.toFixed(1));
  return `${rounded}%`;
}

function formatActivity(value: string | null | undefined, language: "RU" | "KZ"): string {
  if (!value) {
    return tr(language, "Нет данных", "Дерек жоқ");
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return tr(language, "Нет данных", "Дерек жоқ");
  }
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const dayMs = 24 * 60 * 60 * 1000;
  const diffDays = Math.round((startOfToday - startOfDate) / dayMs);
  if (diffDays <= 0) return tr(language, "Сегодня", "Бүгін");
  if (diffDays === 1) return tr(language, "Вчера", "Кеше");
  return date.toLocaleDateString(language === "KZ" ? "kk-KZ" : "ru-RU", {
    day: "2-digit",
    month: "2-digit",
  });
}
