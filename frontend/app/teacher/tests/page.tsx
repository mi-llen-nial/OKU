"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import {
  assignTeacherCustomTestToGroups,
  getTeacherCustomTest,
  getTeacherCustomTests,
  submitTeacherCustomTestForReview,
} from "@/lib/api";
import { getToken, getUser } from "@/lib/auth";
import { tr, uiLocale, useUiLanguage } from "@/lib/i18n";
import { toast } from "@/lib/toast";
import { TeacherCustomQuestion, TeacherCustomTest, TeacherCustomTestDetails, TestModerationStatus } from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/app/teacher/tests/tests.module.css";

function dayLabel(input: string, language: "RU" | "KZ"): string {
  const date = new Date(input);
  const today = new Date();
  const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const startInput = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round((startToday.getTime() - startInput.getTime()) / 86_400_000);
  if (diffDays === 0) return language === "KZ" ? "Бүгін" : "Сегодня";
  if (diffDays === 1) return language === "KZ" ? "Кеше" : "Вчера";
  return date.toLocaleDateString(uiLocale(language), {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}

function resolveDueDate(input?: string | null, language: "RU" | "KZ" = "RU"): {
  label: string;
  isExpired: boolean;
} {
  if (!input) {
    return { label: "–", isExpired: false };
  }

  const parsed = input.trim();
  let date = new Date(parsed);

  if (Number.isNaN(date.getTime())) {
    const dotMatch = parsed.match(/^(\d{2})\.(\d{2})\.(\d{2,4})$/);
    if (dotMatch) {
      const yearRaw = Number(dotMatch[3]);
      const year = yearRaw < 100 ? 2000 + yearRaw : yearRaw;
      date = new Date(year, Number(dotMatch[2]) - 1, Number(dotMatch[1]));
    }
  }

  if (Number.isNaN(date.getTime())) {
    return { label: "–", isExpired: false };
  }

  const now = new Date();
  const dueStart = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());

  return {
    label: date.toLocaleDateString(uiLocale(language), {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
    }),
    isExpired: dueStart < todayStart,
  };
}

function pluralRu(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function groupsLabel(count: number, language: "RU" | "KZ"): string {
  if (language === "KZ") return `${count} топ`;
  return `${count} ${pluralRu(count, "группа", "группы", "групп")}`;
}

function warningsLabel(count: number, language: "RU" | "KZ"): string {
  if (language === "KZ") return `${count} ескерту`;
  return `${count} ${pluralRu(count, "предупреждение", "предупреждения", "предупреждений")}`;
}

function pickTestIcon(title: string): string {
  const normalized = title.toLowerCase();

  if (/(ооп|код|программ|информ|алгоритм|java|python|frontend|backend|api|devops|it|ai|нейро)/.test(normalized)) {
    return assetPaths.icons.informatics;
  }
  if (/(матем|алгебр|геометр|тригоном|уравн|дискриминант|арифмет)/.test(normalized)) {
    return assetPaths.icons.math;
  }
  if (/(англ|ielts|listening|speaking|reading|writing|english)/.test(normalized)) {
    return assetPaths.icons.english;
  }
  if (/(русс|литер|пушкин|айтмат|тіл|язык|граммат|сочинен)/.test(normalized)) {
    return assetPaths.icons.russian;
  }
  if (/(истор|казахстан|дүние|world)/.test(normalized)) {
    return assetPaths.icons.history;
  }
  if (/(биолог|генет|клетк|анатом)/.test(normalized)) {
    return assetPaths.icons.biology;
  }
  if (/(хим|реакц|молекул|органик)/.test(normalized)) {
    return assetPaths.icons.chemistry;
  }
  if (/(физ|механик|электр|оптик|динам)/.test(normalized)) {
    return assetPaths.icons.physics;
  }
  if (/(ент|экзамен|exam|контрольн)/.test(normalized)) {
    return assetPaths.icons.ent;
  }

  return assetPaths.icons.lesson;
}

function toDraftStorageKey(userId: number): string {
  return `oku_teacher_custom_test_draft:${userId}`;
}

function mapDetailsToDraft(details: TeacherCustomTestDetails) {
  return {
    title: details.title,
    duration_minutes: details.duration_minutes,
    warning_limit: details.warning_limit,
    due_date: details.due_date ?? "",
    questions: details.questions.map((question: TeacherCustomQuestion) => ({
      id: `edit-q-${question.id}`,
      prompt: question.prompt ?? "",
      answer_type: question.answer_type,
      options:
        question.answer_type === "choice"
          ? (question.options?.length ? question.options : ["", "", "", ""])
          : ["", "", "", ""],
      correct_option_index:
        question.answer_type === "choice" ? (question.correct_option_index ?? 0) : null,
      sample_answer: question.sample_answer ?? "",
      image_data_url: question.image_data_url ?? null,
    })),
  };
}

export default function TeacherCustomTestsPage() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);
  const router = useRouter();

  const [tests, setTests] = useState<TeacherCustomTest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loadingEditId, setLoadingEditId] = useState<number | null>(null);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);

  const loadTests = async () => {
    const token = getToken();
    if (!token) return;
    try {
      setLoading(true);
      setError("");
      const payload = await getTeacherCustomTests(token);
      setTests(payload);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : t("Не удалось загрузить тесты.", "Тесттерді жүктеу мүмкін болмады."),
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!cancelled) {
        await loadTests();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const sortedTests = useMemo(
    () => [...tests].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()),
    [tests],
  );

  const openResults = (testId: number) => {
    router.push(`/teacher/tests/${testId}`);
  };

  const openEdit = async (testId: number) => {
    const token = getToken();
    const user = getUser();
    if (!token || !user) return;
    try {
      setLoadingEditId(testId);
      const details = await getTeacherCustomTest(token, testId);
      localStorage.setItem(toDraftStorageKey(user.id), JSON.stringify(mapDetailsToDraft(details)));
      router.push(`/teacher/create-test?edit=${testId}`);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : t("Не удалось открыть тест для редактирования.", "Тестті өңдеуге ашу мүмкін болмады."),
      );
    } finally {
      setLoadingEditId(null);
    }
  };

  const moderationLabel = (status: TestModerationStatus): string => {
    if (status === "submitted_for_review") return t("Отправлен на модерацию", "Модерацияға жіберілді");
    if (status === "in_review") return t("На проверке методиста", "Әдіскер тексеруде");
    if (status === "needs_revision") return t("Нужны доработки", "Түзету қажет");
    if (status === "approved") return t("Одобрен", "Мақұлданды");
    if (status === "rejected") return t("Отклонён", "Қабылданбады");
    if (status === "archived") return t("Архив", "Мұрағат");
    return t("Черновик", "Қаралама");
  };

  const submitForReview = async (test: TeacherCustomTest) => {
    const token = getToken();
    if (!token) return;
    try {
      setActionLoadingId(test.id);
      await submitTeacherCustomTestForReview(token, test.id);
      toast.success(t("Тест отправлен на модерацию.", "Тест модерацияға жіберілді."));
      await loadTests();
    } catch (requestError) {
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : t("Не удалось отправить тест на модерацию.", "Тестті модерацияға жіберу мүмкін болмады."),
      );
    } finally {
      setActionLoadingId(null);
    }
  };

  const assignApprovedTest = async (test: TeacherCustomTest) => {
    const token = getToken();
    if (!token) return;
    const groupIds = test.groups.map((item) => Number(item.id)).filter((value) => Number.isFinite(value) && value > 0);
    if (groupIds.length === 0) {
      toast.error(
        t(
          "Укажите группы в тесте перед назначением.",
          "Тағайындаудан бұрын тестте топтарды көрсетіңіз.",
        ),
      );
      return;
    }
    try {
      setActionLoadingId(test.id);
      await assignTeacherCustomTestToGroups(token, test.id, groupIds);
      toast.success(t("Тест назначен выбранным группам.", "Тест таңдалған топтарға тағайындалды."));
      await loadTests();
    } catch (requestError) {
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : t("Не удалось назначить тест группам.", "Тестті топтарға тағайындау мүмкін болмады."),
      );
    } finally {
      setActionLoadingId(null);
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
                "Список тестов и групп, в которые они назначены",
                "Тесттер және олар тағайындалған топтар тізімі",
              )}
            </p>
          </header>

          {error && <p className={styles.error}>{error}</p>}

          {loading ? (
            <p className={styles.empty}>{t("Загрузка...", "Жүктелуде...")}</p>
          ) : sortedTests.length === 0 ? (
            <p className={styles.empty}>{t("Пока нет созданных тестов.", "Әзірге құрылған тесттер жоқ.")}</p>
          ) : (
            <section className={styles.cards}>
              {sortedTests.map((test) => {
                const groupsCount = test.groups.length;
                const dueMeta = resolveDueDate(test.due_date, uiLanguage);
                const moderationStatus = (test.moderation_status || "draft") as TestModerationStatus;
                const canSubmitForReview =
                  moderationStatus === "draft" ||
                  moderationStatus === "needs_revision" ||
                  moderationStatus === "rejected";
                const canAssignApproved = moderationStatus === "approved";
                return (
                  <article className={styles.card} key={test.id}>
                    <div className={styles.cardTop}>
                      <span className={styles.cardDayLabel}>{dayLabel(test.created_at, uiLanguage)}</span>
                      <span
                        className={`${styles.cardDeadline} ${dueMeta.isExpired ? styles.cardDeadlineExpired : ""}`}
                      >
                        <img src={assetPaths.icons.schedule} alt="" aria-hidden />
                        {dueMeta.label}
                      </span>
                    </div>

                    <div className={styles.cardBody}>
                      <img className={styles.cardSubjectIcon} src={pickTestIcon(test.title)} alt="" aria-hidden />
                      <div className={styles.cardBodyText}>
                        <h3 className={styles.cardTitle} title={test.title}>
                          {test.title}
                        </h3>
                        <div className={styles.cardMetrics}>
                          <span>
                            <img src={assetPaths.icons.questionAnswer} alt="" aria-hidden />
                            {test.questions_count} {t("вопросов", "сұрақ")}
                          </span>
                          <span>
                            <img src={assetPaths.icons.warningDiamond} alt="" aria-hidden />
                            {warningsLabel(test.warning_limit, uiLanguage)}
                          </span>
                          <span>
                            <img src={assetPaths.icons.group} alt="" aria-hidden />
                            {groupsLabel(groupsCount, uiLanguage)}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className={styles.statusRow}>
                      <span className={`${styles.statusBadge} ${styles[`status_${moderationStatus}`] || ""}`}>
                        {moderationLabel(moderationStatus)}
                      </span>
                      {test.moderation_comment ? (
                        <span className={styles.statusComment} title={test.moderation_comment}>
                          {test.moderation_comment}
                        </span>
                      ) : null}
                    </div>

                    <div className={styles.cardActions}>
                      <button
                        type="button"
                        className={styles.resultsButton}
                        onClick={() => openResults(test.id)}
                      >
                        {t("Результаты", "Нәтижелер")}
                      </button>
                      <button
                        type="button"
                        className={styles.editButton}
                        onClick={() => void openEdit(test.id)}
                        disabled={loadingEditId === test.id}
                      >
                        {loadingEditId === test.id
                          ? t("Открываем...", "Ашылуда...")
                          : t("Редактировать", "Өңдеу")}
                      </button>
                    </div>
                    <div className={styles.workflowActions}>
                      {canSubmitForReview ? (
                        <button
                          type="button"
                          className={styles.workflowButton}
                          disabled={actionLoadingId === test.id}
                          onClick={() => void submitForReview(test)}
                        >
                          {actionLoadingId === test.id
                            ? t("Отправляем...", "Жіберілуде...")
                            : t("Отправить на модерацию", "Модерацияға жіберу")}
                        </button>
                      ) : null}
                      {canAssignApproved ? (
                        <button
                          type="button"
                          className={styles.workflowButtonSecondary}
                          disabled={actionLoadingId === test.id}
                          onClick={() => void assignApprovedTest(test)}
                        >
                          {actionLoadingId === test.id
                            ? t("Назначаем...", "Тағайындалуда...")
                            : t("Назначить группам", "Топтарға тағайындау")}
                        </button>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </section>
          )}

          <footer className={styles.footer}>oku.com.kz</footer>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
