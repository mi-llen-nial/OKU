"use client";

import { Activity, LineChart, Target } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import StatWidget from "@/components/ui/StatWidget";
import { generateTest, getProgress, getSubjects } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { Difficulty, Language, Mode, StudentProgress, Subject } from "@/lib/types";
import styles from "@/app/dashboard/dashboard.module.css";

const DIFFICULTIES: Array<{ value: Difficulty; title: string; desc: string }> = [
  { value: "easy", title: "Базовый", desc: "Базовые факты и ключевые понятия" },
  { value: "medium", title: "Средний", desc: "Комбинированные задачи и контекст" },
  { value: "hard", title: "Продвинутый", desc: "Глубокий анализ и открытые ответы" },
];

const MODES: Array<{ value: Mode; title: string; desc: string }> = [
  { value: "text", title: "Текстовый", desc: "Выбор ответа и ввод текста" },
  { value: "audio", title: "Аудио", desc: "Озвучивание вопросов через TTS" },
  { value: "oral", title: "Устный", desc: "Ответ голосом через STT-поток" },
];

export default function DashboardPage() {
  const router = useRouter();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subjectId, setSubjectId] = useState<number>(1);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [language, setLanguage] = useState<Language>("RU");
  const [mode, setMode] = useState<Mode>("text");
  const [numQuestions, setNumQuestions] = useState(10);
  const [progress, setProgress] = useState<StudentProgress | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    Promise.all([getSubjects(token), getProgress(token)])
      .then(([subjectsData, progressData]) => {
        setSubjects(subjectsData);
        setProgress(progressData);
        if (subjectsData.length > 0) {
          setSubjectId(subjectsData[0].id);
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Cannot load dashboard data"));
  }, []);

  const selectedSubject = useMemo(() => subjects.find((subject) => subject.id === subjectId), [subjectId, subjects]);

  const handleGenerate = async () => {
    const token = getToken();
    if (!token) return;

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
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <section className={styles.intro}>
          <Card title="Новый тест" subtitle="Соберите персональную попытку под текущую цель обучения.">
            <div className="stack">
              <div className="inline">
                <Badge variant="info">RU / KZ</Badge>
                <Badge variant="normal">Adaptive difficulty</Badge>
                <Badge variant="normal">Text / Audio / Oral</Badge>
              </div>
              <p className="muted">
                Текущий предмет:{" "}
                <b>{selectedSubject ? (language === "RU" ? selectedSubject.name_ru : selectedSubject.name_kz) : "—"}</b>
              </p>
              <p className={styles.meta}>Каждая генерация создаёт новый набор вопросов для выбранной конфигурации.</p>
            </div>
          </Card>
        </section>

        <section className={styles.statGrid}>
          <StatWidget
            label="Средний балл"
            value={`${progress?.avg_percent ?? 0}%`}
            meta="по всем попыткам"
            icon={<Activity size={16} />}
          />
          <StatWidget
            label="Лучший результат"
            value={`${progress?.best_percent ?? 0}%`}
            meta="лучший тест"
            icon={<Target size={16} />}
          />
          <StatWidget
            label="Всего тестов"
            value={`${progress?.total_tests ?? 0}`}
            meta="накопленная история"
            icon={<LineChart size={16} />}
          />
        </section>

        <Card title="Параметры теста" subtitle="Выберите предмет, сложность, язык и режим прохождения.">
          <div className="formGrid">
            <div>
              <h4 className="sectionTitle">Предмет</h4>
              <div className={styles.optionCards}>
                {subjects.map((subject) => {
                  const active = subject.id === subjectId;
                  return (
                    <button
                      key={subject.id}
                      type="button"
                      className={`selectCard ${active ? "selectCardActive" : ""}`}
                      onClick={() => setSubjectId(subject.id)}
                    >
                      <div className="selectCardTitle">{language === "RU" ? subject.name_ru : subject.name_kz}</div>
                      <div className="selectCardDescription">Предмет #{subject.id}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <h4 className="sectionTitle">Сложность</h4>
              <div className={styles.optionCards}>
                {DIFFICULTIES.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className={`selectCard ${difficulty === item.value ? "selectCardActive" : ""}`}
                    onClick={() => setDifficulty(item.value)}
                  >
                    <div className="selectCardTitle">{item.title}</div>
                    <div className="selectCardDescription">{item.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            <div className={styles.optionCards2}>
              <div>
                <h4 className="sectionTitle">Язык</h4>
                <div className={styles.optionCards2}>
                  {(["RU", "KZ"] as const).map((lang) => (
                    <button
                      key={lang}
                      type="button"
                      className={`selectCard ${language === lang ? "selectCardActive" : ""}`}
                      onClick={() => setLanguage(lang)}
                    >
                      <div className="selectCardTitle">{lang}</div>
                      <div className="selectCardDescription">Контент на выбранном языке</div>
                    </button>
                  ))}
                </div>
              </div>

              <label>
                Количество вопросов
                <input
                  max={20}
                  min={5}
                  onChange={(e) => setNumQuestions(Number(e.target.value))}
                  type="number"
                  value={numQuestions}
                />
              </label>
            </div>

            <div>
              <h4 className="sectionTitle">Режим прохождения</h4>
              <div className={styles.optionCards}>
                {MODES.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className={`selectCard ${mode === item.value ? "selectCardActive" : ""}`}
                    onClick={() => setMode(item.value)}
                  >
                    <div className="selectCardTitle">{item.title}</div>
                    <div className="selectCardDescription">{item.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {error && <div className="errorText">{error}</div>}

            <div className="inline">
              <Button disabled={loading} onClick={handleGenerate}>
                {loading ? "Генерируем тест..." : "Начать тест"}
              </Button>
              <Button variant="secondary" onClick={() => router.push("/history")}>История</Button>
            </div>
          </div>
        </Card>
      </AppShell>
    </AuthGuard>
  );
}
