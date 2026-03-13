"use client";

import { Mic, Square, Volume2, VolumeX } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import ProgressBar from "@/components/ui/ProgressBar";
import { getQuestionTtsAudio, getTest, submitTest } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { tr, useUiLanguage } from "@/lib/i18n";
import { Language, OptionItem, Question, Test } from "@/lib/types";
import styles from "@/app/test/[id]/runner.module.css";

interface AnswerMap {
  [questionId: number]: Record<string, unknown>;
}

interface TestIntegrityWarning {
  type: string;
  at_seconds: number;
  question_id?: number | null;
  details?: Record<string, unknown>;
}

interface SpeechRecognitionResultLike {
  isFinal: boolean;
  length: number;
  [index: number]: {
    transcript: string;
    confidence: number;
  };
}

interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}

interface SpeechRecognitionErrorEventLike extends Event {
  error?: string;
  message?: string;
}

interface SpeechRecognitionInstanceLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: ((event: Event) => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: ((event: Event) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionInstanceLike;

interface OralAnswerControls {
  supported: boolean;
  listening: boolean;
  activeQuestionId: number | null;
  error: string;
  onStart: (question: Question) => void;
  onStop: () => void;
}

interface PersistedTestSession {
  version: 1;
  test_id: number;
  started_at_ms: number;
  current_index: number;
  answers: AnswerMap;
  integrity_warnings: TestIntegrityWarning[];
}

const TEST_SESSION_STORAGE_PREFIX = "oku-test-session:";
const WARNING_EVENT_COOLDOWN_MS = 1000;
const WARNING_EVENT_FAMILIES: Record<string, string> = {
  focus_lost: "environment_change",
  suspicious_viewport_resize: "environment_change",
  inspector_open_attempt: "environment_change",
  paste_detected: "paste_input",
  paste_shortcut: "paste_input",
};

export default function TestRunnerPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const testId = Number(params.id);
  const uiLanguage = useUiLanguage();
  const t = useCallback((ru: string, kz: string) => tr(uiLanguage, ru, kz), [uiLanguage]);

  const [test, setTest] = useState<Test | null>(null);
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [audioPlaying, setAudioPlaying] = useState(false);
  const [audioLoading, setAudioLoading] = useState(false);
  const [audioError, setAudioError] = useState("");
  const [oralSupported, setOralSupported] = useState(false);
  const [oralListening, setOralListening] = useState(false);
  const [oralError, setOralError] = useState("");
  const [oralQuestionId, setOralQuestionId] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [integrityWarnings, setIntegrityWarnings] = useState<TestIntegrityWarning[]>([]);
  const [sessionHydrated, setSessionHydrated] = useState(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const audioElementRef = useRef<HTMLAudioElement | null>(null);
  const audioObjectUrlRef = useRef<string | null>(null);
  const speechRecognitionRef = useRef<SpeechRecognitionInstanceLike | null>(null);
  const speechPrefixRef = useRef("");
  const speechQuestionIdRef = useRef<number | null>(null);
  const ttsRequestIdRef = useRef(0);
  const elapsedRef = useRef(0);
  const warningsRef = useRef<TestIntegrityWarning[]>([]);
  const textFocusAtRef = useRef<Record<number, number>>({});
  const fastInputFlagRef = useRef<Record<number, boolean>>({});
  const lastFocusLossWarningAtRef = useRef(0);
  const pasteShortcutAtRef = useRef<Record<number, number>>({});
  const pasteEventAtRef = useRef<Record<number, number>>({});
  const pasteShortcutTimerRef = useRef<Record<number, number>>({});
  const baselineViewportRef = useRef<{ width: number; height: number } | null>(null);
  const lastResizeWarningAtRef = useRef(0);
  const lastInspectorWarningAtRef = useRef(0);
  const lastWarningAtByFamilyRef = useRef<Record<string, number>>({});
  const startedAtMsRef = useRef<number | null>(null);
  const autoSubmittedRef = useRef(false);

  useEffect(() => {
    const token = getToken();
    if (!token || Number.isNaN(testId)) return;

    getTest(token, testId)
      .then((payload) => setTest(payload))
      .catch((err) => setError(err instanceof Error ? err.message : t("Не удалось загрузить тест", "Тестті жүктеу мүмкін болмады")))
      .finally(() => setLoading(false));
  }, [testId, uiLanguage]);

  useEffect(() => {
    setOralSupported(Boolean(getSpeechRecognitionCtor()));
  }, []);

  const question = test?.questions[currentIndex] || null;
  const total = test?.questions.length || 0;
  const progress = total > 0 ? ((currentIndex + 1) / total) * 100 : 0;
  const timeLimitSeconds = test?.time_limit_seconds ?? null;
  const warningLimit = test?.warning_limit ?? null;
  const remainingSeconds = timeLimitSeconds !== null ? Math.max(timeLimitSeconds - elapsedSeconds, 0) : null;
  const isTimeLimitReached = timeLimitSeconds !== null && elapsedSeconds >= timeLimitSeconds;
  const isWarningLimitReached = warningLimit !== null && integrityWarnings.length >= warningLimit;

  const answerForCurrent = useMemo(() => {
    if (!question) return {};
    return answers[question.id] || {};
  }, [answers, question]);

  const addIntegrityWarning = useCallback(
    (event: Omit<TestIntegrityWarning, "at_seconds"> & { at_seconds?: number }) => {
      const next: TestIntegrityWarning = {
        type: event.type,
        at_seconds: event.at_seconds ?? elapsedRef.current,
        question_id: event.question_id ?? null,
        details: event.details || {},
      };
      const family = WARNING_EVENT_FAMILIES[next.type] || next.type;
      const now = Date.now();
      const lastWarningAt = lastWarningAtByFamilyRef.current[family] || 0;
      if (now - lastWarningAt < WARNING_EVENT_COOLDOWN_MS) return;

      const signature = `${next.type}|${next.question_id ?? "none"}|${next.at_seconds}`;
      const exists = warningsRef.current.some(
        (item) => `${item.type}|${item.question_id ?? "none"}|${item.at_seconds}` === signature,
      );
      if (exists) return;

      lastWarningAtByFamilyRef.current[family] = now;
      const merged = [...warningsRef.current, next];
      warningsRef.current = merged;
      setIntegrityWarnings(merged);
    },
    [],
  );

  useEffect(() => {
    if (!test) return;
    setSessionHydrated(false);

    const validQuestionIds = new Set(test.questions.map((item) => item.id));
    const persisted = loadPersistedTestSession(test.id);
    const persistedAnswers = persisted?.answers || {};
    const hydratedAnswers = Object.fromEntries(
      Object.entries(persistedAnswers).filter(([questionId]) => validQuestionIds.has(Number(questionId))),
    ) as AnswerMap;
    const hydratedWarnings = (persisted?.integrity_warnings || []).filter((item) =>
      item.question_id === null || item.question_id === undefined || validQuestionIds.has(item.question_id),
    );
    const startedAtMs =
      persisted && Number.isFinite(persisted.started_at_ms) && persisted.started_at_ms > 0
        ? persisted.started_at_ms
        : Date.now();
    const maxIndex = Math.max(0, test.questions.length - 1);
    const hydratedIndex = Math.min(Math.max(persisted?.current_index ?? 0, 0), maxIndex);
    const hydratedElapsed = Math.max(0, Math.floor((Date.now() - startedAtMs) / 1000));

    startedAtMsRef.current = startedAtMs;
    setAnswers(hydratedAnswers);
    setCurrentIndex(hydratedIndex);
    setElapsedSeconds(hydratedElapsed);
    elapsedRef.current = hydratedElapsed;
    setIntegrityWarnings(hydratedWarnings);
    warningsRef.current = hydratedWarnings;
    textFocusAtRef.current = {};
    fastInputFlagRef.current = {};
    lastFocusLossWarningAtRef.current = 0;
    pasteShortcutAtRef.current = {};
    pasteEventAtRef.current = {};
    const activePasteTimers = Object.values(pasteShortcutTimerRef.current);
    activePasteTimers.forEach((timerId) => window.clearTimeout(timerId));
    pasteShortcutTimerRef.current = {};
    baselineViewportRef.current = null;
    lastResizeWarningAtRef.current = 0;
    lastInspectorWarningAtRef.current = 0;
    lastWarningAtByFamilyRef.current = {};
    autoSubmittedRef.current = false;

    if (!persisted) {
      persistTestSession({
        version: 1,
        test_id: test.id,
        started_at_ms: startedAtMs,
        current_index: hydratedIndex,
        answers: hydratedAnswers,
        integrity_warnings: hydratedWarnings,
      });
    }

    setSessionHydrated(true);

    const interval = window.setInterval(() => {
      if (!startedAtMsRef.current) return;
      const nextElapsed = Math.max(0, Math.floor((Date.now() - startedAtMsRef.current) / 1000));
      elapsedRef.current = nextElapsed;
      setElapsedSeconds(nextElapsed);
    }, 1000);
    return () => window.clearInterval(interval);
  }, [test]);

  useEffect(() => {
    if (!test || !startedAtMsRef.current || !sessionHydrated) return;

    persistTestSession({
      version: 1,
      test_id: test.id,
      started_at_ms: startedAtMsRef.current,
      current_index: currentIndex,
      answers,
      integrity_warnings: integrityWarnings,
    });
  }, [answers, currentIndex, elapsedSeconds, integrityWarnings, sessionHydrated, test]);

  useEffect(() => {
    if (!test) return;

    const registerFocusLossWarning = (source: string) => {
      const now = Date.now();
      if (now - lastFocusLossWarningAtRef.current < 1500) return;
      lastFocusLossWarningAtRef.current = now;
      addIntegrityWarning({
        type: "focus_lost",
        details: { source },
      });
    };

    const onVisibilityChange = () => {
      if (!document.hidden) return;
      registerFocusLossWarning("visibilitychange");
    };

    const onWindowBlur = () => {
      if (document.hidden) return;
      registerFocusLossWarning("window_blur");
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("blur", onWindowBlur);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("blur", onWindowBlur);
    };
  }, [addIntegrityWarning, test]);

  useEffect(() => {
    if (!test || typeof window === "undefined") return;

    baselineViewportRef.current = {
      width: window.innerWidth,
      height: window.innerHeight,
    };

    const maybeWarnSuspiciousResize = (source: "resize" | "interval") => {
      const baseline = baselineViewportRef.current;
      if (!baseline) return;

      const currentWidth = window.innerWidth;
      const currentHeight = window.innerHeight;
      const widthDelta = Math.abs(currentWidth - baseline.width);
      const heightDelta = Math.abs(currentHeight - baseline.height);
      const widthRatio = widthDelta / Math.max(1, baseline.width);
      const heightRatio = heightDelta / Math.max(1, baseline.height);
      const now = Date.now();

      const suspiciousViewportResize =
        (widthDelta >= 220 && widthRatio >= 0.28) ||
        (heightDelta >= 220 && heightRatio >= 0.32);
      if (suspiciousViewportResize && now - lastResizeWarningAtRef.current >= 4000) {
        lastResizeWarningAtRef.current = now;
        addIntegrityWarning({
          type: "suspicious_viewport_resize",
          details: {
            source,
            baseline_width: baseline.width,
            baseline_height: baseline.height,
            current_width: currentWidth,
            current_height: currentHeight,
            width_delta: widthDelta,
            height_delta: heightDelta,
          },
        });
      }

      const isDesktop = currentWidth >= 900 && currentHeight >= 600;
      if (!isDesktop) return;

      const widthGap = Math.max(0, window.outerWidth - currentWidth);
      const heightGap = Math.max(0, window.outerHeight - currentHeight);
      const inspectorLikelyOpen = widthGap >= 170 || heightGap >= 170;
      if (inspectorLikelyOpen && now - lastInspectorWarningAtRef.current >= 4000) {
        lastInspectorWarningAtRef.current = now;
        addIntegrityWarning({
          type: "inspector_open_attempt",
          details: {
            source,
            outer_width: window.outerWidth,
            outer_height: window.outerHeight,
            inner_width: currentWidth,
            inner_height: currentHeight,
            width_gap: widthGap,
            height_gap: heightGap,
          },
        });
      }
    };

    const onResize = () => maybeWarnSuspiciousResize("resize");
    const intervalId = window.setInterval(() => maybeWarnSuspiciousResize("interval"), 2200);
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      window.clearInterval(intervalId);
    };
  }, [addIntegrityWarning, test]);

  const updateAnswer = useCallback((questionId: number, value: Record<string, unknown>) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  }, []);

  const toggleMulti = useCallback(
    (questionId: number, optionId: number) => {
      const selected = (answers[questionId]?.selected_option_ids as number[] | undefined) || [];
      const next = selected.includes(optionId) ? selected.filter((id) => id !== optionId) : [...selected, optionId];
      updateAnswer(questionId, { selected_option_ids: next });
    },
    [answers, updateAnswer],
  );

  const updateMatching = useCallback(
    (questionId: number, left: string, right: string) => {
      const existing = (answers[questionId]?.matches as Record<string, string> | undefined) || {};
      updateAnswer(questionId, { matches: { ...existing, [left]: right } });
    },
    [answers, updateAnswer],
  );

  const stopOralRecognition = useCallback((abort = false) => {
    const recognition = speechRecognitionRef.current;
    if (!recognition) return;

    recognition.onstart = null;
    recognition.onresult = null;
    recognition.onerror = null;
    recognition.onend = null;
    try {
      if (abort) {
        recognition.abort();
      } else {
        recognition.stop();
      }
    } catch {
      // ignore speech recognition stop errors
    }

    speechRecognitionRef.current = null;
    speechQuestionIdRef.current = null;
    setOralListening(false);
    setOralQuestionId(null);
  }, []);

  const startOralRecognition = useCallback(
    (targetQuestion: Question) => {
      if (targetQuestion.type !== "oral_answer") return;
      const SpeechRecognitionCtorValue = getSpeechRecognitionCtor();
      if (!SpeechRecognitionCtorValue) {
        setOralError(t("Распознавание речи недоступно в этом браузере. Введите ответ вручную.", "Бұл браузерде дауысты тану қолжетімсіз. Жауапты қолмен енгізіңіз."));
        return;
      }

      setOralError("");
      stopOralRecognition(true);

      const answer = answers[targetQuestion.id] || {};
      speechPrefixRef.current = String(answer.spoken_answer_text || "").trim();
      speechQuestionIdRef.current = targetQuestion.id;

      const recognition = new SpeechRecognitionCtorValue();
      recognition.lang = test?.language === "KZ" ? "kk-KZ" : "ru-RU";
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        setOralListening(true);
        setOralQuestionId(targetQuestion.id);
      };

      recognition.onresult = (event) => {
        const activeQuestionId = speechQuestionIdRef.current;
        if (!activeQuestionId) return;

        const finalSegments: string[] = [];
        const interimSegments: string[] = [];
        for (let idx = 0; idx < event.results.length; idx += 1) {
          const result = event.results[idx];
          if (!result || !result.length) continue;
          const transcript = normalizeSpokenText(result[0]?.transcript || "");
          if (!transcript) continue;
          if (result.isFinal) {
            finalSegments.push(transcript);
          } else {
            interimSegments.push(transcript);
          }
        }

        const fullText = normalizeSpokenText(
          [speechPrefixRef.current, finalSegments.join(" "), interimSegments.join(" ")]
            .filter(Boolean)
            .join(" "),
        );
        updateAnswer(activeQuestionId, { spoken_answer_text: fullText });
      };

      recognition.onerror = (event) => {
        const message = getSpeechRecognitionErrorMessage(event.error, uiLanguage);
        if (message) {
          setOralError(message);
        }
        setOralListening(false);
        setOralQuestionId(null);
        speechRecognitionRef.current = null;
        speechQuestionIdRef.current = null;
      };

      recognition.onend = () => {
        setOralListening(false);
        setOralQuestionId(null);
        speechRecognitionRef.current = null;
        speechQuestionIdRef.current = null;
      };

      speechRecognitionRef.current = recognition;
      try {
        recognition.start();
      } catch (err) {
        setOralError(err instanceof Error ? err.message : t("Не удалось запустить распознавание речи.", "Дауысты тануды іске қосу мүмкін болмады."));
        setOralListening(false);
        setOralQuestionId(null);
        speechRecognitionRef.current = null;
        speechQuestionIdRef.current = null;
      }
    },
    [answers, stopOralRecognition, t, test?.language, uiLanguage, updateAnswer],
  );

  const stopAudio = useCallback(() => {
    ttsRequestIdRef.current += 1;

    if (audioElementRef.current) {
      audioElementRef.current.onplay = null;
      audioElementRef.current.onended = null;
      audioElementRef.current.onerror = null;
      audioElementRef.current.pause();
      audioElementRef.current.src = "";
      audioElementRef.current = null;
    }
    if (audioObjectUrlRef.current && typeof window !== "undefined") {
      URL.revokeObjectURL(audioObjectUrlRef.current);
      audioObjectUrlRef.current = null;
    }

    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    utteranceRef.current = null;
    setAudioLoading(false);
    setAudioPlaying(false);
  }, []);

  const speakWithBrowserTTS = useCallback(
    (targetQuestion: Question, fallbackMessage?: string) => {
      if (typeof window === "undefined" || !("speechSynthesis" in window)) {
        setAudioError(t("На этом устройстве озвучка недоступна.", "Бұл құрылғыда дыбыстау қолжетімсіз."));
        return;
      }

      const text = buildAudioNarration(targetQuestion, test?.language || "RU");
      if (!text) return;

      setAudioError(fallbackMessage || "");
      const synth = window.speechSynthesis;
      synth.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = test?.language === "KZ" ? "kk-KZ" : "ru-RU";
      utterance.rate = 0.96;
      utterance.pitch = 1;

      const voice = pickBestVoice(synth.getVoices(), utterance.lang);
      if (voice) {
        utterance.voice = voice;
      }

      utterance.onstart = () => setAudioPlaying(true);
      utterance.onend = () => {
        setAudioPlaying(false);
        utteranceRef.current = null;
      };
      utterance.onerror = () => {
        setAudioPlaying(false);
        utteranceRef.current = null;
        setAudioError(t("Не удалось воспроизвести вопрос. Попробуйте снова.", "Сұрақты дыбыстау мүмкін болмады. Қайта көріңіз."));
      };

      utteranceRef.current = utterance;
      synth.speak(utterance);
    },
    [t, test?.language],
  );

  const speakQuestion = useCallback(
    async (targetQuestion: Question) => {
      if (!test) return;
      const token = getToken();
      if (!token) {
        speakWithBrowserTTS(targetQuestion);
        return;
      }

      stopAudio();
      setAudioError("");
      setAudioLoading(true);
      const requestId = ttsRequestIdRef.current;

      try {
        const audioBlob = await getQuestionTtsAudio(token, test.id, targetQuestion.id);
        if (requestId !== ttsRequestIdRef.current) return;

        if (!audioBlob.type.startsWith("audio/")) {
          throw new Error(t("Некорректный формат аудио от сервера.", "Серверден қате аудио форматы келді."));
        }

        const objectUrl = URL.createObjectURL(audioBlob);
        audioObjectUrlRef.current = objectUrl;
        const audio = new Audio(objectUrl);
        audioElementRef.current = audio;

        audio.onplay = () => {
          if (requestId !== ttsRequestIdRef.current) return;
          setAudioPlaying(true);
        };
        audio.onended = () => {
          if (requestId !== ttsRequestIdRef.current) return;
          setAudioLoading(false);
          setAudioPlaying(false);
          if (audioObjectUrlRef.current) {
            URL.revokeObjectURL(audioObjectUrlRef.current);
            audioObjectUrlRef.current = null;
          }
          audioElementRef.current = null;
        };
        audio.onerror = () => {
          if (requestId !== ttsRequestIdRef.current) return;
          setAudioLoading(false);
          setAudioPlaying(false);
          if (audioObjectUrlRef.current) {
            URL.revokeObjectURL(audioObjectUrlRef.current);
            audioObjectUrlRef.current = null;
          }
          audioElementRef.current = null;
          speakWithBrowserTTS(targetQuestion, t("Серверный TTS недоступен, включен голос браузера.", "Серверлік TTS қолжетімсіз, браузер дауысы қосылды."));
        };

        await audio.play();
        if (requestId !== ttsRequestIdRef.current) return;
        setAudioLoading(false);
      } catch (err) {
        if (requestId !== ttsRequestIdRef.current) return;
        setAudioLoading(false);
        if (err instanceof DOMException && err.name === "NotAllowedError") {
          setAudioError(t("Автовоспроизведение заблокировано браузером. Нажмите «Озвучить вопрос».", "Автоойнатуды браузер бұғаттады. «Сұрақты дыбыстау» түймесін басыңыз."));
          return;
        }
        const reason = err instanceof Error ? err.message : "";
        const fallbackText = reason
          ? `${t("Серверный TTS недоступен", "Серверлік TTS қолжетімсіз")} (${reason}). ${t("Включен голос браузера.", "Браузер дауысы қосылды.")}`
          : t("Серверный TTS недоступен, включен голос браузера.", "Серверлік TTS қолжетімсіз, браузер дауысы қосылды.");
        speakWithBrowserTTS(targetQuestion, fallbackText);
        if (err instanceof Error) {
          console.warn("Server TTS failed:", err.message);
        }
      }
    },
    [speakWithBrowserTTS, stopAudio, t, test],
  );

  useEffect(() => {
    return () => {
      Object.values(pasteShortcutTimerRef.current).forEach((timerId) => window.clearTimeout(timerId));
      pasteShortcutTimerRef.current = {};
      stopAudio();
      stopOralRecognition(true);
    };
  }, [stopAudio, stopOralRecognition]);

  useEffect(() => {
    if (!question || test?.mode !== "audio") return;

    // Подгружаем список голосов заранее, чтобы для RU/KZ находился наиболее подходящий.
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.getVoices();
    }
    void speakQuestion(question);
    return () => stopAudio();
  }, [question?.id, speakQuestion, stopAudio, test?.mode]);

  useEffect(() => {
    if (!question) return;
    if (oralQuestionId !== null && oralQuestionId !== question.id) {
      stopOralRecognition(true);
    }
    setOralError("");
  }, [oralQuestionId, question?.id, stopOralRecognition]);

  const submit = useCallback(
    async (finalWarnings?: TestIntegrityWarning[]) => {
      if (!test) return;
      const token = getToken();
      if (!token) return;

      const body = {
        answers: test.questions.map((item) => ({
          question_id: item.id,
          student_answer_json: answers[item.id] || {},
        })),
        telemetry: {
          elapsed_seconds: elapsedRef.current,
          warnings: finalWarnings || warningsRef.current,
        },
      };

      try {
        stopOralRecognition(true);
        stopAudio();
        setSubmitting(true);
        await submitTest(token, test.id, body);
        clearPersistedTestSession(test.id);
        router.push(`/results/${test.id}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("Не удалось отправить тест на проверку", "Тестті тексеруге жіберу мүмкін болмады"));
      } finally {
        setSubmitting(false);
      }
    },
    [answers, router, stopAudio, stopOralRecognition, t, test],
  );

  useEffect(() => {
    if (!test || !timeLimitSeconds || submitting) return;
    if (elapsedSeconds < timeLimitSeconds) return;
    if (autoSubmittedRef.current) return;

    autoSubmittedRef.current = true;
    const timeoutWarning: TestIntegrityWarning = {
      type: "time_limit_exceeded",
      at_seconds: elapsedSeconds,
      question_id: null,
      details: {
        limit_seconds: timeLimitSeconds,
        elapsed_seconds: elapsedSeconds,
      },
    };
    const merged = [...warningsRef.current, timeoutWarning];
    warningsRef.current = merged;
    setIntegrityWarnings(merged);
    submit(merged);
  }, [elapsedSeconds, submit, submitting, test, timeLimitSeconds]);

  useEffect(() => {
    if (!test || warningLimit === null || submitting) return;
    if (integrityWarnings.length < warningLimit) return;
    if (autoSubmittedRef.current) return;

    autoSubmittedRef.current = true;
    submit(warningsRef.current);
  }, [integrityWarnings.length, submit, submitting, test, warningLimit]);

  const handleTextFocus = useCallback((questionId: number) => {
    textFocusAtRef.current[questionId] = Date.now();
    fastInputFlagRef.current[questionId] = false;
  }, []);

  const handleTextChange = useCallback(
    (questionId: number, value: string, answerKey: "text" | "spoken_answer_text") => {
      updateAnswer(questionId, { [answerKey]: value });

      const focusAt = textFocusAtRef.current[questionId] || Date.now();
      const deltaMs = Date.now() - focusAt;
      const isFastFilled = deltaMs <= 2000 && value.trim().length >= 40;
      if (isFastFilled && !fastInputFlagRef.current[questionId]) {
        fastInputFlagRef.current[questionId] = true;
        addIntegrityWarning({
          type: "fast_text_input",
          question_id: questionId,
          details: {
            chars: value.trim().length,
            delta_ms: deltaMs,
          },
        });
      }
    },
    [addIntegrityWarning, updateAnswer],
  );

  const handleTextPaste = useCallback(
    (questionId: number, pastedLength: number) => {
      const now = Date.now();
      pasteEventAtRef.current[questionId] = now;
      const pendingTimer = pasteShortcutTimerRef.current[questionId];
      if (pendingTimer) {
        window.clearTimeout(pendingTimer);
        delete pasteShortcutTimerRef.current[questionId];
      }

      addIntegrityWarning({
        type: "paste_detected",
        question_id: questionId,
        details: {
          pasted_chars: pastedLength,
        },
      });
    },
    [addIntegrityWarning],
  );

  const handleTextShortcut = useCallback(
    (questionId: number, key: string, ctrlOrMeta: boolean, alt: boolean) => {
      if (!ctrlOrMeta && !alt) return;
      if (key.toLowerCase() !== "v") return;
      const now = Date.now();
      pasteShortcutAtRef.current[questionId] = now;

      const pendingTimer = pasteShortcutTimerRef.current[questionId];
      if (pendingTimer) {
        window.clearTimeout(pendingTimer);
      }

      pasteShortcutTimerRef.current[questionId] = window.setTimeout(() => {
        const shortcutAt = pasteShortcutAtRef.current[questionId] || 0;
        const pasteAt = pasteEventAtRef.current[questionId] || 0;
        const pasteCapturedForThisShortcut = pasteAt >= shortcutAt && pasteAt - shortcutAt <= 400;
        if (shortcutAt !== now || pasteCapturedForThisShortcut) return;

        addIntegrityWarning({
          type: "paste_shortcut",
          question_id: questionId,
          details: {
            key,
            ctrl_or_meta: ctrlOrMeta,
            alt,
          },
        });
      }, 260);
    },
    [addIntegrityWarning],
  );

  if (loading) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <div className={styles.page}>
            <Card title={t("Загрузка теста", "Тест жүктелуде")}>{t("Подготавливаем вопросы...", "Сұрақтар дайындалып жатыр...")}</Card>
          </div>
        </AppShell>
      </AuthGuard>
    );
  }

  if (!test || !question) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <div className={styles.page}>
            <Card title={t("Тест не найден", "Тест табылмады")}>{t("Проверьте ссылку или сгенерируйте новый тест.", "Сілтемені тексеріңіз немесе жаңа тест жасаңыз.")}</Card>
          </div>
        </AppShell>
      </AuthGuard>
    );
  }

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <div className={styles.page}>
          <Card
            title={`${t("Тест", "Тест")} #${test.id}`}
            subtitle={`${currentIndex + 1} / ${total} ${t("вопрос", "сұрақ")}`}
            action={<Badge variant="info">{Math.round(progress)}%</Badge>}
          >
            <div className={styles.header}>
              <div className={styles.headerBadges}>
                {test.exam_kind && <Badge variant="info">{test.exam_kind.toUpperCase()}</Badge>}
                <Badge>{formatModeBadge(test.mode, uiLanguage)}</Badge>
                <Badge>{formatLanguageBadge(test.language, uiLanguage)}</Badge>
                <Badge>{formatDifficultyBadge(test.difficulty, uiLanguage)}</Badge>
              </div>
              <div className={styles.headerMeta}>
                <span className={`${styles.metaText} ${styles.metaTimer}`}>{t("Таймер", "Таймер")}: {formatDuration(elapsedSeconds)}</span>
                {remainingSeconds !== null && (
                  <span className={`${styles.metaText} ${styles.metaRemaining}`}>
                    {t("Осталось", "Қалды")}: {formatDuration(remainingSeconds)}
                  </span>
                )}
                <span className={`${styles.metaText} ${styles.metaWarnings}`}>
                  {t("Предупреждения", "Ескертулер")}: {integrityWarnings.length}
                </span>
                {warningLimit !== null && (
                  <span className={`${styles.metaText} ${styles.metaWarningLimit}`}>
                    {t("Лимит предупреждений", "Ескерту лимиті")}: {warningLimit}
                  </span>
                )}
              </div>
              <div className={styles.progressWrap}>
                <ProgressBar value={progress} />
              </div>
            </div>
            {isTimeLimitReached && (
              <div className={styles.timeLimitError}>{t("Лимит времени достигнут. Отправляем тест на проверку...", "Уақыт лимиті бітті. Тест тексеруге жіберіліп жатыр...")}</div>
            )}
            {isWarningLimitReached && (
              <div className={styles.timeLimitError}>{t("Достигнут лимит предупреждений. Тест автоматически отправляется.", "Ескерту лимиті жетті. Тест автоматты түрде жіберіледі.")}</div>
            )}
          </Card>

          <Card title={t("Вопрос", "Сұрақ")}>
            <div className={styles.questionWrap}>
              <h3 className={styles.questionTitle}>{sanitizeQuestionPrompt(question.prompt)}</h3>
              {question.options_json?.image_data_url ? (
                <div className={styles.questionImageWrap}>
                  <img
                    alt={t("Иллюстрация к вопросу", "Сұрақ иллюстрациясы")}
                    className={styles.questionImage}
                    src={question.options_json.image_data_url}
                  />
                </div>
              ) : null}

              {test.mode === "audio" && (
                <div className={styles.audioControls}>
                  <Button variant="secondary" disabled={audioLoading} onClick={() => void speakQuestion(question)}>
                    <Volume2 size={16} />{" "}
                    {audioLoading
                      ? t("Готовим аудио...", "Аудио дайындалып жатыр...")
                      : audioPlaying
                        ? t("Повторить озвучку", "Қайта дыбыстау")
                        : t("Озвучить вопрос", "Сұрақты дыбыстау")}
                  </Button>
                  <Button variant="ghost" disabled={!audioPlaying && !audioLoading} onClick={stopAudio}>
                    <VolumeX size={16} /> {t("Стоп", "Тоқтату")}
                  </Button>
                </div>
              )}
              {test.mode === "audio" && audioError && <div className={styles.audioError}>{audioError}</div>}

              {question.type === "single_choice" && renderSingleChoice(question, answerForCurrent, updateAnswer)}
              {question.type === "multi_choice" && renderMultiChoice(question, answerForCurrent, toggleMulti)}
              {(question.type === "short_text" || question.type === "oral_answer") &&
                renderTextAnswer(
                  question,
                  uiLanguage,
                  answerForCurrent,
                  handleTextFocus,
                  handleTextChange,
                  handleTextPaste,
                  handleTextShortcut,
                  test.mode === "oral",
                  {
                    supported: oralSupported,
                    listening: oralListening,
                    activeQuestionId: oralQuestionId,
                    error: oralError,
                    onStart: startOralRecognition,
                    onStop: () => stopOralRecognition(),
                  },
                )}
              {question.type === "matching" && renderMatching(question, uiLanguage, answerForCurrent, updateMatching)}
            </div>

            {error && <div className="errorText">{error}</div>}

            <div className={styles.navRow}>
              <Button
                variant="ghost"
                disabled={currentIndex === 0}
                onClick={() => {
                  stopOralRecognition(true);
                  stopAudio();
                  setCurrentIndex((idx) => Math.max(0, idx - 1));
                }}
              >
                {t("Назад", "Артқа")}
              </Button>

              {currentIndex < total - 1 ? (
                <Button
                  onClick={() => {
                    stopOralRecognition(true);
                    stopAudio();
                    setCurrentIndex((idx) => Math.min(total - 1, idx + 1));
                  }}
                >
                  {t("Далее", "Келесі")}
                </Button>
              ) : (
                <Button disabled={submitting} onClick={() => submit()}>
                  {submitting ? t("Проверяем ответы...", "Жауаптар тексерілуде...") : t("Завершить тест", "Тестті аяқтау")}
                </Button>
              )}
            </div>
          </Card>
        </div>
      </AppShell>
    </AuthGuard>
  );
}

function renderSingleChoice(
  question: Question,
  answer: Record<string, unknown>,
  updateAnswer: (questionId: number, value: Record<string, unknown>) => void,
) {
  const selected = ((answer.selected_option_ids as number[] | undefined) || [])[0];
  const options = question.options_json?.options || [];

  return (
    <div className="stack">
      {options.map((option: OptionItem) => (
        <label className={styles.option} key={`${question.id}-${option.id}`}>
          <input
            checked={selected === option.id}
            name={`single-${question.id}`}
            onChange={() => updateAnswer(question.id, { selected_option_ids: [option.id] })}
            type="radio"
          />
          <span className={styles.optionLabel}>{extractOptionLabel(option.text, option.id)}</span>
          <span className={styles.optionText}>{stripOptionPrefix(option.text)}</span>
        </label>
      ))}
    </div>
  );
}

function renderMultiChoice(
  question: Question,
  answer: Record<string, unknown>,
  toggleMulti: (questionId: number, optionId: number) => void,
) {
  const selected = (answer.selected_option_ids as number[] | undefined) || [];
  const options = question.options_json?.options || [];

  return (
    <div className="stack">
      {options.map((option: OptionItem) => (
        <label className={styles.option} key={`${question.id}-${option.id}`}>
          <input
            checked={selected.includes(option.id)}
            onChange={() => toggleMulti(question.id, option.id)}
            type="checkbox"
          />
          <span className={styles.optionLabel}>{extractOptionLabel(option.text, option.id)}</span>
          <span className={styles.optionText}>{stripOptionPrefix(option.text)}</span>
        </label>
      ))}
    </div>
  );
}

function renderTextAnswer(
  question: Question,
  language: Language,
  answer: Record<string, unknown>,
  onFocus: (questionId: number) => void,
  onTextChange: (questionId: number, value: string, answerKey: "text" | "spoken_answer_text") => void,
  onPasteDetected: (questionId: number, pastedLength: number) => void,
  onPasteShortcut: (questionId: number, key: string, ctrlOrMeta: boolean, alt: boolean) => void,
  forceOralInput: boolean,
  oralControls: OralAnswerControls,
) {
  const t = (ru: string, kz: string) => tr(language, ru, kz);
  const isOral = question.type === "oral_answer" || forceOralInput;
  const key = isOral ? "spoken_answer_text" : "text";
  const value = (answer[key] as string | undefined) || "";
  const oralActive = oralControls.listening && oralControls.activeQuestionId === question.id;

  return (
    <div className="stack">
      {isOral && (
        <div className={styles.oralWrap}>
          <div className={styles.oralHint}>
            {t("Проговорите ответ голосом. Текст автоматически появится в поле ниже.", "Жауапты дауыстап айтыңыз. Мәтін төмендегі өріске автоматты түрде түседі.")}
          </div>
          <div className={styles.oralControls}>
            <Button
              variant="secondary"
              onClick={() => oralControls.onStart(question)}
              disabled={!oralControls.supported || oralActive}
            >
              <Mic size={16} /> {oralActive ? t("Идет запись...", "Жазылып жатыр...") : t("Начать запись", "Жазуды бастау")}
            </Button>
            <Button variant="ghost" disabled={!oralActive} onClick={oralControls.onStop}>
              <Square size={16} /> {t("Остановить", "Тоқтату")}
            </Button>
          </div>
          {!oralControls.supported && (
            <div className="muted">{t("Браузер не поддерживает распознавание речи. Можно ввести ответ вручную.", "Браузер дауысты тануды қолдамайды. Жауапты қолмен енгізуге болады.")}</div>
          )}
          {oralControls.error && <div className={styles.oralError}>{oralControls.error}</div>}
        </div>
      )}
      <textarea
        onFocus={() => onFocus(question.id)}
        onChange={(e) => onTextChange(question.id, e.target.value, key)}
        onPaste={(e) => onPasteDetected(question.id, e.clipboardData?.getData("text")?.length || 0)}
        onKeyDown={(e) => onPasteShortcut(question.id, e.key, e.ctrlKey || e.metaKey, e.altKey)}
        placeholder={isOral ? t("Сюда попадает распознанная речь", "Танылған сөйлеу осында түседі") : t("Ваш ответ", "Сіздің жауабыңыз")}
        rows={4}
        value={value}
      />
    </div>
  );
}

function renderMatching(
  question: Question,
  language: Language,
  answer: Record<string, unknown>,
  updateMatching: (questionId: number, left: string, right: string) => void,
) {
  const t = (ru: string, kz: string) => tr(language, ru, kz);
  const leftItems = question.options_json?.left || [];
  const rightItems = question.options_json?.right || [];
  const selectedMatches = (answer.matches as Record<string, string> | undefined) || {};

  return (
    <div className="stack">
      {leftItems.map((left) => (
        <label className={styles.matchRow} key={`${question.id}-${left}`}>
          <span>{left}</span>
          <select onChange={(e) => updateMatching(question.id, left, e.target.value)} value={selectedMatches[left] || ""}>
            <option value="">{t("Выберите...", "Таңдаңыз...")}</option>
            {rightItems.map((right) => (
              <option key={`${question.id}-${left}-${right}`} value={right}>
                {right}
              </option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
}

function getTestSessionStorageKey(testId: number): string {
  return `${TEST_SESSION_STORAGE_PREFIX}${testId}`;
}

function loadPersistedTestSession(testId: number): PersistedTestSession | null {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.sessionStorage.getItem(getTestSessionStorageKey(testId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PersistedTestSession>;
    if (parsed.version !== 1 || parsed.test_id !== testId) return null;
    if (typeof parsed.started_at_ms !== "number" || !Number.isFinite(parsed.started_at_ms)) return null;
    return {
      version: 1,
      test_id: testId,
      started_at_ms: parsed.started_at_ms,
      current_index: typeof parsed.current_index === "number" ? parsed.current_index : 0,
      answers: parsed.answers && typeof parsed.answers === "object" ? (parsed.answers as AnswerMap) : {},
      integrity_warnings: Array.isArray(parsed.integrity_warnings)
        ? (parsed.integrity_warnings as TestIntegrityWarning[])
        : [],
    };
  } catch {
    return null;
  }
}

function persistTestSession(session: PersistedTestSession): void {
  if (typeof window === "undefined") return;

  try {
    window.sessionStorage.setItem(getTestSessionStorageKey(session.test_id), JSON.stringify(session));
  } catch {
    // ignore session storage errors
  }
}

function clearPersistedTestSession(testId: number): void {
  if (typeof window === "undefined") return;

  try {
    window.sessionStorage.removeItem(getTestSessionStorageKey(testId));
  } catch {
    // ignore session storage errors
  }
}

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const maybeWindow = window as Window & {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return maybeWindow.SpeechRecognition || maybeWindow.webkitSpeechRecognition || null;
}

function getSpeechRecognitionErrorMessage(errorCode: string | undefined, language: Language): string {
  if (!errorCode) return tr(language, "Не удалось распознать речь. Попробуйте еще раз.", "Сөйлеуді тану мүмкін болмады. Қайта көріңіз.");
  if (errorCode === "not-allowed" || errorCode === "service-not-allowed") {
    return tr(language, "Нет доступа к микрофону. Разрешите доступ в настройках браузера.", "Микрофонға рұқсат жоқ. Браузер баптауларында рұқсат беріңіз.");
  }
  if (errorCode === "audio-capture") {
    return tr(language, "Микрофон не найден. Подключите микрофон и попробуйте снова.", "Микрофон табылмады. Микрофонды қосып, қайта көріңіз.");
  }
  if (errorCode === "network") {
    return tr(language, "Ошибка сети при распознавании речи. Проверьте подключение к интернету.", "Сөйлеуді тану кезінде желі қатесі шықты. Интернет байланысын тексеріңіз.");
  }
  if (errorCode === "no-speech") {
    return tr(language, "Речь не распознана. Говорите чуть громче и повторите попытку.", "Сөйлеу танылмады. Дауысыңызды сәл көтеріп, қайта көріңіз.");
  }
  if (errorCode === "aborted") {
    return "";
  }
  return tr(language, "Не удалось распознать речь. Попробуйте еще раз.", "Сөйлеуді тану мүмкін болмады. Қайта көріңіз.");
}

function normalizeSpokenText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function formatDuration(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (safe % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function extractOptionLabel(text: string, optionId: number): string {
  const match = text.match(/^\s*([A-Z])\s*[\).:-]/i);
  if (match?.[1]) {
    return match[1].toUpperCase();
  }
  const base = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  return base[optionId] || "?";
}

function stripOptionPrefix(text: string): string {
  return text.replace(/^\s*[A-Z]\s*[\).:-]\s*/i, "").trim();
}

function pickBestVoice(voices: SpeechSynthesisVoice[], lang: string): SpeechSynthesisVoice | null {
  if (!voices.length) return null;
  const normalized = lang.toLowerCase();

  const exact = voices.find((voice) => voice.lang.toLowerCase() === normalized);
  if (exact) return exact;

  const byBaseLang = voices.find((voice) => voice.lang.toLowerCase().startsWith(normalized.slice(0, 2)));
  return byBaseLang || voices[0] || null;
}

function buildAudioNarration(question: Question, language: "RU" | "KZ"): string {
  const basePrompt = sanitizeQuestionPrompt((question.tts_text || question.prompt || "").trim());
  return basePrompt;
}

function sanitizeQuestionPrompt(prompt: string): string {
  return prompt.replace(/\s*\((вариант|нұсқа)\s*\d+\)\s*$/i, "").trim();
}

function formatModeBadge(mode: Test["mode"], language: Language): string {
  if (mode === "audio") return tr(language, "Аудио", "Аудио");
  if (mode === "oral") return tr(language, "Устный", "Ауызша");
  return tr(language, "Стандарт", "Стандарт");
}

function formatLanguageBadge(value: Test["language"], language: Language): string {
  return value === "KZ" ? tr(language, "Казахский", "Қазақша") : tr(language, "Русский", "Орысша");
}

function formatDifficultyBadge(difficulty: Test["difficulty"], language: Language): string {
  if (difficulty === "easy") return tr(language, "Легкий", "Жеңіл");
  if (difficulty === "hard") return tr(language, "Сложный", "Күрделі");
  return tr(language, "Средний", "Орташа");
}
