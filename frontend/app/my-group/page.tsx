"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import { generateGroupAssignedTest, getStudentGroupTests } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { GroupAssignedTest } from "@/lib/types";
import { tr, useUiLanguage } from "@/lib/i18n";
import { assetPaths } from "@/src/assets";
import styles from "@/app/my-group/my-group.module.css";

export default function MyGroupPage() {
  const router = useRouter();
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [tests, setTests] = useState<GroupAssignedTest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [startingTestId, setStartingTestId] = useState<number | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    let isCancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError("");
        const payload = await getStudentGroupTests(token);
        if (!isCancelled) {
          setTests(payload);
        }
      } catch (requestError) {
        if (!isCancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : t("Не удалось загрузить тесты группы.", "Топ тесттерін жүктеу мүмкін болмады."),
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

  const groupName = useMemo(() => {
    if (tests.length === 0) return t("Моя группа", "Менің тобым");
    return tests[0].group_name;
  }, [tests, t]);

  const startGroupTest = async (customTestId: number) => {
    const token = getToken();
    if (!token) return;
    try {
      setStartingTestId(customTestId);
      const generated = await generateGroupAssignedTest(token, customTestId);
      router.push(`/test/${generated.id}`);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : t("Не удалось запустить тест.", "Тестті бастау мүмкін болмады."),
      );
    } finally {
      setStartingTestId(null);
    }
  };

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <div className={styles.page}>
          <section className={styles.section}>
            <header className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>{t("Тесты группы", "Топ тесттері")}</h2>
              <p className={styles.sectionSubtitle}>
                {t("Группа", "Топ")}: {groupName}
              </p>
            </header>

            {error && <div className="errorText">{error}</div>}
            {loading ? (
              <p className={styles.empty}>{t("Загрузка...", "Жүктелуде...")}</p>
            ) : tests.length === 0 ? (
              <p className={styles.empty}>
                {t("В вашей группе пока нет назначенных тестов.", "Сіздің тобыңызда әзірге тағайындалған тесттер жоқ.")}
              </p>
            ) : (
              <div className={styles.cards}>
                {tests.map((test) => (
                  <button
                    key={test.custom_test_id}
                    type="button"
                    className={styles.card}
                    onClick={() => void startGroupTest(test.custom_test_id)}
                    disabled={startingTestId === test.custom_test_id}
                  >
                    <img className={styles.icon} src={assetPaths.icons.group} alt="" aria-hidden="true" />
                    <div className={styles.body}>
                      <h3 className={styles.title}>{test.title}</h3>
                      <p className={styles.description}>
                        {t("Вопросов", "Сұрақтар")}: {test.questions_count}
                      </p>
                      <p className={styles.meta}>
                        {t("Лимит", "Лимит")}: {test.duration_minutes} {t("мин", "мин")} ·{" "}
                        {t("Предупреждений", "Ескертулер")}: {test.warning_limit}
                      </p>
                      <p className={styles.meta}>
                        {t("Учитель", "Мұғалім")}: {test.teacher_name}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>

          <footer className={styles.footer}>OKU.com.kz</footer>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
