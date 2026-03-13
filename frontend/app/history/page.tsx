"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { generateMistakesTest, getHistory, getProgress } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { tr, uiLocale, useUiLanguage } from "@/lib/i18n";
import { HistoryItem, StudentProgress } from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/app/history/history.module.css";

const INITIAL_VISIBLE_TESTS = 5;
const LOAD_MORE_STEP = 10;

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

export default function HistoryPage() {
  const router = useRouter();
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [progress, setProgress] = useState<StudentProgress | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE_TESTS);
  const [loading, setLoading] = useState(true);
  const [launchingMistakes, setLaunchingMistakes] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    Promise.all([getProgress(token), getHistory(token)])
      .then(([progressData, historyData]) => {
        setProgress(progressData);
        setHistory(historyData);
        setVisibleCount(INITIAL_VISIBLE_TESTS);
      })
      .catch((err) => setError(err instanceof Error ? err.message : t("Не удалось загрузить историю", "Тарихты жүктеу мүмкін болмады")))
      .finally(() => setLoading(false));
  }, []);

  const sortedByPercent = useMemo(
    () => history.slice().sort((left, right) => right.percent - left.percent),
    [history],
  );
  const bestAttempt = sortedByPercent[0] || null;
  const worstAttempt = sortedByPercent[sortedByPercent.length - 1] || null;

  const favoriteSubject = useMemo(() => {
    if (history.length === 0) return t("Нет данных", "Дерек жоқ");
    const counter = new Map<string, number>();
    for (const item of history) {
      const title = attemptTitle(item, uiLanguage);
      counter.set(title, (counter.get(title) || 0) + 1);
    }
    return [...counter.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] || t("Нет данных", "Дерек жоқ");
  }, [history, t]);

  const alignmentPercent = useMemo(() => {
    const avg = progress?.avg_percent ?? 0;
    const warningPenalty = Math.min(progress?.total_warnings ?? 0, 15);
    return Math.max(0, Math.min(100, Math.round(avg * 0.8 + 50 - warningPenalty)));
  }, [progress?.avg_percent, progress?.total_warnings]);

  const visibleHistory = useMemo(() => history.slice(0, visibleCount), [history, visibleCount]);
  const hasMoreHistory = visibleCount < history.length;

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
          <div className={styles.page}>
            <Card title={t("История", "Тарих")}>{t("Загрузка...", "Жүктелуде...")}</Card>
          </div>
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
              <h2 className={styles.sectionTitle}>{t("История", "Тарих")}</h2>
              <p className={styles.sectionSubtitle}>{t("Краткий пересказ вашего текущего прогресса", "Ағымдағы прогрестің қысқаша көрінісі")}</p>
            </div>

            <div className={styles.metricsGrid}>
              <article className={styles.metricItem}>
                <h3 className={styles.metricLabel}>{t("Средняя успеваемость", "Орташа үлгерім")}</h3>
                <p className={styles.metricMeta}>{t("По всем попыткам", "Барлық талпыныс бойынша")}</p>
                <p className={styles.metricValue}>{formatPercent(progress?.avg_percent ?? 0)}</p>
              </article>

              <article className={styles.metricItem}>
                <h3 className={styles.metricLabel}>{t("Лучший результат", "Ең үздік нәтиже")}</h3>
                <p className={styles.metricMeta}>
                  {bestAttempt ? `${attemptTitle(bestAttempt, uiLanguage)} (${difficultyLabel(bestAttempt.difficulty, uiLanguage)})` : t("Пока нет данных", "Әзірге дерек жоқ")}
                </p>
                <p className={styles.metricValue}>{formatPercent(progress?.best_percent ?? 0)}</p>
              </article>

              <article className={styles.metricItem}>
                <h3 className={styles.metricLabel}>{t("Всего тестов", "Барлық тест саны")}</h3>
                <p className={styles.metricMeta}>{t("За все время", "Барлық уақыт ішінде")}</p>
                <p className={styles.metricValue}>{progress?.total_tests ?? 0}</p>
              </article>

              <article className={styles.metricItem}>
                <h3 className={styles.metricLabel}>{t("Соответствие", "Сәйкестік")}</h3>
                <p className={styles.metricMeta}>{t("Относительно образования", "Білім деңгейіне қатысты")}</p>
                <p className={styles.metricValue}>{alignmentPercent}%</p>
              </article>

              <article className={styles.metricItem}>
                <h3 className={styles.metricLabel}>{t("Худший результат", "Ең төмен нәтиже")}</h3>
                <p className={styles.metricMeta}>
                  {worstAttempt ? `${attemptTitle(worstAttempt, uiLanguage)} (${difficultyLabel(worstAttempt.difficulty, uiLanguage)})` : t("Пока нет данных", "Әзірге дерек жоқ")}
                </p>
                <p className={styles.metricValue}>{worstAttempt ? formatPercent(worstAttempt.percent) : "–"}</p>
              </article>

              <article className={styles.metricItem}>
                <h3 className={styles.metricLabel}>{t("Любимчик", "Таңдаулы")}</h3>
                <p className={styles.metricMeta}>{t("Наиболее часто проходимый", "Ең жиі өтетін")}</p>
                <p className={styles.metricValueText}>{formatSubjectTitle(favoriteSubject, uiLanguage)}</p>
              </article>
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>{t("История тестов", "Тесттер тарихы")}</h2>
              <p className={styles.sectionSubtitle}>{t("Последние попытки и текущий уровень результатов", "Соңғы талпыныстар және ағымдағы нәтиже деңгейі")}</p>
            </div>

            {error && <div className="errorText">{error}</div>}

            {visibleHistory.length === 0 ? (
              <div className={styles.emptyState}>
                <p className={styles.emptyText}>{t("У вас пока нет завершенных тестов.", "Сізде әлі аяқталған тесттер жоқ.")}</p>
                <Button onClick={() => router.push("/test")}>{t("Пройти первый тест", "Бірінші тестті өту")}</Button>
              </div>
            ) : (
              <>
                <div className={styles.attemptList}>
                  {visibleHistory.map((item) => {
                    const scoreClass = resolveScoreClass(item.percent);
                    const title = attemptTitle(item, uiLanguage);

                    return (
                      <article className={styles.attemptCard} key={item.test_id}>
                        <div className={styles.attemptHead}>
                          <p className={styles.attemptDate}>{formatRelativeDate(item.created_at, uiLanguage)}</p>
                          <div className={styles.attemptMeta}>
                            <p className={`${styles.attemptScore} ${styles[scoreClass]}`}>{formatPercent(item.percent)}</p>
                            <p className={styles.metaStrong}>{difficultyLabel(item.difficulty, uiLanguage)}</p>
                            <p className={styles.metaStrong}>{modeLabel(item.mode, uiLanguage)}</p>
                            <p className={styles.metaStrong}>{t("Предупреждений", "Ескертулер")}: {item.warning_count}</p>
                          </div>
                        </div>

                        <div className={styles.attemptBody}>
                          <img className={styles.attemptIcon} src={resolveSubjectIcon(title)} alt={title} />
                          <div className={styles.attemptInfo}>
                            <h3 className={styles.attemptTitle}>{title}</h3>
                            <p className={styles.attemptTopics}>
                              {item.weak_topics.length > 0 ? item.weak_topics.slice(0, 3).join("   ") : t("Сильное прохождение", "Мықты өту")}
                            </p>
                          </div>
                        </div>

                        <Button block className={styles.resultButton} onClick={() => router.push(`/results/${item.test_id}`)}>
                          {t("Результаты", "Нәтижелер")}
                        </Button>
                      </article>
                    );
                  })}
                </div>

                {hasMoreHistory ? (
                  <button
                    className={styles.showMoreButton}
                    type="button"
                    onClick={() => setVisibleCount((prev) => Math.min(prev + LOAD_MORE_STEP, history.length))}
                  >
                    {t("Показать больше", "Көбірек көрсету")}
                  </button>
                ) : null}
              </>
            )}
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>{t("Рекомендуем", "Ұсынамыз")}</h2>
              <p className={styles.sectionSubtitle}>{t("Основаны на ваших тестах и результатах", "Сіздің тесттеріңіз бен нәтижелеріңіз негізінде")}</p>
            </div>

            <div className={styles.recommendGrid}>
              {recommendations.map((item) => (
                <article className={styles.recommendCard} key={item.id}>
                  <p className={styles.recommendLabel}>{item.label}</p>
                  <div className={styles.recommendTop}>
                    <img className={styles.recommendIcon} src={item.icon} alt={item.title} />
                    <div className={styles.recommendInfo}>
                      <h3 className={styles.recommendTitle}>{item.title}</h3>
                      <p className={styles.recommendText}>{item.text}</p>
                    </div>
                  </div>
                  {item.kind === "mistakes" ? (
                    <Button className={styles.recommendAction} disabled={launchingMistakes} block onClick={openMistakesReview}>
                      {launchingMistakes ? t("Подготавливаем...", "Дайындалып жатыр...") : item.action}
                    </Button>
                  ) : (
                    <Button className={styles.recommendAction} block onClick={() => router.push(item.href || "/test")}>
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

function modeLabel(value: HistoryItem["mode"], language: "RU" | "KZ"): string {
  if (value === "audio") return tr(language, "Аудио", "Аудио");
  if (value === "oral") return tr(language, "Устный", "Ауызша");
  return tr(language, "Стандарт", "Стандарт");
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
  return date.toLocaleDateString(uiLocale(language), { day: "numeric", month: "long" });
}

function formatPercent(value: number): string {
  const rounded = Math.round((value || 0) * 10) / 10;
  if (Number.isInteger(rounded)) {
    return `${rounded.toFixed(0)}%`;
  }
  return `${rounded.toFixed(1)}%`;
}

function formatSubjectTitle(value: string, language: "RU" | "KZ"): string {
  if (!value || value === "Нет данных" || value === "Дерек жоқ") return tr(language, "Нет данных", "Дерек жоқ");
  const normalized = normalizeText(value);
  if (normalized.includes("ielts")) return "IELTS";
  if (normalized.includes("ент") || normalized.includes("ent")) return "ЕНТ";
  return value
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function resolveScoreClass(percent: number): "scoreSuccess" | "scoreWarning" | "scoreDanger" {
  if (percent >= 75) return "scoreSuccess";
  if (percent >= 50) return "scoreWarning";
  return "scoreDanger";
}
