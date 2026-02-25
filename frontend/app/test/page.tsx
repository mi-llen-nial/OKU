"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import { assetPaths } from "@/src/assets";
import { generateTest, getSubjects } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { Difficulty, Language, Mode, Subject } from "@/lib/types";
import styles from "@/app/test/test-setup.module.css";

type SubjectIconKey =
  | "math"
  | "algebra"
  | "geometry"
  | "physics"
  | "english"
  | "russian"
  | "history"
  | "biology"
  | "chemistry"
  | "informatics"
  | "soon";

interface ModeInfo {
  value: Mode;
  title: string;
  description: string;
  icon: string;
}

interface SubjectCatalogItem {
  key: string;
  name_ru: string;
  name_kz: string;
  description_ru: string;
  description_kz: string;
  iconKey: SubjectIconKey;
  aliases: string[];
  subject_id: number | null;
  available: boolean;
}

const MODES: ModeInfo[] = [
  {
    value: "text",
    title: "Стандартный",
    description: "Классический режим: чтение вопроса и ответы в текстовом формате.",
    icon: assetPaths.icons.text,
  },
  {
    value: "audio",
    title: "Аудио",
    description: "Режим, где вы можете воспроизводить вопросы в аудио формате.",
    icon: assetPaths.icons.headphones,
  },
  {
    value: "oral",
    title: "Устный",
    description: "Режим для устных ответов: вы говорите, а система оценивает ответ.",
    icon: assetPaths.icons.microphone,
  },
];

const SUBJECT_TEMPLATE: Array<Omit<SubjectCatalogItem, "subject_id" | "available">> = [
  {
    key: "math",
    name_ru: "Математика",
    name_kz: "Математика",
    description_ru: "Математика для средних классов",
    description_kz: "Орта сыныптарға арналған математика",
    iconKey: "math",
    aliases: ["математика"],
  },
  {
    key: "algebra",
    name_ru: "Алгебра",
    name_kz: "Алгебра",
    description_ru: "Математика для старших классов",
    description_kz: "Жоғары сыныптарға арналған математика",
    iconKey: "algebra",
    aliases: ["алгебра"],
  },
  {
    key: "geometry",
    name_ru: "Геометрия",
    name_kz: "Геометрия",
    description_ru: "Материал для старших классов",
    description_kz: "Жоғары сыныптарға арналған материал",
    iconKey: "geometry",
    aliases: ["геометрия"],
  },
  {
    key: "physics",
    name_ru: "Физика",
    name_kz: "Физика",
    description_ru: "Естественные науки для старших классов",
    description_kz: "Жаратылыстану жоғары сыныптарға",
    iconKey: "physics",
    aliases: ["физика"],
  },
  {
    key: "english",
    name_ru: "Английский язык",
    name_kz: "Ағылшын тілі",
    description_ru: "Языковая практика и грамматика",
    description_kz: "Тілдік практика мен грамматика",
    iconKey: "english",
    aliases: ["английскийязык", "агылшынтили"],
  },
  {
    key: "russian",
    name_ru: "Русский язык",
    name_kz: "Орыс тілі",
    description_ru: "Грамматика, лексика и чтение",
    description_kz: "Грамматика, сөздік және оқу",
    iconKey: "russian",
    aliases: ["русскийязык", "орыстили"],
  },
  {
    key: "history",
    name_ru: "Всемирная история",
    name_kz: "Дүниежүзі тарихы",
    description_ru: "Ключевые события и даты",
    description_kz: "Негізгі оқиғалар мен даталар",
    iconKey: "history",
    aliases: ["история", "тарих", "всемирнаяистория"],
  },
  {
    key: "biology",
    name_ru: "Биология",
    name_kz: "Биология",
    description_ru: "Живые системы и процессы",
    description_kz: "Тірі жүйелер мен үдерістер",
    iconKey: "biology",
    aliases: ["биология"],
  },
  {
    key: "chemistry",
    name_ru: "Химия",
    name_kz: "Химия",
    description_ru: "Основы веществ и реакций",
    description_kz: "Заттар мен реакциялар негізі",
    iconKey: "chemistry",
    aliases: ["химия"],
  },
  {
    key: "informatics",
    name_ru: "Информатика",
    name_kz: "Информатика",
    description_ru: "Алгоритмы и цифровая грамотность",
    description_kz: "Алгоритмдер және цифрлық сауат",
    iconKey: "informatics",
    aliases: ["информатика"],
  },
  {
    key: "soon",
    name_ru: "Скоро новое...",
    name_kz: "Жақында жаңа...",
    description_ru: "Здесь скоро будут новые материалы",
    description_kz: "Мұнда жақында жаңа материалдар болады",
    iconKey: "soon",
    aliases: [],
  },
];

