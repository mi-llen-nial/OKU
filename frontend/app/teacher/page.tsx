"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import { getTeacherGroupMembers, getTeacherGroups } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { tr, useUiLanguage } from "@/lib/i18n";
import { TeacherGroup } from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/app/teacher/teacher.module.css";

interface AttentionItem {
  student_id: number;
  student_name: string;
  group_name: string;
  warnings_count: number;
}

function buildStudentAnalyticsHref(studentId: number, studentName?: string) {
  const params = new URLSearchParams();
  const normalizedName = (studentName || "").trim();
  if (normalizedName) {
    params.set("name", normalizedName);
  }
  const query = params.toString();
  return query ? `/teacher/students/${studentId}?${query}` : `/teacher/students/${studentId}`;
}

export default function TeacherGroupsPage() {
  const router = useRouter();
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);
  const [groups, setGroups] = useState<TeacherGroup[]>([]);
  const [attention, setAttention] = useState<AttentionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [attentionLoading, setAttentionLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setAttentionLoading(true);
        setError("");
        setSuccess("");
        const groupsPayload = await getTeacherGroups(token);
        if (cancelled) return;
        setGroups(groupsPayload);
        setLoading(false);

        if (groupsPayload.length === 0) {
          setAttention([]);
          setAttentionLoading(false);
          return;
        }

        const membersPayload = await Promise.all(
          groupsPayload.map(async (group) => ({
            group,
            members: await getTeacherGroupMembers(token, group.id),
          })),
        );
        if (cancelled) return;

        const items: AttentionItem[] = [];
        for (const payload of membersPayload) {
          for (const member of payload.members.members) {
            if (member.warnings_count <= 0) continue;
            items.push({
              student_id: member.student_id,
              student_name: member.full_name || member.username,
              group_name: payload.group.name,
              warnings_count: member.warnings_count,
            });
          }
        }
        items.sort((left, right) => right.warnings_count - left.warnings_count);
        setAttention(items.slice(0, 3));
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("Не удалось загрузить группы", "Топтарды жүктеу мүмкін болмады"));
          setLoading(false);
        }
      } finally {
        if (!cancelled) {
          setAttentionLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [uiLanguage]);

  return (
    <AuthGuard roles={["teacher"]}>
      <AppShell>
        <div className={styles.page}>
          <section className={styles.section}>
            <header className={styles.sectionHeader}>
              <div>
                <h2 className={styles.title}>{t("Группы", "Топтар")}</h2>
                <p className={styles.subtitle}>{t("Группы с вашими учениками", "Оқушыларыңыз бар топтар")}</p>
              </div>
              <Button onClick={() => router.push("/teacher/tests")} className={styles.actionButton}>
                <img className={styles.actionIcon} src={assetPaths.icons.lesson} alt="" aria-hidden="true" />
                <span>{t("Мои тесты", "Менің тесттерім")}</span>
              </Button>
            </header>

            {success && <p className={styles.success}>{success}</p>}

            {loading ? (
              <p className="muted">{t("Загрузка...", "Жүктелуде...")}</p>
            ) : (
              <div className={styles.groupsGrid}>
                {groups.map((group) => (
                  <button key={group.id} type="button" className={styles.groupCard} onClick={() => router.push(`/teacher/groups/${group.id}`)}>
                    <img className={styles.groupIcon} src={assetPaths.icons.group} alt={t("Группа", "Топ")} />
                    <div className={styles.groupBody}>
                      <h3>{group.name}</h3>
                      <p>{group.members_count} {t("человек", "адам")}</p>
                    </div>
                  </button>
                ))}
              </div>
            )}

            {!loading && groups.length === 0 && (
              <div className={styles.emptyState}>
                <p>{t("У вас пока нет назначенных групп.", "Сізге әлі топтар тағайындалмаған.")}</p>
              </div>
            )}
          </section>

          <section className={styles.section}>
            <header className={styles.sectionHeader}>
              <div>
                <h2 className={styles.title}>{t("Требует внимания", "Назар аударуды қажет етеді")}</h2>
                <p className={styles.subtitle}>
                  {t("Основаны на тестах и результатах учеников", "Оқушылардың тесттері мен нәтижелері негізінде")}
                </p>
              </div>
            </header>

            {error && <div className="errorText">{error}</div>}

            {!attentionLoading && (
              <div className={styles.attentionGrid}>
                {attention.map((item) => (
                  <article className={styles.attentionCard} key={item.student_id}>
                    <p className={styles.warning}>+{item.warnings_count} {t("предупреждений", "ескерту")}</p>
                    <div className={styles.studentRow}>
                      <img className={styles.studentIcon} src={assetPaths.icons.student} alt={t("Ученик", "Оқушы")} />
                      <div>
                        <h3>{item.student_name}</h3>
                        <p>{item.group_name}</p>
                      </div>
                    </div>
                    <Button block onClick={() => router.push(buildStudentAnalyticsHref(item.student_id, item.student_name))}>
                      {t("Открыть", "Ашу")}
                    </Button>
                  </article>
                ))}
              </div>
            )}

            {attention.length === 0 && !loading && !attentionLoading && (
              <p className="muted">{t("Пока нет учеников с предупреждениями.", "Ескертулері бар оқушылар әзірге жоқ.")}</p>
            )}
            {attentionLoading && (
              <p className="muted">{t("Загрузка...", "Жүктелуде...")}</p>
            )}
          </section>

          <footer className={styles.footer}>oku.com.kz</footer>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
