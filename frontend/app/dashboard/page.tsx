"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import { generateMistakesTest, getDashboard } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { tr, uiLocale, useUiLanguage } from "@/lib/i18n";
import { HistoryItem, StudentProgress } from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/app/dashboard/dashboard.module.css";

interface RecommendationCard {
  id: string;
  label: string;
  title: string;
  text: string;
  action: string;
  icon: string;
  kind: "link" | "mistakes";
  href?: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [progress, setProgress] = useState<StudentProgress | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [launchingMistakes, setLaunchingMistakes] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    getDashboard(token)
      .then((dashboardData) => {
        setProgress(dashboardData.progress);
        setHistory(dashboardData.history);
      })
      .catch((err) => setError(err instanceof Error ? err.message : t("Не удалось загрузить данные главной страницы", "Басты бет деректерін жүктеу мүмкін болмады")))
      .finally(() => setLoading(false));
  }, []);

  const recentAttempts = useMemo(() => history.slice(0, 3), [history]);
  const bestAttempt = useMemo(
    () => history.slice().sort((left, right) => right.percent - left.percent)[0] || null,
    [history],
  );

  const recommendations = useMemo<RecommendationCard[]>(() => {
    const weakTopic = progress?.weak_topics[0] || t("Слабая тема", "Әлсіз тақырып");
    const hasAttempts = history.length > 0;

    return [
      {
        id: "review-errors",
        label: t("Приоритет для вас", "Сіз үшін басымдық"),
        title: t("Работа над ошибками", "Қателермен жұмыс"),
        text: t("Короткая практика по вопросам, где вы ошибались в последних попытках.", "Соңғы әрекеттердегі қателескен сұрақтар бойынша қысқа жаттығу."),
        action: t("Начать", "Бастау"),
        icon: assetPaths.icons.repeat,
        kind: "mistakes",
      },
      {
        id: "weak-topic",
        label: t("Самая слабая тема", "Ең әлсіз тақырып"),
        title: weakTopic,
        text: t("Сконцентрируйтесь на самой слабой теме, чтобы поднять общий балл.", "Жалпы нәтижені көтеру үшін ең әлсіз тақырыпқа назар аударыңыз."),
        action: t("Начать", "Бастау"),
        icon: assetPaths.icons.weakTopic,
        kind: "link",
        href: "/test",
      },
      {
        id: "control",
        label: t("Для вас", "Сіз үшін"),
        title: hasAttempts ? t("Контрольный тест", "Бақылау тесті") : t("Первый тест", "Бірінші тест"),
        text: hasAttempts
          ? t("Проверьте прогресс после повторения и сравните результат с предыдущими тестами.", "Қайталаудан кейін прогресті тексеріп, нәтижені алдыңғы тесттермен салыстырыңыз.")
          : t("Сделайте первую попытку, чтобы система собрала базовый профиль знаний.", "Жүйе бастапқы білім профилін құруы үшін алғашқы тестті өтіңіз."),
        action: t("Начать", "Бастау"),
        icon: assetPaths.icons.lesson,
        kind: "link",
        href: "/test",
      },
    ];
  }, [history.length, progress?.weak_topics, t]);

  const openMistakesReview = async () => {
    const token = getToken();
    if (!token) return;

    try {
      setLaunchingMistakes(true);
      setError("");
      const test = await generateMistakesTest(token, { num_questions: 10 });
      router.push(`/test/${test.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось подготовить повторение ошибок", "Қателерді қайталау тестін дайындау мүмкін болмады"));
    } finally {
      setLaunchingMistakes(false);
    }
  };

  if (loading) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <div className={styles.pageLoading}>{t("Загрузка...", "Жүктелуде...")}</div>
        </AppShell>
      </AuthGuard>
    );
  }

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <div className={styles.page}>
          <section className={`${styles.section} ${styles.primarySection}`}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>{t("Главная", "Басты бет")}</h2>
              <p className={styles.sectionSubtitle}>{t("Краткий пересказ вашего текущего прогресса", "Ағымдағы прогрестің қысқаша көрінісі")}</p>
            </div>

            <div className={styles.statsRow}>
              <article className={styles.statItem}>
                <h3 className={styles.statLabel}>{t("Средняя успеваемость", "Орташа үлгерім")}</h3>
                <p className={styles.statMeta}>{t("По всем попыткам", "Барлық талпыныс бойынша")}</p>
                <p className={styles.statValue}>{progress?.avg_percent ?? 0}%</p>
              </article>

              <article className={styles.statItem}>
                <h3 className={styles.statLabel}>{t("Лучший результат", "Ең үздік нәтиже")}</h3>
                <p className={styles.statMeta}>
                  {bestAttempt ? `${attemptTitle(bestAttempt, uiLanguage)} (${difficultyLabel(bestAttempt.difficulty, uiLanguage)})` : t("Пока нет данных", "Әзірге дерек жоқ")}
                </p>
                <p className={styles.statValue}>{progress?.best_percent ?? 0}%</p>
              </article>

              <article className={styles.statItem}>
                <h3 className={styles.statLabel}>{t("Всего тестов", "Барлық тест саны")}</h3>
                <p className={styles.statMeta}>{t("За все время", "Барлық уақыт ішінде")}</p>
                <p className={styles.statValue}>{progress?.total_tests ?? 0}</p>
              </article>
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>{t("Недавно вы проходили...", "Жақында өткендеріңіз...")}</h2>
              <p className={styles.sectionSubtitle}>{t("Последние попытки и текущий уровень результатов", "Соңғы талпыныстар және ағымдағы нәтиже деңгейі")}</p>
            </div>

            {error && <div className="errorText">{error}</div>}

            {recentAttempts.length === 0 ? (
              <div className={styles.emptyState}>
                <p className={styles.emptyText}>{t("У вас пока нет завершенных тестов.", "Сізде әлі аяқталған тесттер жоқ.")}</p>
                <Button onClick={() => router.push("/test")}>{t("Пройти первый тест", "Бірінші тестті өту")}</Button>
              </div>
            ) : (
              <>
                <div className={styles.cardGrid}>
                  {recentAttempts.map((item) => {
                    const scoreClass = resolveScoreClass(item.percent);
                    const title = attemptTitle(item, uiLanguage);

                    return (
                      <article className={styles.recentCard} key={item.test_id}>
                        <p className={styles.cardDate}>{formatRelativeDate(item.created_at, uiLanguage)}</p>

                        <div className={styles.cardTop}>
                          <img
                            className={styles.cardIcon}
                            src={resolveSubjectIcon(title)}
                            alt={title}
                          />
                          <div className={styles.cardInfo}>
                            <h3 className={styles.cardTitle}>{title}</h3>
                            <p className={styles.cardMeta}>
                              {difficultyLabel(item.difficulty, uiLanguage)}&nbsp;&nbsp;
                              {languageLabel(item.language, uiLanguage)}&nbsp;&nbsp;
                              #{item.test_id}
                            </p>
                          </div>
                          <p className={`${styles.scoreValue} ${styles[scoreClass]}`}>{item.percent}%</p>
                        </div>

                        <div className={styles.cardActions}>
                          <Button onClick={() => router.push("/test")}>{t("Повторить", "Қайталау")}</Button>
                          <button
                            type="button"
                            className={styles.linkButton}
                            onClick={() => router.push(`/results/${item.test_id}`)}
                          >
                            {t("Результаты", "Нәтижелер")}
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>

                <button type="button" className={styles.showAllButton} onClick={() => router.push("/history")}>
                  {t("Показать все", "Барлығын көрсету")}
                </button>
              </>
            )}
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>{t("Рекомендуем", "Ұсынамыз")}</h2>
              <p className={styles.sectionSubtitle}>{t("Основаны на ваших тестах и результатах", "Сіздің тесттеріңіз бен нәтижелеріңіз негізінде")}</p>
            </div>

            <div className={styles.cardGrid}>
              {recommendations.map((item) => (
                <article className={styles.recommendCard} key={item.id}>
                  <p className={styles.cardDate}>{item.label}</p>
                  <div className={styles.cardTop}>
                    <img className={styles.cardIcon} src={item.icon} alt={item.title} />
                    <div className={styles.cardInfo}>
                      <h3 className={styles.cardTitle}>{item.title}</h3>
                      <p className={styles.cardMeta}>{item.text}</p>
                    </div>
                  </div>
                  {item.kind === "mistakes" ? (
                    <Button disabled={launchingMistakes} block onClick={openMistakesReview}>
                      {launchingMistakes ? t("Подготавливаем...", "Дайындалып жатыр...") : item.action}
                    </Button>
                  ) : (
                    <Button block onClick={() => router.push(item.href || "/test")}>
                      {item.action}
                    </Button>
                  )}
                </article>
              ))}
            </div>
          </section>

          <footer className={styles.footer}>oku.com.kz</footer>
        </div>
      </AppShell>
    </AuthGuard>
  );
}

function normalizeText(value: string): string {
  return value
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[^a-zа-я0-9әіңғүұқөһ]/gi, "");
}

function resolveSubjectIcon(subjectName: string): string {
  const key = normalizeText(subjectName);
  if (key.includes("ielts")) return assetPaths.icons.ielts;
  if (key.includes("ент") || key.includes("ұбт") || key.includes("ent") || key.includes("ubt")) return assetPaths.icons.ent;
  if (key.includes("алгебр")) return assetPaths.icons.algebra;
  if (key.includes("геометр")) return assetPaths.icons.geometry;
  if (key.includes("физик")) return assetPaths.icons.physics;
  if (key.includes("русск") || key.includes("орыс")) return assetPaths.icons.russian;
  if (key.includes("англ") || key.includes("агылшын")) return assetPaths.icons.english;
  if (key.includes("биолог")) return assetPaths.icons.biology;
  if (key.includes("хим")) return assetPaths.icons.chemistry;
  if (key.includes("информ")) return assetPaths.icons.informatics;
  if (key.includes("истор") || key.includes("тарих")) return assetPaths.icons.history;
  if (key.includes("матем")) return assetPaths.icons.math;
  return assetPaths.icons.soon;
}

function difficultyLabel(value: HistoryItem["difficulty"], language: "RU" | "KZ"): string {
  if (value === "easy") return tr(language, "Легкий", "Жеңіл");
  if (value === "hard") return tr(language, "Сложный", "Күрделі");
  return tr(language, "Средний", "Орташа");
}

function attemptTitle(
  item: Pick<HistoryItem, "subject_name" | "subject_name_ru" | "subject_name_kz" | "exam_kind">,
  language: "RU" | "KZ",
): string {
  if (item.exam_kind === "ielts") return "IELTS";
  if (item.exam_kind === "ent") return tr(language, "ЕНТ", "ҰБТ");
  if (language === "KZ") {
    return item.subject_name_kz || item.subject_name_ru || item.subject_name;
  }
  return item.subject_name_ru || item.subject_name_kz || item.subject_name;
}

function languageLabel(value: HistoryItem["language"], language: "RU" | "KZ"): string {
  if (value === "KZ") {
    return tr(language, "Каз", "Қаз");
  }
  return tr(language, "Рус", "Орыс");
}

function formatRelativeDate(value: string, language: "RU" | "KZ"): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return tr(language, "Недавно", "Жақында");

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(date);
  target.setHours(0, 0, 0, 0);
  const diffDays = Math.round((today.getTime() - target.getTime()) / 86_400_000);

  if (diffDays === 0) return tr(language, "Сегодня", "Бүгін");
  if (diffDays === 1) return tr(language, "Вчера", "Кеше");
  return date.toLocaleDateString(uiLocale(language), { day: "2-digit", month: "2-digit", year: "numeric" });
}

function resolveScoreClass(percent: number): "scoreSuccess" | "scoreWarning" | "scoreDanger" {
  if (percent >= 75) return "scoreSuccess";
  if (percent >= 50) return "scoreWarning";
  return "scoreDanger";
}
