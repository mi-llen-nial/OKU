"use client";

import { Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import { createTeacherCustomTest, getTeacherGroups } from "@/lib/api";
import { getToken, getUser } from "@/lib/auth";
import { tr, useUiLanguage } from "@/lib/i18n";
import { TeacherCustomQuestionInput, TeacherGroup } from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/app/teacher/create-test/create-test.module.css";

type AnswerType = "choice" | "free_text";

interface DraftQuestion {
  id: string;
  prompt: string;
  answer_type: AnswerType;
  options: string[];
  correct_option_index: number | null;
  sample_answer: string;
}

interface DraftState {
  title: string;
  duration_minutes: number;
  warning_limit: number;
  due_date: string;
  questions: DraftQuestion[];
}

const DURATION_OPTIONS = [5, 10, 15, 20, 30, 45, 60, 90, 120];
const WARNING_OPTIONS = [0, 1, 2, 3, 5, 10];

function createEmptyQuestion(seed = Date.now()): DraftQuestion {
  return {
    id: `q-${seed}-${Math.random().toString(36).slice(2, 8)}`,
    prompt: "",
    answer_type: "choice",
    options: ["", "", "", ""],
    correct_option_index: 0,
    sample_answer: "",
  };
}

function defaultDueDate(): string {
  const date = new Date();
  date.setDate(date.getDate() + 14);
  return date.toISOString().slice(0, 10);
}

function createInitialDraft(): DraftState {
  return {
    title: "",
    duration_minutes: 5,
    warning_limit: 2,
    due_date: defaultDueDate(),
    questions: [createEmptyQuestion()],
  };
}

function toDraftStorageKey(): string | null {
  if (typeof window === "undefined") return null;
  const user = getUser();
  if (!user) return null;
  return `oku_teacher_custom_test_draft:${user.id}`;
}

function normalizeDraft(value: unknown): DraftState {
  const fallback = createInitialDraft();
  if (!value || typeof value !== "object") return fallback;
  const payload = value as Partial<DraftState>;

  const title = typeof payload.title === "string" ? payload.title : fallback.title;
  const duration = Number(payload.duration_minutes);
  const warning = Number(payload.warning_limit);
  const dueDate = typeof payload.due_date === "string" && payload.due_date ? payload.due_date : fallback.due_date;
  const rawQuestions = Array.isArray(payload.questions) ? payload.questions : fallback.questions;

  const mappedQuestions = rawQuestions
    .map((item, index): DraftQuestion | null => {
      if (!item || typeof item !== "object") return null;
      const row = item as Partial<DraftQuestion>;
      const answerType: AnswerType = row.answer_type === "free_text" ? "free_text" : "choice";
      const options = Array.isArray(row.options)
        ? row.options.map((option) => (typeof option === "string" ? option : ""))
        : ["", "", "", ""];
      const correct = typeof row.correct_option_index === "number" ? row.correct_option_index : 0;
      return {
        id: typeof row.id === "string" && row.id ? row.id : `q-restored-${index}`,
        prompt: typeof row.prompt === "string" ? row.prompt : "",
        answer_type: answerType,
        options: options.length > 0 ? options : ["", "", "", ""],
        correct_option_index: Number.isFinite(correct) ? correct : 0,
        sample_answer: typeof row.sample_answer === "string" ? row.sample_answer : "",
      };
    })
    .filter((item): item is DraftQuestion => item !== null);

  return {
    title,
    duration_minutes: Number.isFinite(duration) && duration > 0 ? duration : fallback.duration_minutes,
    warning_limit: Number.isFinite(warning) && warning >= 0 ? warning : fallback.warning_limit,
    due_date: dueDate,
    questions: mappedQuestions.length > 0 ? mappedQuestions : fallback.questions,
  };
}

function buildPayloadQuestions(
  questions: DraftQuestion[],
  t: (ru: string, kz: string) => string,
): TeacherCustomQuestionInput[] {
  return questions.map((question, index) => {
    const prompt = question.prompt.trim();
    if (!prompt) {
      throw new Error(t(`Заполните текст вопроса №${index + 1}.`, `№${index + 1} сұрақ мәтінін толтырыңыз.`));
    }

    if (question.answer_type === "choice") {
      const indexedOptions = question.options
        .map((item, optionIndex) => ({
          originalIndex: optionIndex,
          text: item.trim(),
        }))
        .filter((item) => item.text.length > 0);

      if (indexedOptions.length < 2) {
        throw new Error(
          t(
            `В вопросе №${index + 1} нужно минимум 2 варианта ответа.`,
            `№${index + 1} сұрақта кемінде 2 жауап нұсқасы болуы керек.`,
          ),
        );
      }

      if (question.correct_option_index === null || question.correct_option_index < 0) {
        throw new Error(
          t(
            `Выберите правильный вариант для вопроса №${index + 1}.`,
            `№${index + 1} сұрақ үшін дұрыс нұсқаны таңдаңыз.`,
          ),
        );
      }

      const normalizedCorrectIndex = indexedOptions.findIndex(
        (item) => item.originalIndex === question.correct_option_index,
      );
      if (normalizedCorrectIndex < 0) {
        throw new Error(
          t(
            `В вопросе №${index + 1} выбран пустой вариант как правильный.`,
            `№${index + 1} сұрақта бос нұсқа дұрыс деп таңдалған.`,
          ),
        );
      }

      return {
        prompt,
        answer_type: "choice",
        options: indexedOptions.map((item) => item.text),
        correct_option_index: normalizedCorrectIndex,
      };
    }

    const sampleAnswer = question.sample_answer.trim();
    if (!sampleAnswer) {
      throw new Error(
        t(
          `Укажите эталонный ответ для вопроса №${index + 1}.`,
          `№${index + 1} сұраққа эталон жауапты енгізіңіз.`,
        ),
      );
    }

    return {
      prompt,
      answer_type: "free_text",
      sample_answer: sampleAnswer,
    };
  });
}

function formatRuGroups(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return "группа";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "группы";
  return "групп";
}

export default function TeacherCreateTestPage() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [draft, setDraft] = useState<DraftState>(createInitialDraft);
  const [groups, setGroups] = useState<TeacherGroup[]>([]);
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([]);
  const [loadingGroups, setLoadingGroups] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const totalQuestions = draft.questions.length;

  const groupSelectionLabel = useMemo(() => {
    if (uiLanguage === "KZ") return `${selectedGroupIds.length} топ`;
    return `${selectedGroupIds.length} ${formatRuGroups(selectedGroupIds.length)}`;
  }, [selectedGroupIds.length, uiLanguage]);

  const difficultyLabel = useMemo(() => {
    const freeTextCount = draft.questions.filter((item) => item.answer_type === "free_text").length;
    if (draft.questions.length >= 16 || freeTextCount >= 6) return t("Сложный", "Күрделі");
    if (draft.questions.length >= 9 || freeTextCount >= 3) return t("Средний", "Орташа");
    return t("Легкий", "Жеңіл");
  }, [draft.questions, t]);

  useEffect(() => {
    const key = toDraftStorageKey();
    if (!key) return;
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return;
      setDraft(normalizeDraft(JSON.parse(raw)));
    } catch {
      // ignore malformed draft
    }
  }, []);

  useEffect(() => {
    const key = toDraftStorageKey();
    if (!key) return;
    try {
      localStorage.setItem(key, JSON.stringify(draft));
    } catch {
      // ignore localStorage quota errors
    }
  }, [draft]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    let cancelled = false;
    (async () => {
      try {
        setLoadingGroups(true);
        const payload = await getTeacherGroups(token);
        if (cancelled) return;
        setGroups(payload);
      } catch (requestError) {
        if (cancelled) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : t("Не удалось загрузить список групп.", "Топтар тізімін жүктеу мүмкін болмады."),
        );
      } finally {
        if (!cancelled) {
          setLoadingGroups(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [uiLanguage]);

  const updateQuestion = (questionId: string, updater: (question: DraftQuestion) => DraftQuestion) => {
    setDraft((prev) => ({
      ...prev,
      questions: prev.questions.map((question) => (question.id === questionId ? updater(question) : question)),
    }));
  };

  const addQuestion = () => {
    setDraft((prev) => ({
      ...prev,
      questions: [...prev.questions, createEmptyQuestion()],
    }));
  };

  const removeQuestion = (questionId: string) => {
    setDraft((prev) => {
      if (prev.questions.length <= 1) return prev;
      return {
        ...prev,
        questions: prev.questions.filter((question) => question.id !== questionId),
      };
    });
  };

  const addChoiceOption = (questionId: string) => {
    updateQuestion(questionId, (question) => {
      if (question.options.length >= 8) return question;
      return {
        ...question,
        options: [...question.options, ""],
      };
    });
  };

  const toggleGroupSelection = (groupId: number) => {
    setSelectedGroupIds((prev) => (prev.includes(groupId) ? prev.filter((id) => id !== groupId) : [...prev, groupId]));
  };

  const clearDraft = () => {
    setDraft(createInitialDraft());
    setSelectedGroupIds([]);
    setError("");
    setSuccess("");
  };

  const submitCustomTest = async () => {
    const token = getToken();
    if (!token) return;

    setError("");
    setSuccess("");

    const normalizedTitle = draft.title.trim();
    if (!normalizedTitle) {
      setError(t("Введите тему теста.", "Тест тақырыбын енгізіңіз."));
      return;
    }

    if (selectedGroupIds.length === 0) {
      setError(
        t(
          "Выберите хотя бы одну группу справа, чтобы назначить тест.",
          "Тестті тағайындау үшін оң жақтан кемінде бір топты таңдаңыз.",
        ),
      );
      return;
    }

    let payloadQuestions: TeacherCustomQuestionInput[];
    try {
      payloadQuestions = buildPayloadQuestions(draft.questions, t);
    } catch (validationError) {
      setError(validationError instanceof Error ? validationError.message : t("Проверьте вопросы.", "Сұрақтарды тексеріңіз."));
      return;
    }

    try {
      setSubmitting(true);
      const created = await createTeacherCustomTest(token, {
        title: normalizedTitle,
        duration_minutes: draft.duration_minutes,
        warning_limit: draft.warning_limit,
        group_ids: selectedGroupIds,
        questions: payloadQuestions,
      });

      setSuccess(
        t(
          `Тест «${created.title}» создан. Вопросов: ${created.questions_count}.`,
          `«${created.title}» тесті құрылды. Сұрақтар: ${created.questions_count}.`,
        ),
      );
      setDraft(createInitialDraft());
      setSelectedGroupIds([]);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : t("Не удалось создать тест.", "Тестті құру мүмкін болмады."),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthGuard roles={["teacher"]}>
      <AppShell>
        <div className={styles.page}>
          <div className={styles.headerGrid}>
            <header className={styles.headerBlock}>
              <h2 className={styles.title}>{t("Создать тест", "Тест құру")}</h2>
              <p className={styles.subtitle}>
                {t(
                  "Соберите собственный тест: тема, лимиты и вопросы с правильными ответами",
                  "Өз тестіңізді жасаңыз: тақырып, лимиттер және дұрыс жауаптары бар сұрақтар",
                )}
              </p>
            </header>
            <header className={styles.headerBlock}>
              <h2 className={styles.title}>{t("Для групп", "Топтар үшін")}</h2>
              <p className={styles.subtitle}>
                {t("Выберите группы, которым хотите добавить этот тест", "Бұл тестті қосқыңыз келетін топтарды таңдаңыз")}
              </p>
            </header>
          </div>

          {error && <p className={styles.error}>{error}</p>}
          {success && <p className={styles.success}>{success}</p>}

          <div className={styles.topGrid}>
            <section className={styles.heroPanel}>
              <label className={styles.heroLabel}>
                {t("Тема", "Тақырып")}
                <input
                  className={styles.heroInput}
                  placeholder={t("Например: Алгебра — степени", "Мысалы: Алгебра — дәреже")}
                  value={draft.title}
                  onChange={(event) =>
                    setDraft((prev) => ({
                      ...prev,
                      title: event.target.value,
                    }))
                  }
                  maxLength={160}
                />
              </label>

              <div className={styles.heroMetaGrid}>
                <label className={styles.heroLabel}>
                  {t("Длительность", "Ұзақтығы")}
                  <select
                    className={styles.heroInput}
                    value={draft.duration_minutes}
                    onChange={(event) =>
                      setDraft((prev) => ({
                        ...prev,
                        duration_minutes: Number(event.target.value),
                      }))
                    }
                  >
                    {DURATION_OPTIONS.map((value) => (
                      <option key={value} value={value}>
                        {value} {t("мин", "мин")}
                      </option>
                    ))}
                  </select>
                </label>

                <label className={styles.heroLabel}>
                  {t("Лимит предупреждений", "Ескерту лимиті")}
                  <select
                    className={styles.heroInput}
                    value={draft.warning_limit}
                    onChange={(event) =>
                      setDraft((prev) => ({
                        ...prev,
                        warning_limit: Number(event.target.value),
                      }))
                    }
                  >
                    {WARNING_OPTIONS.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </label>

                <label className={styles.heroLabel}>
                  {t("Срок сдачи", "Тапсыру мерзімі")}
                  <input
                    className={styles.heroInput}
                    type="date"
                    value={draft.due_date}
                    onChange={(event) =>
                      setDraft((prev) => ({
                        ...prev,
                        due_date: event.target.value,
                      }))
                    }
                  />
                </label>
              </div>

              <div className={styles.summaryBlock}>
                <h3 className={styles.heroSummaryTitle}>{t("Итого", "Қорытынды")}</h3>
                <div className={styles.heroStats}>
                  <article className={styles.statItem}>
                    <span>{t("Ваш тест распознан как", "Тест анықталды")}</span>
                    <strong>{difficultyLabel}</strong>
                  </article>
                  <article className={styles.statItem}>
                    <span>{t("Вопросов", "Сұрақтар")}</span>
                    <strong>{totalQuestions}</strong>
                  </article>
                  <article className={styles.statItem}>
                    <span>{t("Выбран для", "Таңдалған")}</span>
                    <strong>{groupSelectionLabel}</strong>
                  </article>
                </div>
              </div>

              <div className={styles.heroActions}>
                <button className={styles.createButton} disabled={submitting} onClick={() => void submitCustomTest()} type="button">
                  {submitting ? t("Создаем...", "Құрылуда...") : t("Создать тест", "Тест құру")}
                </button>
                <button className={styles.clearButton} onClick={clearDraft} type="button">
                  {t("Очистить форму", "Форманы тазалау")}
                </button>
              </div>
            </section>

            <aside className={styles.groupsAside}>
              {loadingGroups ? (
                <p className={styles.empty}>{t("Загрузка...", "Жүктелуде...")}</p>
              ) : groups.length === 0 ? (
                <p className={styles.empty}>
                  {t(
                    "У вас пока нет групп. Сначала создайте группу на странице «Группы».",
                    "Сізде әлі топ жоқ. Алдымен «Топтар» бетінде топ құрыңыз.",
                  )}
                </p>
              ) : (
                <div className={styles.groupsList}>
                  {groups.map((group) => {
                    const selected = selectedGroupIds.includes(group.id);
                    return (
                      <button
                        className={`${styles.groupCard} ${selected ? styles.groupCardActive : ""}`}
                        key={group.id}
                        onClick={() => toggleGroupSelection(group.id)}
                        type="button"
                      >
                        <img alt="" aria-hidden="true" className={styles.groupIcon} src={assetPaths.icons.group} />
                        <div className={styles.groupText}>
                          <h3>{group.name}</h3>
                          <p>
                            {group.members_count} {t("человек", "адам")}
                          </p>
                        </div>
                        <span className={`${styles.groupDot} ${selected ? styles.groupDotActive : ""}`} />
                      </button>
                    );
                  })}
                </div>
              )}
            </aside>
          </div>

          <section className={styles.questionsSection}>
            <h2 className={styles.questionsTitle}>{t("Вопросы и ответы", "Сұрақтар мен жауаптар")}</h2>

            <div className={styles.questionsList}>
              {draft.questions.map((question, index) => (
                <article className={styles.questionCard} key={question.id}>
                  <header className={styles.questionHeader}>
                    <div className={styles.questionHeaderLeft}>
                      <p className={styles.questionIndex}>{t("Вопрос", "Сұрақ")} {index + 1}</p>
                      <label className={styles.typeLabel}>
                        <span>{t("Тип", "Түрі")}:</span>
                        <select
                          className={styles.typeSelect}
                          value={question.answer_type}
                          onChange={(event) =>
                            updateQuestion(question.id, (prev) => ({
                              ...prev,
                              answer_type: event.target.value === "free_text" ? "free_text" : "choice",
                            }))
                          }
                        >
                          <option value="choice">{t("Варианты", "Нұсқалар")}</option>
                          <option value="free_text">{t("Свободный", "Еркін жауап")}</option>
                        </select>
                      </label>
                    </div>

                    <button
                      className={styles.deleteButton}
                      disabled={draft.questions.length <= 1}
                      onClick={() => removeQuestion(question.id)}
                      type="button"
                    >
                      <Trash2 size={18} />
                      <span>{t("Удалить", "Жою")}</span>
                    </button>
                  </header>

                  <textarea
                    className={styles.questionInput}
                    onChange={(event) =>
                      updateQuestion(question.id, (prev) => ({
                        ...prev,
                        prompt: event.target.value,
                      }))
                    }
                    placeholder={t("Введите формулировку вопроса", "Сұрақ тұжырымын енгізіңіз")}
                    rows={3}
                    value={question.prompt}
                  />

                  {question.answer_type === "choice" ? (
                    <div className={styles.choiceList}>
                      {question.options.map((option, optionIndex) => {
                        const isActive = question.correct_option_index === optionIndex;
                        return (
                          <label className={styles.choiceRow} key={`${question.id}-option-${optionIndex}`}>
                            <input
                              checked={isActive}
                              className={styles.choiceRadio}
                              name={`${question.id}-correct-option`}
                              onChange={() =>
                                updateQuestion(question.id, (prev) => ({
                                  ...prev,
                                  correct_option_index: optionIndex,
                                }))
                              }
                              type="radio"
                            />
                            <span className={`${styles.choiceDot} ${isActive ? styles.choiceDotActive : ""}`} />
                            <input
                              className={styles.choiceInput}
                              onChange={(event) =>
                                updateQuestion(question.id, (prev) => {
                                  const nextOptions = [...prev.options];
                                  nextOptions[optionIndex] = event.target.value;
                                  return {
                                    ...prev,
                                    options: nextOptions,
                                  };
                                })
                              }
                              placeholder={t(`Вариант ${optionIndex + 1}`, `Нұсқа ${optionIndex + 1}`)}
                              value={option}
                            />
                          </label>
                        );
                      })}

                      <button
                        className={styles.addOptionButton}
                        disabled={question.options.length >= 8}
                        onClick={() => addChoiceOption(question.id)}
                        type="button"
                      >
                        <Plus size={16} />
                        <span>{t("Добавить вариант", "Нұсқа қосу")}</span>
                      </button>
                    </div>
                  ) : (
                    <div className={styles.freeAnswerBlock}>
                      <p className={styles.freeAnswerTitle}>{t("Эталонный ответ", "Эталон жауап")}</p>
                      <textarea
                        className={styles.questionInput}
                        onChange={(event) =>
                          updateQuestion(question.id, (prev) => ({
                            ...prev,
                            sample_answer: event.target.value,
                          }))
                        }
                        placeholder={t(
                          "Введите ответ, с которым будет сравниваться ответ ученика.",
                          "Оқушы жауабымен салыстырылатын эталон жауапты енгізіңіз.",
                        )}
                        rows={4}
                        value={question.sample_answer}
                      />
                    </div>
                  )}
                </article>
              ))}
            </div>

            <button className={styles.addQuestionButton} onClick={addQuestion} type="button">
              <Plus size={20} />
              <span>{t("Добавить вопрос", "Сұрақ қосу")}</span>
            </button>
          </section>

          <footer className={styles.footer}>OKU.com.kz</footer>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
