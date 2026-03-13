"use client";

import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import { getHistory, getProgress, getSubjects } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { readBlitzResultHistory } from "@/lib/blitz";
import { tr, useUiLanguage } from "@/lib/i18n";
import { HistoryItem, Language, StudentProgress, Subject } from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/app/progress/progress.module.css";

interface MetricItem {
  id: string;
  label: string;
  meta: string;
  value: string;
}

interface SubjectMetricItem {
  id: string;
  name: string;
  value: string;
}

interface ExtraMetricItem {
  id: string;
  label: string;
  meta: string;
  value: string;
}

const SUBJECT_FALLBACK_RU = [
  "Математика",
  "Алгебра",
  "Геометрия",
  "Физика",
  "Английский язык",
  "Русский язык",
  "Всемирная история",
  "Биология",
  "Химия",
  "Информатика",
];

const SUBJECT_FALLBACK_KZ = [
  "Математика",
  "Алгебра",
  "Геометрия",
  "Физика",
  "Ағылшын тілі",
  "Орыс тілі",
  "Дүниежүзі тарихы",
  "Биология",
  "Химия",
  "Информатика",
];

export default function ProgressPage() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [progress, setProgress] = useState<StudentProgress | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [blitzHistory, setBlitzHistory] = useState<Array<{ percent: number }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    let isCancelled = false;
    setBlitzHistory(readBlitzResultHistory().map((item) => ({ percent: item.percent })));

    (async () => {
      try {
        const [progressPayload, historyPayload] = await Promise.all([getProgress(token), getHistory(token)]);
        if (isCancelled) return;
        setProgress(progressPayload);
        setHistory(historyPayload);
      } catch (err) {
        if (!isCancelled) {
          setError(err instanceof Error ? err.message : t("Не удалось загрузить аналитику", "Аналитиканы жүктеу мүмкін болмады"));
        }
      } finally {
        if (!isCancelled) {
          setLoading(false);
        }
      }

      try {
        const subjectsPayload = await getSubjects(token);
        if (!isCancelled) {
          setSubjects(subjectsPayload);
        }
      } catch (err) {
        console.warn("Не удалось загрузить список предметов для аналитики:", err);
      }
    })();

    return () => {
      isCancelled = true;
    };
  }, [uiLanguage]);

  const sortedByPercent = useMemo(() => history.slice().sort((left, right) => right.percent - left.percent), [history]);

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
  }, [history, t, uiLanguage]);

  const alignmentPercent = useMemo(() => {
    const avg = progress?.avg_percent ?? 0;
    const warningPenalty = Math.min(progress?.total_warnings ?? 0, 15);
    return Math.max(0, Math.min(100, Math.round(avg * 0.8 + 50 - warningPenalty)));
  }, [progress?.avg_percent, progress?.total_warnings]);

  const testsToday = useMemo(() => {
    const today = new Date();
    const todayKey = dateKey(today);
    return history.filter((item) => dateKey(new Date(item.created_at)) === todayKey).length;
  }, [history]);

  const streakDays = useMemo(() => {
    if (history.length === 0) return 0;
    const uniqueDays = [...new Set(history.map((item) => dateKey(new Date(item.created_at))))].sort((a, b) =>
      b.localeCompare(a),
    );
    if (uniqueDays.length === 0) return 0;

    let streak = 1;
    let current = parseDateKey(uniqueDays[0]);
    for (let i = 1; i < uniqueDays.length; i += 1) {
      const next = parseDateKey(uniqueDays[i]);
      if (!current || !next) break;
      const expected = new Date(current);
      expected.setDate(expected.getDate() - 1);
      if (dateKey(expected) !== uniqueDays[i]) break;
      streak += 1;
      current = next;
    }
    return streak;
  }, [history]);

  const metrics = useMemo<MetricItem[]>(() => {
    return [
      {
        id: "avg",
        label: t("Средняя успеваемость", "Орташа үлгерім"),
        meta: t("По всем попыткам", "Барлық талпыныс бойынша"),
        value: formatPercent(progress?.avg_percent ?? 0),
      },
      {
        id: "best",
        label: t("Лучший результат", "Ең үздік нәтиже"),
        meta: bestAttempt
          ? `${attemptTitle(bestAttempt, uiLanguage)} (${difficultyLabel(bestAttempt.difficulty, uiLanguage)})`
          : t("Пока нет данных", "Әзірге дерек жоқ"),
        value: formatPercent(progress?.best_percent ?? 0),
      },
      {
        id: "total",
        label: t("Всего тестов", "Барлық тест саны"),
        meta: t("За все время", "Барлық уақыт ішінде"),
        value: String(progress?.total_tests ?? 0),
      },
      {
        id: "alignment",
        label: t("Соответствие", "Сәйкестік"),
        meta: t("Относительно образования", "Білім деңгейіне қатысты"),
        value: `${alignmentPercent}%`,
      },
      {
        id: "worst",
        label: t("Худший результат", "Ең төмен нәтиже"),
        meta: worstAttempt
          ? `${attemptTitle(worstAttempt, uiLanguage)} (${difficultyLabel(worstAttempt.difficulty, uiLanguage)})`
          : t("Пока нет данных", "Әзірге дерек жоқ"),
        value: worstAttempt ? formatPercent(worstAttempt.percent) : "–",
      },
      {
        id: "favorite",
        label: t("Любимчик", "Таңдаулы"),
        meta: t("Наиболее часто проходимый", "Ең жиі өтетін"),
        value: formatSubjectTitle(favoriteSubject, uiLanguage),
      },
      {
        id: "warnings",
        label: t("Предупреждения", "Ескертулер"),
        meta: t("Подозрение в спекуляции", "Ереже бұзу қаупі"),
        value: String(progress?.total_warnings ?? 0),
      },
      {
        id: "streak",
        label: t("Дней в ударе", "Белсенді күндер"),
        meta: t("Дней подряд проходите тесты", "Тесттерді қатарынан өткен күндер"),
        value: String(streakDays),
      },
      {
        id: "today",
        label: t("Тесты за сегодня", "Бүгінгі тесттер"),
        meta: t("Пройденных тестов", "Өткен тест саны"),
        value: String(testsToday),
      },
    ];
  }, [
    alignmentPercent,
    bestAttempt,
    favoriteSubject,
    progress?.avg_percent,
    progress?.best_percent,
    progress?.total_tests,
    progress?.total_warnings,
    streakDays,
    t,
    testsToday,
    uiLanguage,
    worstAttempt,
  ]);

  const subjectMetrics = useMemo<SubjectMetricItem[]>(() => {
    const stats = progress?.subject_stats || [];
    const statsBySubjectId = new Map(
      stats.map((item) => [
        item.subject_id,
        {
          percent: item.avg_percent,
        },
      ]),
    );

    if (subjects.length > 0) {
      const metrics = subjects.map((subject) => {
        const title =
          uiLanguage === "KZ"
            ? subject.name_kz || subject.name_ru || `Пән #${subject.id}`
            : subject.name_ru || subject.name_kz || `Предмет #${subject.id}`;
        const stat = statsBySubjectId.get(subject.id);
        return {
          id: String(subject.id),
          name: title,
          value: stat ? formatPercent(stat.percent) : "–",
        };
      });

      for (const stat of stats) {
        if (subjects.some((subject) => subject.id === stat.subject_id)) continue;
        const title =
          uiLanguage === "KZ"
            ? stat.subject_name_kz || stat.subject_name_ru || stat.subject_name
            : stat.subject_name_ru || stat.subject_name_kz || stat.subject_name;
        metrics.push({
          id: String(stat.subject_id),
          name: title,
          value: formatPercent(stat.avg_percent),
        });
      }
      return metrics;
    }

    if (stats.length > 0) {
      return stats.map((stat) => ({
        id: String(stat.subject_id),
        name:
          uiLanguage === "KZ"
            ? stat.subject_name_kz || stat.subject_name_ru || stat.subject_name
            : stat.subject_name_ru || stat.subject_name_kz || stat.subject_name,
        value: formatPercent(stat.avg_percent),
      }));
    }

    const fallbackNames = uiLanguage === "KZ" ? SUBJECT_FALLBACK_KZ : SUBJECT_FALLBACK_RU;
    return fallbackNames.map((subject, index) => ({
      id: `fallback-${index}`,
      name: subject,
      value: "–",
    }));
  }, [progress?.subject_stats, subjects, uiLanguage]);

  const examMetrics = useMemo<ExtraMetricItem[]>(() => {
    const createExamMetric = (examKind: "ent" | "ielts", title: string): ExtraMetricItem => {
      const examHistory = history.filter((item) => item.exam_kind === examKind);
      if (examHistory.length === 0) {
        return {
          id: examKind,
          label: title,
          meta: t("Пока нет попыток", "Әзірге талпыныс жоқ"),
          value: "–",
        };
      }

      const best = Math.max(...examHistory.map((item) => item.percent));
      const avg = examHistory.reduce((acc, item) => acc + item.percent, 0) / examHistory.length;

      return {
        id: examKind,
        label: title,
        meta: t("Попыток", "Талпыныс") + `: ${examHistory.length} · ` + t("Средний", "Орташа") + `: ${formatPercent(avg)}`,
        value: formatPercent(best),
      };
    };

    return [createExamMetric("ent", "ЕНТ"), createExamMetric("ielts", "IELTS")];
  }, [history, t]);

  const blitzMetrics = useMemo<ExtraMetricItem[]>(() => {
    if (blitzHistory.length === 0) {
      return [
        {
          id: "blitz-best",
          label: t("Лучший результат", "Ең үздік нәтиже"),
          meta: t("Быстрые вопросы Да/Нет", "Жылдам Иә/Жоқ сұрақтары"),
          value: "–",
        },
        {
          id: "blitz-avg",
          label: t("Средний результат", "Орташа нәтиже"),
          meta: t("По всем блиц-сессиям", "Барлық блиц-сессия бойынша"),
          value: "–",
        },
        {
          id: "blitz-attempts",
          label: t("Всего блицев", "Барлық блиц саны"),
          meta: t("Завершенных сессий", "Аяқталған сессиялар"),
          value: "0",
        },
      ];
    }

    const best = Math.max(...blitzHistory.map((item) => item.percent));
    const avg = blitzHistory.reduce((acc, item) => acc + item.percent, 0) / blitzHistory.length;

    return [
      {
        id: "blitz-best",
        label: t("Лучший результат", "Ең үздік нәтиже"),
        meta: t("Быстрые вопросы Да/Нет", "Жылдам Иә/Жоқ сұрақтары"),
        value: formatPercent(best),
      },
      {
        id: "blitz-avg",
        label: t("Средний результат", "Орташа нәтиже"),
        meta: t("По всем блиц-сессиям", "Барлық блиц-сессия бойынша"),
        value: formatPercent(avg),
      },
      {
        id: "blitz-attempts",
        label: t("Всего блицев", "Барлық блиц саны"),
        meta: t("Завершенных сессий", "Аяқталған сессиялар"),
        value: String(blitzHistory.length),
      },
    ];
  }, [blitzHistory, t]);

  const exportRows = useMemo(() => {
    const rows: Array<{ label: string; value: string }> = [];
    for (const item of metrics) {
      rows.push({ label: item.label, value: item.value });
    }
    for (const subject of subjectMetrics) {
      rows.push({ label: `${t("Предмет", "Пән")}: ${subject.name}`, value: subject.value });
    }
    for (const exam of examMetrics) {
      rows.push({ label: `${t("Подготовка", "Дайындық")}: ${exam.label}`, value: exam.value });
    }
    for (const blitz of blitzMetrics) {
      rows.push({ label: `${t("Блиц", "Блиц")}: ${blitz.label}`, value: blitz.value });
    }
    return rows;
  }, [blitzMetrics, examMetrics, metrics, subjectMetrics, t]);

  const exportCsv = () => {
    const rows = [
      `${t("Показатель", "Көрсеткіш")},${t("Значение", "Мәні")}`,
      ...exportRows.map((item) => `${toCsvCell(item.label)},${toCsvCell(item.value)}`),
    ];
    const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = uiLanguage === "KZ" ? "oku-analitika.csv" : "oku-analytics.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <div className={styles.page}>
            <div>{t("Загрузка...", "Жүктелуде...")}</div>
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
              <h2 className={styles.sectionTitle}>{t("Аналитика", "Аналитика")}</h2>
              <p className={styles.sectionSubtitle}>{t("Краткий пересказ вашего текущего прогресса", "Ағымдағы прогрестің қысқаша көрінісі")}</p>
            </div>

            <div className={styles.metricsGrid}>
              {metrics.map((item) => (
                <article className={styles.metricItem} key={item.id}>
                  <h3 className={styles.metricLabel}>{item.label}</h3>
                  <p className={styles.metricMeta}>{item.meta}</p>
                  <p className={styles.metricValue}>{item.value}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>{t("По предметам", "Пәндер бойынша")}</h2>
              <p className={styles.sectionSubtitle}>{t("Ваша статистика по отдельным предметам", "Жекелеген пәндер бойынша статистика")}</p>
            </div>

            {error && <div className="errorText">{error}</div>}

            <div className={styles.subjectGrid}>
              {subjectMetrics.map((item) => (
                <article className={styles.subjectItem} key={item.id}>
                  <h3 className={styles.metricLabel}>{item.name}</h3>
                  <p className={styles.metricMeta}>{t("По всем попыткам", "Барлық талпыныс бойынша")}</p>
                  <p className={styles.metricValue}>{item.value}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>{t("Подготовка к важному", "Маңыздысына дайындық")}</h2>
              <p className={styles.sectionSubtitle}>{t("Статистика по экзаменационным режимам ЕНТ и IELTS", "ЕНТ және IELTS емтихан режимдері бойынша статистика")}</p>
            </div>

            <div className={styles.extraGrid}>
              {examMetrics.map((item) => (
                <article className={styles.extraCard} key={item.id}>
                  <h3 className={styles.metricLabel}>{item.label}</h3>
                  <p className={styles.metricMeta}>{item.meta}</p>
                  <p className={styles.metricValue}>{item.value}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeaderCentered}>
              <h2 className={styles.sectionTitle}>{t("Блиц", "Блиц")}</h2>
              <p className={styles.sectionSubtitle}>{t("Краткая статистика по быстрым сессиям", "Жылдам сессиялар бойынша қысқаша статистика")}</p>
            </div>

            <div className={styles.extraGrid}>
              {blitzMetrics.map((item, index) => (
                <article className={styles.extraCard} key={item.id}>
                  {index === 0 ? (
                    <div className={styles.iconRow}>
                      <img className={styles.blitzIcon} src={assetPaths.icons.blitz} alt={t("Блиц", "Блиц")} />
                    </div>
                  ) : null}
                  <h3 className={styles.metricLabel}>{item.label}</h3>
                  <p className={styles.metricMeta}>{item.meta}</p>
                  <p className={styles.metricValue}>{item.value}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.exportSection}>
            <h3 className={styles.exportTitle}>{t("Экспортировать статистику", "Статистиканы экспорттау")}</h3>
            <div className={styles.exportActions}>
              <Button className={styles.exportButton} onClick={exportCsv}>
                {t("Скачать .csv", ".csv жүктеу")}
              </Button>
            </div>
          </section>

          <footer className={styles.footer}>oku.com.kz</footer>
        </div>
      </AppShell>
    </AuthGuard>
  );
}

function normalizeName(value: string): string {
  return value
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[^a-zа-я0-9әіңғүұқөһ]/gi, "");
}

function difficultyLabel(value: HistoryItem["difficulty"], language: Language): string {
  if (value === "easy") return tr(language, "Легкий", "Жеңіл");
  if (value === "hard") return tr(language, "Сложный", "Күрделі");
  return tr(language, "Средний", "Орташа");
}

function attemptTitle(
  item: Pick<HistoryItem, "subject_name" | "subject_name_ru" | "subject_name_kz" | "exam_kind">,
  language: Language,
): string {
  if (item.exam_kind === "ielts") return "IELTS";
  if (item.exam_kind === "ent") return tr(language, "ЕНТ", "ҰБТ");
  if (language === "KZ") {
    return item.subject_name_kz || item.subject_name_ru || item.subject_name;
  }
  return item.subject_name_ru || item.subject_name_kz || item.subject_name;
}

function formatPercent(value: number): string {
  const rounded = Math.round((value || 0) * 10) / 10;
  if (Number.isInteger(rounded)) return `${rounded.toFixed(0)}%`;
  return `${rounded.toFixed(1)}%`;
}

function formatSubjectTitle(value: string, language: Language): string {
  if (!value || value === "Нет данных" || value === "Дерек жоқ") return tr(language, "Нет данных", "Дерек жоқ");
  const normalized = normalizeName(value);
  if (normalized.includes("ielts")) return "IELTS";
  if (normalized.includes("ент") || normalized.includes("ent")) return "ЕНТ";
  return value
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function dateKey(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseDateKey(value: string): Date | null {
  const parts = value.split("-").map(Number);
  if (parts.length !== 3 || parts.some((part) => Number.isNaN(part))) return null;
  return new Date(parts[0], parts[1] - 1, parts[2]);
}

function toCsvCell(value: string): string {
  return `"${value.replace(/"/g, '""')}"`;
}
