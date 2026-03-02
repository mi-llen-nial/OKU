"use client";

import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import { deleteTeacherCustomTest, getTeacherCustomTest, getTeacherCustomTests } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { tr, uiLocale, useUiLanguage } from "@/lib/i18n";
import { TeacherCustomTest, TeacherCustomTestDetails } from "@/lib/types";
import styles from "@/app/teacher/tests/tests.module.css";

export default function TeacherCustomTestsPage() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [tests, setTests] = useState<TeacherCustomTest[]>([]);
  const [detailsById, setDetailsById] = useState<Record<number, TeacherCustomTestDetails>>({});
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    let isCancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError("");
        const payload = await getTeacherCustomTests(token);
        if (!isCancelled) {
          setTests(payload);
        }
      } catch (requestError) {
        if (!isCancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : t("Не удалось загрузить тесты.", "Тесттерді жүктеу мүмкін болмады."),
          );
        }
      } finally {
        if (!isCancelled) {
          setLoading(false);
        }
      }
    })();

    return () => {
      isCancelled = true;
    };
  }, [uiLanguage]);

  const togglePreview = async (customTestId: number) => {
    if (expandedId === customTestId) {
      setExpandedId(null);
      return;
    }

    setExpandedId(customTestId);
    if (detailsById[customTestId]) return;

    const token = getToken();
    if (!token) return;

    try {
      const payload = await getTeacherCustomTest(token, customTestId);
      setDetailsById((prev) => ({ ...prev, [customTestId]: payload }));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : t("Не удалось загрузить детали теста.", "Тест мәліметтерін жүктеу мүмкін болмады."),
      );
    }
  };

  const removeTest = async (customTest: TeacherCustomTest) => {
    const token = getToken();
    if (!token) return;
    const confirmed = window.confirm(
      t(
        `Удалить тест «${customTest.title}»?`,
        `«${customTest.title}» тестін жою керек пе?`,
      ),
    );
    if (!confirmed) return;

    try {
      setDeletingId(customTest.id);
      await deleteTeacherCustomTest(token, customTest.id);
      setTests((prev) => prev.filter((item) => item.id !== customTest.id));
      setExpandedId((prev) => (prev === customTest.id ? null : prev));
      setSuccess(t("Тест удален.", "Тест жойылды."));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : t("Не удалось удалить тест.", "Тестті жою мүмкін болмады."),
      );
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <AuthGuard roles={["teacher"]}>
      <AppShell>
        <div className={styles.page}>
          <header className={styles.header}>
            <h2 className={styles.title}>{t("Мои тесты", "Менің тесттерім")}</h2>
            <p className={styles.subtitle}>
              {t(
                "Список авторских тестов и групп, в которые они назначены.",
                "Авторлық тесттер тізімі және олар тағайындалған топтар.",
              )}
            </p>
          </header>

          {error && <p className={styles.error}>{error}</p>}
          {success && <p className={styles.success}>{success}</p>}

          {loading ? (
            <p className={styles.empty}>{t("Загрузка...", "Жүктелуде...")}</p>
          ) : tests.length === 0 ? (
            <p className={styles.empty}>{t("Вы пока не создали тесты.", "Сіз әлі тест құрмадыңыз.")}</p>
          ) : (
            <section className={styles.list}>
              {tests.map((item) => {
                const details = detailsById[item.id];
                const isExpanded = expandedId === item.id;
                return (
                  <article className={styles.item} key={item.id}>
                    <h3>{item.title}</h3>
                    <p className={styles.meta}>
                      {item.questions_count} {t("вопросов", "сұрақ")} · {item.duration_minutes} {t("мин", "мин")} ·{" "}
                      {t("предупреждений", "ескерту")}: {item.warning_limit}
                    </p>
                    <div className={styles.groups}>
                      {item.groups.map((group) => (
                        <span key={group.id} className={styles.groupTag}>
                          {group.name}
                        </span>
                      ))}
                    </div>
                    <p className={styles.meta}>
                      {t("Обновлено", "Жаңартылған")}:{" "}
                      {new Date(item.updated_at).toLocaleString(uiLocale(uiLanguage), {
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                    <div className={styles.actions}>
                      <Button variant="ghost" onClick={() => void togglePreview(item.id)}>
                        {isExpanded ? t("Скрыть вопросы", "Сұрақтарды жасыру") : t("Показать вопросы", "Сұрақтарды көрсету")}
                      </Button>
                      <Button variant="danger" onClick={() => void removeTest(item)} disabled={deletingId === item.id}>
                        {deletingId === item.id ? t("Удаляем...", "Жойылуда...") : t("Удалить", "Жою")}
                      </Button>
                    </div>
                    {isExpanded && details && (
                      <div className={styles.preview}>
                        {details.questions.map((question) => (
                          <p key={question.id} className={styles.previewItem}>
                            {question.order_index}. {question.prompt}
                          </p>
                        ))}
                      </div>
                    )}
                  </article>
                );
              })}
            </section>
          )}

          <footer className={styles.footer}>OKU.com.kz</footer>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
