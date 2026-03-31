"use client";

import { Plus, Trash2 } from "lucide-react";
import { Suspense, useEffect, useMemo, useState, type CSSProperties } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import {
  createTeacherCustomTest,
  generateTeacherCustomTestMaterial,
  getTeacherCustomTest,
  getTeacherGroups,
  parseTeacherCustomTestFile,
  updateTeacherCustomTest,
} from "@/lib/api";
import { getToken, getUser } from "@/lib/auth";
import { tr, useUiLanguage } from "@/lib/i18n";
import { toast } from "@/lib/toast";
import {
  Difficulty,
  TeacherCustomMaterialQuestion,
  TeacherCustomQuestion,
  TeacherCustomQuestionInput,
  TeacherCustomTestDetails,
  TeacherGroup,
} from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/app/teacher/create-test/create-test.module.css";

type AnswerType = "choice" | "free_text";
type CreateMode = "manual" | "ai" | "file";

interface DraftQuestion {
  id: string;
  prompt: string;
  answer_type: AnswerType;
  options: string[];
  correct_option_index: number | null;
  sample_answer: string;
  image_data_url?: string | null;
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
const AI_QUESTION_COUNT_OPTIONS = [5, 10, 15, 20, 25, 30];
const MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024;
const MAX_QUESTION_IMAGE_SIZE = 1 * 1024 * 1024;
const FILE_IMPORT_ALLOWED_EXTENSIONS = [".docx", ".csv"];

function normalizeGeneratedQuestion(question: TeacherCustomMaterialQuestion, index: number): DraftQuestion {
  const answerType: AnswerType = question.answer_type === "free_text" ? "free_text" : "choice";
  if (answerType === "free_text") {
    return {
      id: `ai-q-${index}-${Math.random().toString(36).slice(2, 8)}`,
      prompt: (question.prompt || "").trim(),
      answer_type: "free_text",
      options: ["", "", "", ""],
      correct_option_index: null,
      sample_answer: (question.sample_answer || "").trim(),
      image_data_url: (question.image_data_url || "").trim() || null,
    };
  }

  const options = Array.isArray(question.options)
    ? question.options.map((item) => (item || "").trim()).filter(Boolean).slice(0, 8)
    : [];
  while (options.length < 4) {
    options.push("");
  }
  const rawCorrectIndex = Number(question.correct_option_index ?? 0);
  const correctOptionIndex = Number.isFinite(rawCorrectIndex) && rawCorrectIndex >= 0 && rawCorrectIndex < options.length
    ? rawCorrectIndex
    : 0;

  return {
    id: `ai-q-${index}-${Math.random().toString(36).slice(2, 8)}`,
    prompt: (question.prompt || "").trim(),
    answer_type: "choice",
    options,
    correct_option_index: correctOptionIndex,
    sample_answer: "",
    image_data_url: (question.image_data_url || "").trim() || null,
  };
}

function createEmptyQuestion(seed = Date.now()): DraftQuestion {
  return {
    id: `q-${seed}-${Math.random().toString(36).slice(2, 8)}`,
    prompt: "",
    answer_type: "choice",
    options: ["", "", "", ""],
    correct_option_index: 0,
    sample_answer: "",
    image_data_url: null,
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
        image_data_url: typeof row.image_data_url === "string" ? row.image_data_url : null,
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

function draftFromCustomTestDetails(details: TeacherCustomTestDetails): DraftState {
  return {
    title: details.title,
    duration_minutes: details.duration_minutes,
    warning_limit: details.warning_limit,
    due_date: details.due_date || defaultDueDate(),
    questions: details.questions.map((question: TeacherCustomQuestion, index: number): DraftQuestion => {
      const answerType: AnswerType = question.answer_type === "free_text" ? "free_text" : "choice";
      if (answerType === "free_text") {
        return {
          id: `edit-q-${question.id}-${index}`,
          prompt: question.prompt || "",
          answer_type: "free_text",
          options: ["", "", "", ""],
          correct_option_index: null,
          sample_answer: question.sample_answer || "",
          image_data_url: question.image_data_url || null,
        };
      }

      const options = (question.options || []).map((item) => (item || "").trim()).filter(Boolean).slice(0, 8);
      while (options.length < 4) {
        options.push("");
      }
      const rawCorrectIndex = Number(question.correct_option_index ?? 0);
      const correctOptionIndex = Number.isFinite(rawCorrectIndex) && rawCorrectIndex >= 0 && rawCorrectIndex < options.length
        ? rawCorrectIndex
        : 0;

      return {
        id: `edit-q-${question.id}-${index}`,
        prompt: question.prompt || "",
        answer_type: "choice",
        options,
        correct_option_index: correctOptionIndex,
        sample_answer: "",
        image_data_url: question.image_data_url || null,
      };
    }),
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
        image_data_url: question.image_data_url || undefined,
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
      image_data_url: question.image_data_url || undefined,
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

function TeacherCreateTestPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);
  const editIdFromQuery = useMemo(() => {
    const raw = searchParams.get("edit");
    if (!raw) return null;
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }, [searchParams]);

  const [draft, setDraft] = useState<DraftState>(createInitialDraft);
  const [createMode, setCreateMode] = useState<CreateMode>("manual");
  const [aiDifficulty, setAiDifficulty] = useState<Difficulty>("medium");
  const [aiQuestionsCount, setAiQuestionsCount] = useState<number>(10);
  const [materialGenerated, setMaterialGenerated] = useState(false);
  const [generatingMaterial, setGeneratingMaterial] = useState(false);
  const [generationProgress, setGenerationProgress] = useState(0);
  const [selectedImportFile, setSelectedImportFile] = useState<File | null>(null);
  const [parsingImportFile, setParsingImportFile] = useState(false);
  const [parsedImportFilename, setParsedImportFilename] = useState<string>("");
  const [editingTestId, setEditingTestId] = useState<number | null>(editIdFromQuery);
  const [loadingEditDraft, setLoadingEditDraft] = useState(false);
  const [groups, setGroups] = useState<TeacherGroup[]>([]);
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([]);
  const [loadingGroups, setLoadingGroups] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [createdSuccessModalOpen, setCreatedSuccessModalOpen] = useState(false);
  const [successModalMode, setSuccessModalMode] = useState<"create" | "update">("create");

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

  const aiDifficultyLabel = useMemo(() => {
    if (aiDifficulty === "hard") return t("Сложный", "Күрделі");
    if (aiDifficulty === "medium") return t("Средний", "Орташа");
    return t("Легкий", "Жеңіл");
  }, [aiDifficulty, t]);

  const effectiveDifficultyLabel = createMode === "ai" ? aiDifficultyLabel : difficultyLabel;
  const createDisabled = loadingEditDraft || submitting || ((createMode === "ai" || createMode === "file") && !materialGenerated);
  const generationProgressStyle = {
    "--generation-progress": `${Math.max(0, Math.min(100, generationProgress))}%`,
  } as CSSProperties;

  useEffect(() => {
    setEditingTestId(editIdFromQuery);
  }, [editIdFromQuery]);

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
    const token = getToken();
    if (!token || !editingTestId) return;
    let cancelled = false;

    (async () => {
      try {
        setLoadingEditDraft(true);
        const details = await getTeacherCustomTest(token, editingTestId);
        if (cancelled) return;
        setDraft(draftFromCustomTestDetails(details));
        setSelectedGroupIds(details.groups.map((item) => Number(item.id)).filter((value) => Number.isFinite(value) && value > 0));
        setCreateMode("manual");
        setMaterialGenerated(true);
      } catch (requestError) {
        if (cancelled) return;
        toast.error(
          requestError instanceof Error
            ? requestError.message
            : t("Не удалось загрузить тест для редактирования.", "Өңдеуге арналған тестті жүктеу мүмкін болмады."),
        );
      } finally {
        if (!cancelled) {
          setLoadingEditDraft(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [editingTestId, t]);

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
    if (!generatingMaterial) {
      return;
    }
    setGenerationProgress(6);
    const timer = setInterval(() => {
      setGenerationProgress((prev) => {
        if (prev >= 92) return prev;
        const delta = Math.max(0.6, (92 - prev) * 0.08);
        return Math.min(92, Number((prev + delta).toFixed(1)));
      });
    }, 220);
    return () => {
      clearInterval(timer);
    };
  }, [generatingMaterial]);

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
        toast.error(
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
  }, []);

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
    setMaterialGenerated(false);
    setSelectedImportFile(null);
    setParsedImportFilename("");
    setCreatedSuccessModalOpen(false);
  };

  const setMode = (mode: CreateMode) => {
    setCreateMode(mode);
    if (mode === "manual") {
      return;
    }
    setMaterialGenerated(false);
    if (mode !== "file") {
      setSelectedImportFile(null);
      setParsedImportFilename("");
    }
  };

  const generateMaterial = async () => {
    const token = getToken();
    if (!token) return;

    const topic = draft.title.trim();
    if (!topic) {
      toast.error(t("Введите тему.", "Тақырыпты енгізіңіз."));
      return;
    }

    setGenerationProgress(0);
    setGeneratingMaterial(true);

    try {
      const payload = await generateTeacherCustomTestMaterial(token, {
        topic,
        difficulty: aiDifficulty,
        questions_count: aiQuestionsCount,
        language: uiLanguage === "KZ" ? "KZ" : "RU",
      });

      const mappedQuestions = payload.questions.map((item, index) => normalizeGeneratedQuestion(item, index));
      if (mappedQuestions.length === 0) {
        toast.error(t("Материал не сгенерирован.", "Материал генерацияланбады."));
        setMaterialGenerated(false);
        return;
      }

      setDraft((prev) => ({
        ...prev,
        title: payload.topic,
        questions: mappedQuestions,
      }));
      setMaterialGenerated(true);
      setGenerationProgress(100);
      toast.success(
        t(
          `Материал готов: ${mappedQuestions.length} вопросов.`,
          `Материал дайын: ${mappedQuestions.length} сұрақ.`,
        ),
      );
    } catch (requestError) {
      setMaterialGenerated(false);
      setGenerationProgress(0);
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : t("Не удалось сгенерировать материал.", "Материалды генерациялау мүмкін болмады."),
      );
    } finally {
      setGeneratingMaterial(false);
      setTimeout(() => {
        setGenerationProgress(0);
      }, 250);
    }
  };

  const parseFileMaterial = async () => {
    const token = getToken();
    if (!token) return;

    if (!selectedImportFile) {
      toast.error(t("Прикрепите файл.", "Файлды тіркеңіз."));
      return;
    }

    setParsingImportFile(true);
    try {
      const payload = await parseTeacherCustomTestFile(token, selectedImportFile);
      const mappedQuestions = payload.questions.map((item, index) => normalizeGeneratedQuestion(item, index));
      if (mappedQuestions.length === 0) {
        throw new Error(t("Файл не содержит корректных вопросов.", "Файлда дұрыс сұрақтар жоқ."));
      }

      const fallbackTitle = selectedImportFile.name.replace(/\.[^.]+$/, "").trim();
      setDraft((prev) => ({
        ...prev,
        title: prev.title.trim() || fallbackTitle,
        questions: mappedQuestions,
      }));
      setMaterialGenerated(true);
      setParsedImportFilename(payload.source_filename || selectedImportFile.name);
      toast.success(
        t(
          `Файл обработан: ${mappedQuestions.length} вопросов.`,
          `Файл өңделді: ${mappedQuestions.length} сұрақ.`,
        ),
      );
    } catch (requestError) {
      setMaterialGenerated(false);
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : t("Не удалось преобразовать файл.", "Файлды түрлендіру мүмкін болмады."),
      );
    } finally {
      setParsingImportFile(false);
    }
  };

  const handleImportFileChange = (nextFile: File | null) => {
    if (!nextFile) {
      setSelectedImportFile(null);
      setParsedImportFilename("");
      setMaterialGenerated(false);
      return;
    }

    const normalizedName = nextFile.name.trim().toLowerCase();
    const hasAllowedExtension = FILE_IMPORT_ALLOWED_EXTENSIONS.some((ext) => normalizedName.endsWith(ext));
    if (!hasAllowedExtension) {
      toast.error(t("Только .docx и .csv.", "Тек .docx және .csv."));
      setSelectedImportFile(null);
      setMaterialGenerated(false);
      return;
    }
    if (nextFile.size > MAX_IMPORT_FILE_SIZE) {
      toast.error(t("Файл больше 5MB.", "Файл 5MB-тан үлкен."));
      setSelectedImportFile(null);
      setMaterialGenerated(false);
      return;
    }

    setSelectedImportFile(nextFile);
    setParsedImportFilename("");
    setMaterialGenerated(false);
  };

  const handleQuestionImageChange = (questionId: string, nextFile: File | null) => {
    if (!nextFile) {
      return;
    }
    const normalizedType = (nextFile.type || "").toLowerCase();
    if (!normalizedType.startsWith("image/")) {
      toast.error(t("Только изображение.", "Тек сурет файлы."));
      return;
    }
    if (nextFile.size > MAX_QUESTION_IMAGE_SIZE) {
      toast.error(t("Изображение больше 1MB.", "Сурет 1MB-тан үлкен."));
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const value = typeof reader.result === "string" ? reader.result : "";
      if (!value) {
        toast.error(t("Не удалось прочитать изображение.", "Суретті оқу мүмкін болмады."));
        return;
      }
      updateQuestion(questionId, (prev) => ({
        ...prev,
        image_data_url: value,
      }));
    };
    reader.onerror = () => {
      toast.error(t("Не удалось прочитать изображение.", "Суретті оқу мүмкін болмады."));
    };
    reader.readAsDataURL(nextFile);
  };

  const submitCustomTest = async () => {
    const token = getToken();
    if (!token) return;

    const normalizedTitle = draft.title.trim();
    if (!normalizedTitle) {
      toast.error(t("Введите тему.", "Тақырыпты енгізіңіз."));
      return;
    }

    if (createMode === "ai" && !materialGenerated) {
      toast.error(
        t(
          "Подготовьте материал.",
          "Материалды дайындаңыз.",
        ),
      );
      return;
    }

    const allowedGroupIds = new Set(groups.map((group) => group.id));
    const selectedExistingGroupIds = selectedGroupIds.filter((groupId) => allowedGroupIds.has(groupId));
    if (selectedExistingGroupIds.length !== selectedGroupIds.length) {
      setSelectedGroupIds(selectedExistingGroupIds);
    }

    let payloadQuestions: TeacherCustomQuestionInput[];
    try {
      payloadQuestions = buildPayloadQuestions(draft.questions, t);
    } catch (validationError) {
      toast.error(validationError instanceof Error ? validationError.message : t("Проверьте вопросы.", "Сұрақтарды тексеріңіз."));
      return;
    }

    try {
      setSubmitting(true);
      const requestPayload = {
        title: normalizedTitle,
        duration_minutes: draft.duration_minutes,
        warning_limit: draft.warning_limit,
        due_date: draft.due_date || null,
        group_ids: selectedExistingGroupIds,
        questions: payloadQuestions,
      };
      if (editingTestId) {
        await updateTeacherCustomTest(token, editingTestId, requestPayload);
        setSuccessModalMode("update");
      } else {
        await createTeacherCustomTest(token, requestPayload);
        setSuccessModalMode("create");
      }

      const key = toDraftStorageKey();
      if (key) {
        try {
          localStorage.removeItem(key);
        } catch {
          // ignore localStorage quota errors
        }
      }
      setDraft(createInitialDraft());
      setSelectedGroupIds([]);
      if (editingTestId) {
        setEditingTestId(null);
        router.replace("/teacher/create-test");
      }
      setCreatedSuccessModalOpen(true);
    } catch (requestError) {
      toast.error(
        requestError instanceof Error
          ? requestError.message
          : editingTestId
            ? t("Не удалось обновить тест.", "Тестті жаңарту мүмкін болмады.")
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
          <div className={styles.topGrid}>
            <section className={styles.topColumn}>
              <header className={styles.headerBlock}>
                <h2 className={styles.title}>
                  {editingTestId ? t("Редактировать тест", "Тестті өңдеу") : t("Создать тест", "Тест құру")}
                </h2>
                <p className={styles.subtitle}>
                  {t(
                    "Соберите собственный тест: тема, лимиты и вопросы с правильными ответами",
                    "Өз тестіңізді жасаңыз: тақырып, лимиттер және дұрыс жауаптары бар сұрақтар",
                  )}
                </p>
                {loadingEditDraft ? (
                  <p className={styles.subtitle}>
                    {t("Загружаем данные теста...", "Тест деректері жүктелуде...")}
                  </p>
                ) : null}
              </header>

              <section className={styles.heroPanel}>
                <div className={styles.modeSwitch} role="tablist" aria-label={t("Режим создания теста", "Тест құру режимі")}>
                  <span
                    className={`${styles.modeSwitchIndicator} ${
                      createMode === "manual"
                        ? styles.modeSwitchIndicatorLeft
                        : createMode === "ai"
                          ? styles.modeSwitchIndicatorMiddle
                          : styles.modeSwitchIndicatorRight
                    }`}
                    aria-hidden="true"
                  />
                  <button
                    className={`${styles.modeSwitchButton} ${createMode === "manual" ? styles.modeSwitchButtonActive : ""}`}
                    onClick={() => setMode("manual")}
                    type="button"
                  >
                    {t("Создать вручную", "Қолмен құру")}
                  </button>
                  <button
                    className={`${styles.modeSwitchButton} ${createMode === "ai" ? styles.modeSwitchButtonActive : ""}`}
                    onClick={() => setMode("ai")}
                    type="button"
                  >
                    {t("Создать с AI", "AI арқылы құру")}
                  </button>
                  <button
                    className={`${styles.modeSwitchButton} ${createMode === "file" ? styles.modeSwitchButtonActive : ""}`}
                    onClick={() => setMode("file")}
                    type="button"
                  >
                    {t("Создать из файла", "Файлдан құру")}
                  </button>
                </div>

                <div key={createMode} className={styles.modeContent}>
                  {createMode === "ai" ? (
                    <>
                      <p className={styles.aiHint}>
                        {t(
                          "Настройте ключевые параметры: AI сгенерирует вопросы и варианты ответов по теме.",
                          "Негізгі параметрлерді орнатыңыз: AI тақырып бойынша сұрақтар мен жауап нұсқаларын жасайды.",
                        )}
                      </p>

                      <label className={styles.heroLabel}>
                        {t("Тема", "Тақырып")}
                        <input
                          className={styles.heroInput}
                          placeholder={t("Например: Алгебра — степени", "Мысалы: Алгебра — дәреже")}
                          value={draft.title}
                          onChange={(event) => {
                            setDraft((prev) => ({
                              ...prev,
                              title: event.target.value,
                            }));
                            setMaterialGenerated(false);
                          }}
                          maxLength={160}
                        />
                      </label>

                      <div className={styles.aiMetaGrid}>
                        <label className={styles.heroLabel}>
                          {t("Сложность", "Күрделілік")}
                          <select
                            className={`${styles.heroInput} ${styles.heroSelect}`}
                            value={aiDifficulty}
                            onChange={(event) => {
                              setAiDifficulty(event.target.value as Difficulty);
                              setMaterialGenerated(false);
                            }}
                          >
                            <option value="easy">{t("Легкий", "Жеңіл")}</option>
                            <option value="medium">{t("Средний", "Орташа")}</option>
                            <option value="hard">{t("Сложный", "Күрделі")}</option>
                          </select>
                        </label>

                        <label className={styles.heroLabel}>
                          {t("Количество вопросов", "Сұрақ саны")}
                          <select
                            className={`${styles.heroInput} ${styles.heroSelect}`}
                            value={aiQuestionsCount}
                            onChange={(event) => {
                              setAiQuestionsCount(Number(event.target.value));
                              setMaterialGenerated(false);
                            }}
                          >
                            {AI_QUESTION_COUNT_OPTIONS.map((value) => (
                              <option key={value} value={value}>
                                {value}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>

                      <div
                        className={`${styles.generateButtonProgress} ${generatingMaterial ? styles.generateButtonProgressActive : ""}`}
                        style={generationProgressStyle}
                      >
                        <button
                          className={styles.generateButton}
                          disabled={generatingMaterial}
                          onClick={() => void generateMaterial()}
                          type="button"
                        >
                          <img alt="" aria-hidden="true" src={assetPaths.icons.aiGenerate} />
                          <span>
                            {generatingMaterial
                              ? t("Генерируем материал...", "Материал жасалып жатыр...")
                              : t("Сгенерировать материал", "Материалды генерациялау")}
                          </span>
                        </button>
                      </div>
                    </>
                  ) : createMode === "file" ? (
                    <>
                      <p className={styles.aiHint}>
                        {t(
                          "Прикрепите шаблонный файл .docx или .csv с вопросами. Размер файла до 5MB.",
                          "Сұрақтары бар .docx немесе .csv шаблон файлын тіркеңіз. Файл көлемі 5MB-қа дейін.",
                        )}
                      </p>

                      <label className={styles.fileUploadArea}>
                        <input
                          accept=".docx,.csv"
                          className={styles.fileInput}
                          onChange={(event) => handleImportFileChange(event.target.files?.[0] ?? null)}
                          type="file"
                        />
                        <img alt="" aria-hidden="true" src={assetPaths.icons.attachFile} />
                        <div className={styles.fileUploadText}>
                          <strong>
                            {selectedImportFile
                              ? selectedImportFile.name
                              : t("Прикрепить файл", "Файлды тіркеу")}
                          </strong>
                          <span>{t("до 5MB", "5MB дейін")}</span>
                        </div>
                      </label>

                      <button
                        className={`${styles.generateButton} ${styles.generateButtonSolid}`}
                        disabled={parsingImportFile || !selectedImportFile}
                        onClick={() => void parseFileMaterial()}
                        type="button"
                      >
                        <img alt="" aria-hidden="true" src={assetPaths.icons.aiGenerate} />
                        <span>
                          {parsingImportFile
                            ? t("Преобразуем файл...", "Файл түрлендірілуде...")
                            : t("Преобразовать файл", "Файлды түрлендіру")}
                        </span>
                      </button>
                      {parsedImportFilename ? (
                        <p className={styles.aiHint}>
                          {t("Файл обработан:", "Файл өңделді:")} {parsedImportFilename}
                        </p>
                      ) : null}
                    </>
                  ) : (
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
                  )}
                </div>

                <div className={`${styles.heroDivider} ${createMode !== "manual" ? styles.heroDividerVisible : ""}`} />

                <div className={styles.heroMetaGrid}>
                  <label className={styles.heroLabel}>
                    {t("Длительность", "Ұзақтығы")}
                    <select
                      className={`${styles.heroInput} ${styles.heroSelect}`}
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
                      className={`${styles.heroInput} ${styles.heroSelect}`}
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
                    <div className={styles.dateInputWrap}>
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
                    </div>
                  </label>
                </div>

                <div className={styles.summaryBlock}>
                  <h3 className={styles.heroSummaryTitle}>{t("Итого", "Қорытынды")}</h3>
                  <div className={styles.heroStats}>
                    <article className={styles.statItem}>
                      <span>{t("Ваш тест распознан как", "Тест анықталды")}</span>
                      <strong>{effectiveDifficultyLabel}</strong>
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
                  <button className={styles.createButton} disabled={createDisabled} onClick={() => void submitCustomTest()} type="button">
                    {submitting
                      ? editingTestId
                        ? t("Сохраняем...", "Сақталуда...")
                        : t("Создаем...", "Құрылуда...")
                      : (createMode === "ai" || createMode === "file") && !materialGenerated
                        ? t("Подготовьте материал", "Материалды дайындаңыз")
                        : editingTestId
                          ? t("Сохранить тест", "Тестті сақтау")
                          : t("Создать тест", "Тест құру")}
                  </button>
                  <button className={styles.clearButton} onClick={clearDraft} type="button">
                    {t("Очистить форму", "Форманы тазалау")}
                  </button>
                </div>
              </section>
            </section>

            <section className={styles.topColumn}>
              <header className={styles.headerBlock}>
                <h2 className={styles.title}>{t("Для групп", "Топтар үшін")}</h2>
                <p className={styles.subtitle}>
                  {t("Выберите группы, которым хотите добавить этот тест", "Бұл тестті қосқыңыз келетін топтарды таңдаңыз")}
                </p>
              </header>

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
            </section>
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

                  {question.image_data_url ? (
                    <div className={styles.questionImagePreview}>
                      <img alt={t("Иллюстрация к вопросу", "Сұрақ иллюстрациясы")} src={question.image_data_url} />
                      <button
                        className={styles.removeImageButton}
                        onClick={() =>
                          updateQuestion(question.id, (prev) => ({
                            ...prev,
                            image_data_url: null,
                          }))
                        }
                        type="button"
                      >
                        {t("Удалить фото", "Фотоны жою")}
                      </button>
                    </div>
                  ) : (
                    <label className={styles.questionImageUpload}>
                      <input
                        accept="image/*"
                        className={styles.fileInput}
                        onChange={(event) => {
                          handleQuestionImageChange(question.id, event.target.files?.[0] ?? null);
                          event.currentTarget.value = "";
                        }}
                        type="file"
                      />
                      <img alt="" aria-hidden="true" src={assetPaths.icons.attachFile} />
                      <div className={`${styles.fileUploadText} ${styles.questionUploadText}`}>
                        <strong>{t("Прикрепить фото", "Фото тіркеу")}</strong>
                        <span>{t("до 1MB", "1MB дейін")}</span>
                      </div>
                    </label>
                  )}

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

          <footer className={styles.footer}>oku.com.kz</footer>
        </div>
        {createdSuccessModalOpen ? (
          <div
            className={styles.successOverlay}
            role="dialog"
            aria-modal="true"
            aria-label={successModalMode === "update" ? t("Тест успешно обновлён", "Тест сәтті жаңартылды") : t("Тест успешно создан", "Тест сәтті құрылды")}
          >
            <div className={styles.successModal}>
              <img alt="" aria-hidden="true" className={styles.successModalIcon} src={assetPaths.icons.testCreated} />
              <p className={styles.successModalTitle}>
                {successModalMode === "update"
                  ? t("Тест успешно обновлён", "Тест сәтті жаңартылды")
                  : t("Тест успешно создан", "Тест сәтті құрылды")}
              </p>
              <button
                className={styles.successModalButton}
                onClick={() => {
                  setCreatedSuccessModalOpen(false);
                  router.push("/teacher/tests");
                }}
                type="button"
              >
                {t("Продолжить", "Жалғастыру")}
              </button>
            </div>
          </div>
        ) : null}
      </AppShell>
    </AuthGuard>
  );
}

export default function TeacherCreateTestPage() {
  return (
    <Suspense fallback={null}>
      <TeacherCreateTestPageContent />
    </Suspense>
  );
}
