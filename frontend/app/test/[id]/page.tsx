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
import { getTest, submitTest } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { OptionItem, Question, Test } from "@/lib/types";
import styles from "@/app/test/[id]/runner.module.css";

interface AnswerMap {
  [questionId: number]: Record<string, unknown>;
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
  const [audioError, setAudioError] = useState("");
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

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

  const answerForCurrent = useMemo(() => {
    if (!question) return {};
    return answers[question.id] || {};
  }, [answers, question]);

  const updateAnswer = (questionId: number, value: Record<string, unknown>) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  };

  const toggleMulti = (questionId: number, optionId: number) => {
    const selected = (answers[questionId]?.selected_option_ids as number[] | undefined) || [];
    const next = selected.includes(optionId) ? selected.filter((id) => id !== optionId) : [...selected, optionId];
    updateAnswer(questionId, { selected_option_ids: next });
  };

  const updateMatching = (questionId: number, left: string, right: string) => {
    const existing = (answers[questionId]?.matches as Record<string, string> | undefined) || {};
    updateAnswer(questionId, { matches: { ...existing, [left]: right } });
  };

  const stopAudio = useCallback(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    utteranceRef.current = null;
    setAudioPlaying(false);
  }, []);

  const speakQuestion = useCallback(
    (targetQuestion: Question) => {
      if (typeof window === "undefined" || !("speechSynthesis" in window)) {
        setAudioError("На этом устройстве озвучка недоступна.");
        return;
      }

      const text = buildAudioNarration(targetQuestion, test?.language || "RU");
      if (!text) return;

      setAudioError("");
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
    speakQuestion(question);
    return () => stopAudio();
  }, [question?.id, speakQuestion, stopAudio, test?.mode]);

  const submit = async () => {
    if (!test) return;
    const token = getToken();
    if (!token) return;

    const body = {
      answers: test.questions.map((item) => ({
        question_id: item.id,
        student_answer_json: answers[item.id] || {},
      })),
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
  };

  if (loading) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <Card title="Загрузка теста">Подготавливаем вопросы...</Card>
        </AppShell>
      </AuthGuard>
    );
  }

  if (!test || !question) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <Card title="Тест не найден">Проверьте ссылку или сгенерируйте новый тест.</Card>
        </AppShell>
      </AuthGuard>
    );
  }

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <Card
          title={`Тест #${test.id}`}
          subtitle={`${currentIndex + 1} / ${total} вопрос`}
          action={<Badge variant="info">{Math.round(progress)}%</Badge>}
        >
          <div className={styles.header}>
            <div className="inline">
              <Badge>{test.mode.toUpperCase()}</Badge>
              <Badge>{test.language}</Badge>
              <Badge>{test.difficulty}</Badge>
            </div>
            <div style={{ minWidth: 180, flex: "1 1 220px" }}>
              <ProgressBar value={progress} />
            </div>
          </div>
        </Card>

        <Card title="Вопрос">
          <div className={styles.questionWrap}>
            <h3 className={styles.questionTitle}>{question.prompt}</h3>

            {test.mode === "audio" && (
              <div className={styles.audioControls}>
                <Button variant="secondary" onClick={() => speakQuestion(question)}>
                  <Volume2 size={16} /> {audioPlaying ? "Повторить озвучку" : "Озвучить вопрос"}
                </Button>
                <Button variant="ghost" disabled={!audioPlaying} onClick={stopAudio}>
                  <VolumeX size={16} /> Стоп
                </Button>
              </div>
            )}
            {test.mode === "audio" && audioError && <div className={styles.audioError}>{audioError}</div>}

            {question.type === "single_choice" && renderSingleChoice(question, answerForCurrent, updateAnswer)}
            {question.type === "multi_choice" && renderMultiChoice(question, answerForCurrent, toggleMulti)}
            {(question.type === "short_text" || question.type === "oral_answer") &&
              renderTextAnswer(question, answerForCurrent, updateAnswer)}
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
              <Button disabled={submitting} onClick={submit}>
                {submitting ? "Проверяем ответы..." : "Завершить тест"}
              </Button>
            )}
          </div>
        </Card>
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
) {
  const isOral = question.type === "oral_answer";
  const key = isOral ? "spoken_answer_text" : "text";
  const value = (answer[key] as string | undefined) || "";

  return (
    <div className="stack">
      {isOral && <div className="muted">Вставьте распознанную речь из STT (mock-режим).</div>}
      <textarea
        onChange={(e) => updateAnswer(question.id, { [key]: e.target.value })}
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
  const basePrompt = (question.tts_text || question.prompt || "").trim();
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
