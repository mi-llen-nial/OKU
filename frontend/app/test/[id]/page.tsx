"use client";

import { Volume2, VolumeX } from "lucide-react";
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
import { OptionItem, Question, Test } from "@/lib/types";
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

export default function TestRunnerPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const testId = Number(params.id);

  const [test, setTest] = useState<Test | null>(null);
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [audioPlaying, setAudioPlaying] = useState(false);
  const [audioLoading, setAudioLoading] = useState(false);
  const [audioError, setAudioError] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [integrityWarnings, setIntegrityWarnings] = useState<TestIntegrityWarning[]>([]);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const audioElementRef = useRef<HTMLAudioElement | null>(null);
  const audioObjectUrlRef = useRef<string | null>(null);
  const ttsRequestIdRef = useRef(0);
  const elapsedRef = useRef(0);
  const warningsRef = useRef<TestIntegrityWarning[]>([]);
  const textFocusAtRef = useRef<Record<number, number>>({});
  const fastInputFlagRef = useRef<Record<number, boolean>>({});
  const lastVisibilityWarningAtRef = useRef(0);
  const autoSubmittedRef = useRef(false);

  useEffect(() => {
    const token = getToken();
    if (!token || Number.isNaN(testId)) return;

    getTest(token, testId)
      .then((payload) => setTest(payload))
      .catch((err) => setError(err instanceof Error ? err.message : "Cannot load test"))
      .finally(() => setLoading(false));
  }, [testId]);

  const question = test?.questions[currentIndex] || null;
  const total = test?.questions.length || 0;
  const progress = total > 0 ? ((currentIndex + 1) / total) * 100 : 0;
  const timeLimitSeconds = test?.time_limit_seconds ?? null;
  const isTimeLimitReached = timeLimitSeconds !== null && elapsedSeconds >= timeLimitSeconds;

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
      const signature = `${next.type}|${next.question_id ?? "none"}|${next.at_seconds}`;
      const exists = warningsRef.current.some(
        (item) => `${item.type}|${item.question_id ?? "none"}|${item.at_seconds}` === signature,
      );
      if (exists) return;

      const merged = [...warningsRef.current, next];
      warningsRef.current = merged;
      setIntegrityWarnings(merged);
    },
    [],
  );

  useEffect(() => {
    if (!test) return;
    setElapsedSeconds(0);
    elapsedRef.current = 0;
    setIntegrityWarnings([]);
    warningsRef.current = [];
    textFocusAtRef.current = {};
    fastInputFlagRef.current = {};
    lastVisibilityWarningAtRef.current = 0;
    autoSubmittedRef.current = false;
    const startedAt = Date.now();
    const interval = window.setInterval(() => {
      const nextElapsed = Math.floor((Date.now() - startedAt) / 1000);
      elapsedRef.current = nextElapsed;
      setElapsedSeconds(nextElapsed);
    }, 1000);
    return () => window.clearInterval(interval);
  }, [test?.id]);

  useEffect(() => {
    if (!test) return;

    const onVisibilityChange = () => {
      if (!document.hidden) return;
      const now = Date.now();
      if (now - lastVisibilityWarningAtRef.current < 1500) return;
      lastVisibilityWarningAtRef.current = now;
      addIntegrityWarning({
        type: "tab_switch",
        details: { source: "visibilitychange" },
      });
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
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

  const stopAudio = useCallback(() => {
    ttsRequestIdRef.current += 1;

    if (audioElementRef.current) {
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
        setAudioError("На этом устройстве озвучка недоступна.");
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
        setAudioError("Не удалось воспроизвести вопрос. Попробуйте снова.");
      };

      utteranceRef.current = utterance;
      synth.speak(utterance);
    },
    [test?.language],
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
          throw new Error("Некорректный формат аудио от сервера.");
        }

        const objectUrl = URL.createObjectURL(audioBlob);
        audioObjectUrlRef.current = objectUrl;
        const audio = new Audio(objectUrl);
        audioElementRef.current = audio;

        audio.onplay = () => setAudioPlaying(true);
        audio.onended = () => {
          setAudioLoading(false);
          setAudioPlaying(false);
          if (audioObjectUrlRef.current) {
            URL.revokeObjectURL(audioObjectUrlRef.current);
            audioObjectUrlRef.current = null;
          }
          audioElementRef.current = null;
        };
        audio.onerror = () => {
          setAudioLoading(false);
          setAudioPlaying(false);
          if (audioObjectUrlRef.current) {
            URL.revokeObjectURL(audioObjectUrlRef.current);
            audioObjectUrlRef.current = null;
          }
          audioElementRef.current = null;
          speakWithBrowserTTS(targetQuestion, "Серверный TTS недоступен, включен голос браузера.");
        };

        await audio.play();
        if (requestId !== ttsRequestIdRef.current) return;
        setAudioLoading(false);
      } catch (err) {
        if (requestId !== ttsRequestIdRef.current) return;
        setAudioLoading(false);
        if (err instanceof DOMException && err.name === "NotAllowedError") {
          setAudioError("Автовоспроизведение заблокировано браузером. Нажмите «Озвучить вопрос».");
          return;
        }
        const reason = err instanceof Error ? err.message : "";
        const fallbackText = reason
          ? `Серверный TTS недоступен (${reason}). Включен голос браузера.`
          : "Серверный TTS недоступен, включен голос браузера.";
        speakWithBrowserTTS(targetQuestion, fallbackText);
        if (err instanceof Error) {
          console.warn("Server TTS failed:", err.message);
        }
      }
    },
    [speakWithBrowserTTS, stopAudio, test],
  );

  useEffect(() => {
    return () => {
      stopAudio();
    };
  }, [stopAudio]);

  useEffect(() => {
    if (!question || test?.mode !== "audio") return;

    // Подгружаем список голосов заранее, чтобы для RU/KZ находился наиболее подходящий.
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.getVoices();
    }
    void speakQuestion(question);
    return () => stopAudio();
  }, [question?.id, speakQuestion, stopAudio, test?.mode]);

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
        stopAudio();
        setSubmitting(true);
        await submitTest(token, test.id, body);
        router.push(`/results/${test.id}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Submit failed");
      } finally {
        setSubmitting(false);
      }
    },
    [answers, router, stopAudio, test],
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
      addIntegrityWarning({
        type: "paste_shortcut",
        question_id: questionId,
        details: {
          key,
          ctrl_or_meta: ctrlOrMeta,
          alt,
        },
      });
    },
    [addIntegrityWarning],
  );

  if (loading) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <div className={styles.page}>
            <Card title="Загрузка теста">Подготавливаем вопросы...</Card>
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
            <Card title="Тест не найден">Проверьте ссылку или сгенерируйте новый тест.</Card>
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
            title={`Тест #${test.id}`}
            subtitle={`${currentIndex + 1} / ${total} вопрос`}
            action={<Badge variant="info">{Math.round(progress)}%</Badge>}
          >
            <div className={styles.header}>
              <div className={styles.headerBadges}>
                <Badge>{test.mode.toUpperCase()}</Badge>
                <Badge>{test.language}</Badge>
                <Badge>{test.difficulty}</Badge>
              </div>
              <div className={styles.headerMeta}>
                <span className={styles.metaText}>Таймер: {formatDuration(elapsedSeconds)}</span>
                {timeLimitSeconds !== null && (
                  <span className={styles.metaText}>
                    Лимит: {formatDuration(timeLimitSeconds)}
                  </span>
                )}
                <span className={styles.metaText}>Предупреждения: {integrityWarnings.length}</span>
              </div>
              <div style={{ minWidth: 180, flex: "1 1 220px" }}>
                <ProgressBar value={progress} />
              </div>
            </div>
            {isTimeLimitReached && (
              <div className={styles.timeLimitError}>Лимит времени достигнут. Отправляем тест на проверку...</div>
            )}
          </Card>

          <Card title="Вопрос">
            <div className={styles.questionWrap}>
              <h3 className={styles.questionTitle}>{sanitizeQuestionPrompt(question.prompt)}</h3>

              {test.mode === "audio" && (
                <div className={styles.audioControls}>
                  <Button variant="secondary" disabled={audioLoading} onClick={() => void speakQuestion(question)}>
                    <Volume2 size={16} /> {audioLoading ? "Готовим аудио..." : audioPlaying ? "Повторить озвучку" : "Озвучить вопрос"}
                  </Button>
                  <Button variant="ghost" disabled={!audioPlaying && !audioLoading} onClick={stopAudio}>
                    <VolumeX size={16} /> Стоп
                  </Button>
                </div>
              )}
              {test.mode === "audio" && audioError && <div className={styles.audioError}>{audioError}</div>}

              {question.type === "single_choice" && renderSingleChoice(question, answerForCurrent, updateAnswer)}
              {question.type === "multi_choice" && renderMultiChoice(question, answerForCurrent, toggleMulti)}
              {(question.type === "short_text" || question.type === "oral_answer") &&
                renderTextAnswer(
                  question,
                  answerForCurrent,
                  updateAnswer,
                  handleTextFocus,
                  handleTextChange,
                  handleTextPaste,
                  handleTextShortcut,
                )}
              {question.type === "matching" && renderMatching(question, answerForCurrent, updateMatching)}
            </div>

            {error && <div className="errorText">{error}</div>}

            <div className={styles.navRow}>
              <Button
                variant="ghost"
                disabled={currentIndex === 0}
                onClick={() => {
                  stopAudio();
                  setCurrentIndex((idx) => Math.max(0, idx - 1));
                }}
              >
                Назад
              </Button>

              {currentIndex < total - 1 ? (
                <Button
                  onClick={() => {
                    stopAudio();
                    setCurrentIndex((idx) => Math.min(total - 1, idx + 1));
                  }}
                >
                  Далее
                </Button>
              ) : (
                <Button disabled={submitting} onClick={() => submit()}>
                  {submitting ? "Проверяем ответы..." : "Завершить тест"}
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
  answer: Record<string, unknown>,
  updateAnswer: (questionId: number, value: Record<string, unknown>) => void,
  onFocus: (questionId: number) => void,
  onTextChange: (questionId: number, value: string, answerKey: "text" | "spoken_answer_text") => void,
  onPasteDetected: (questionId: number, pastedLength: number) => void,
  onPasteShortcut: (questionId: number, key: string, ctrlOrMeta: boolean, alt: boolean) => void,
) {
  const isOral = question.type === "oral_answer";
  const key = isOral ? "spoken_answer_text" : "text";
  const value = (answer[key] as string | undefined) || "";

  return (
    <div className="stack">
      {isOral && <div className="muted">Вставьте распознанную речь из STT (mock-режим).</div>}
      <textarea
        onFocus={() => onFocus(question.id)}
        onChange={(e) => onTextChange(question.id, e.target.value, key)}
        onPaste={(e) => onPasteDetected(question.id, e.clipboardData?.getData("text")?.length || 0)}
        onKeyDown={(e) => onPasteShortcut(question.id, e.key, e.ctrlKey || e.metaKey, e.altKey)}
        placeholder={isOral ? "Сюда попадает распознанная речь" : "Ваш ответ"}
        rows={4}
        value={value}
      />
      {isOral && (
        <Button
          variant="secondary"
          onClick={() => updateAnswer(question.id, { spoken_answer_text: `${value} [mock transcript]`.trim() })}
        >
          Сгенерировать mock STT
        </Button>
      )}
    </div>
  );
}

function renderMatching(
  question: Question,
  answer: Record<string, unknown>,
  updateMatching: (questionId: number, left: string, right: string) => void,
) {
  const leftItems = question.options_json?.left || [];
  const rightItems = question.options_json?.right || [];
  const selectedMatches = (answer.matches as Record<string, string> | undefined) || {};

  return (
    <div className="stack">
      {leftItems.map((left) => (
        <label className={styles.matchRow} key={`${question.id}-${left}`}>
          <span>{left}</span>
          <select onChange={(e) => updateMatching(question.id, left, e.target.value)} value={selectedMatches[left] || ""}>
            <option value="">Выберите...</option>
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
  const parts: string[] = [];
  const basePrompt = sanitizeQuestionPrompt((question.tts_text || question.prompt || "").trim());
  if (basePrompt) {
    parts.push(basePrompt);
  }

  const options = question.options_json?.options || [];
  if (options.length > 0) {
    parts.push(language === "KZ" ? "Жауап нұсқалары:" : "Варианты ответа:");
    for (const option of options) {
      const label = extractOptionLabel(option.text, option.id);
      const text = stripOptionPrefix(option.text);
      parts.push(`${label}. ${text}.`);
    }
  }

  const left = question.options_json?.left || [];
  const right = question.options_json?.right || [];
  if (left.length && right.length) {
    if (language === "KZ") {
      parts.push("Сол жақтағы элементтер:");
      parts.push(left.join(". "));
      parts.push("Оң жақтағы элементтер:");
      parts.push(right.join(". "));
    } else {
      parts.push("Элементы слева:");
      parts.push(left.join(". "));
      parts.push("Элементы справа:");
      parts.push(right.join(". "));
    }
  }

  return parts.join(" ");
}

function sanitizeQuestionPrompt(prompt: string): string {
  return prompt.replace(/\s*\((вариант|нұсқа)\s*\d+\)\s*$/i, "").trim();
}