const DIFFICULTIES: Array<{ value: Difficulty; title: string }> = [
  { value: "easy", title: "Лёгкий" },
  { value: "medium", title: "Средний" },
  { value: "hard", title: "Сложный" },
];

const QUESTION_COUNTS = [5, 10, 15, 20, 25] as const;

const ICON_BY_SUBJECT: Record<SubjectIconKey, string> = {
  math: assetPaths.icons.math,
  algebra: assetPaths.icons.algebra,
  geometry: assetPaths.icons.geometry,
  physics: assetPaths.icons.physics,
  english: assetPaths.icons.english,
  russian: assetPaths.icons.russian,
  history: assetPaths.icons.history,
  biology: assetPaths.icons.biology,
  chemistry: assetPaths.icons.chemistry,
  informatics: assetPaths.icons.informatics,
  soon: assetPaths.icons.soon,
};

function normalizeSubjectName(value: string): string {
  return value
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[^a-zа-я0-9әіңғүұқөһ]/gi, "");
}

export default function TestSetupPage() {
  const router = useRouter();

  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subjectId, setSubjectId] = useState<number | null>(null);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [language, setLanguage] = useState<Language>("RU");
  const [mode, setMode] = useState<Mode>("text");
  const [numQuestions, setNumQuestions] = useState(10);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    getSubjects(token)
      .then((data) => {
        setSubjects(data);
        setSubjectId(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить предметы"));
  }, []);

  useEffect(() => {
    if (!isSettingsModalOpen) return;

    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !loading) {
        setIsSettingsModalOpen(false);
        setError("");
        setSubjectId(null);
      }
    };

    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [isSettingsModalOpen, loading]);

  const subjectCatalog = useMemo<SubjectCatalogItem[]>(() => {
    const apiByNormalizedName = new Map<string, Subject>();
    for (const subject of subjects) {
      apiByNormalizedName.set(normalizeSubjectName(subject.name_ru), subject);
      apiByNormalizedName.set(normalizeSubjectName(subject.name_kz), subject);
    }

    const catalog = SUBJECT_TEMPLATE.map((item) => {
      if (item.key === "soon") {
        return {
          ...item,
          subject_id: null,
          available: false,
        };
      }

      const match = item.aliases
        .map((alias) => apiByNormalizedName.get(normalizeSubjectName(alias)))
        .find(Boolean);

      return {
        ...item,
        subject_id: match?.id ?? null,
        available: Boolean(match),
      };
    });

    const used = new Set(catalog.filter((item) => item.subject_id !== null).map((item) => item.subject_id as number));
    const extras: SubjectCatalogItem[] = subjects
      .filter((subject) => !used.has(subject.id))
      .map((subject) => ({
        key: `api-${subject.id}`,
        name_ru: subject.name_ru,
        name_kz: subject.name_kz,
        description_ru: "Дополнительный предмет",
        description_kz: "Қосымша пән",
        iconKey: "soon",
        aliases: [],
        subject_id: subject.id,
        available: true,
      }));

    return [...catalog, ...extras];
  }, [subjects]);

  const selectedSubject = useMemo(() => subjects.find((item) => item.id === subjectId) || null, [subjects, subjectId]);
  const selectedSubjectTitle = selectedSubject ? (language === "RU" ? selectedSubject.name_ru : selectedSubject.name_kz) : "";

  const closeSettingsModal = () => {
    if (loading) return;
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
    setIsSettingsModalOpen(false);
    setError("");
    setSubjectId(null);
  };

  const createTest = async () => {
    const token = getToken();
    if (!token) return;

    if (!subjectId) {
      setError("Сначала выберите предмет.");
      return;
    }

    try {
      setLoading(true);
      setError("");

      const test = await generateTest(token, {
        subject_id: subjectId,
        difficulty,
        language,
        mode,
        num_questions: numQuestions,
      });

      router.push(`/test/${test.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сгенерировать тест");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <div className={styles.page}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Режим прохождения</h2>
              <p className={styles.sectionSubtitle}>Выберите формат, в котором вам удобнее сдавать тест.</p>
            </div>
            <div className={styles.modeGrid}>
              {MODES.map((item) => (
                <article className={styles.modeItem} key={item.value}>
                  <img className={styles.modeIcon} src={item.icon} alt={item.title} />
                  <div>
                    <h3 className={styles.modeTitle}>{item.title}</h3>
                    <p className={styles.modeText}>{item.description}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Общеобразовательные предметы</h2>
              <p className={styles.sectionSubtitle}>Сначала определите предмет, затем настройте параметры теста.</p>
            </div>

            <div className={styles.subjectGrid}>
              {subjectCatalog.map((item) => {
                const isActive = item.subject_id === subjectId && item.available;
                const title = language === "RU" ? item.name_ru : item.name_kz;
                const description = language === "RU" ? item.description_ru : item.description_kz;

                return (
                  <button
                    key={item.key}
                    type="button"
                    className={`${styles.subjectCard} ${isActive ? styles.subjectCardActive : ""} ${!item.available ? styles.subjectCardDisabled : ""}`}
                    onClick={() => {
                      if (!item.available || !item.subject_id) {
                        setError("Этот предмет скоро станет доступен.");
                        return;
                      }

                      setError("");
                      setSubjectId(item.subject_id);
                      setIsSettingsModalOpen(true);
                    }}
                  >
                    <img className={styles.subjectIcon} src={ICON_BY_SUBJECT[item.iconKey]} alt={title} />
                    <div className={styles.subjectBody}>
                      <h3 className={styles.subjectTitle}>{title}</h3>
                      <p className={styles.subjectDescription}>{description}</p>
                    </div>
                  </button>
                );
              })}
            </div>

            {error && !isSettingsModalOpen && <div className="errorText">{error}</div>}

            <div className={styles.actions}>
              <Button variant="secondary" onClick={() => router.push("/history")}>
                История попыток
              </Button>
            </div>
          </section>
        </div>

        {isSettingsModalOpen && (
          <div className={styles.modalOverlay} role="presentation" onClick={closeSettingsModal}>
            <section
              className={styles.modal}
              role="dialog"
              aria-modal="true"
              aria-label="Настройки теста"
              onClick={(event) => event.stopPropagation()}
            >
              <header className={styles.modalHeader}>
                <h3>Настройки теста</h3>
                <p>{selectedSubjectTitle ? `Предмет: ${selectedSubjectTitle}` : "Настройте тест под свои задачи"}</p>
              </header>

              <div className={styles.modalBlock}>
                <span className={styles.settingLabel}>Сложность</span>
                <div className={styles.choiceRow}>
                  {DIFFICULTIES.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      className={`${styles.choiceButton} ${difficulty === item.value ? styles.choiceButtonActive : ""}`}
                      onClick={() => setDifficulty(item.value)}
                    >
                      {item.title}
                    </button>
                  ))}
                </div>
              </div>

              <div className={styles.modalBlock}>
                <span className={styles.settingLabel}>Режим</span>
                <div className={styles.choiceRow}>
                  {MODES.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      className={`${styles.choiceButton} ${mode === item.value ? styles.choiceButtonActive : ""}`}
                      onClick={() => setMode(item.value)}
                    >
                      {item.title}
                    </button>
                  ))}
                </div>
              </div>

              <div className={styles.modalBlock}>
                <span className={styles.settingLabel}>Язык</span>
                <div className={styles.choiceRow}>
                  {([
                    { value: "RU", title: "Русский" },
                    { value: "KZ", title: "Казахский" },
                  ] as const).map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      className={`${styles.choiceButton} ${language === item.value ? styles.choiceButtonActive : ""}`}
                      onClick={() => setLanguage(item.value)}
                    >
                      {item.title}
                    </button>
                  ))}
                </div>
              </div>

              <div className={styles.modalBlock}>
                <span className={styles.settingLabel}>Количество вопросов</span>
                <div className={styles.choiceRow}>
                  {QUESTION_COUNTS.map((value) => (
                    <button
                      key={value}
                      type="button"
                      className={`${styles.choiceButton} ${numQuestions === value ? styles.choiceButtonActive : ""}`}
                      onClick={() => setNumQuestions(value)}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </div>

              {error && <div className="errorText">{error}</div>}

              <div className={styles.modalActions}>
                <Button disabled={loading || !subjectId} onClick={createTest}>
                  {loading ? "Генерируем тест..." : "Начать тест"}
                </Button>
                <Button variant="ghost" onClick={closeSettingsModal}>
                  Отмена
                </Button>
              </div>
            </section>
          </div>
        )}
      </AppShell>
    </AuthGuard>
  );
}
