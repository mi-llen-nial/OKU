"use client";

import { Headphones, Mic2, Type } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { generateTest, getSubjects } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { Difficulty, Language, Mode, Subject } from "@/lib/types";
import styles from "@/app/test/test-setup.module.css";

export default function TestSetupPage() {
  const router = useRouter();
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subjectId, setSubjectId] = useState<number>(1);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [language, setLanguage] = useState<Language>("RU");
  const [mode, setMode] = useState<Mode>("text");
  const [numQuestions, setNumQuestions] = useState(10);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    getSubjects(token)
      .then((data) => {
        setSubjects(data);
        if (data.length > 0) {
          setSubjectId(data[0].id);
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Cannot load subjects"));
  }, []);

  const createTest = async () => {
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
      setError(err instanceof Error ? err.message : "Cannot generate test");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <div className={styles.layout}>
          <Card title="Настройка теста" subtitle="Соберите конфигурацию и запустите попытку.">
            <div className="formGrid">
              <label>
                Предмет
                <select onChange={(e) => setSubjectId(Number(e.target.value))} value={subjectId}>
                  {subjects.map((subject) => (
                    <option key={subject.id} value={subject.id}>
                      {language === "RU" ? subject.name_ru : subject.name_kz}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Сложность
                <select onChange={(e) => setDifficulty(e.target.value as Difficulty)} value={difficulty}>
                  <option value="easy">easy</option>
                  <option value="medium">medium</option>
                  <option value="hard">hard</option>
                </select>
              </label>

              <label>
                Язык
                <select onChange={(e) => setLanguage(e.target.value as Language)} value={language}>
                  <option value="RU">RU</option>
                  <option value="KZ">KZ</option>
                </select>
              </label>

              <label>
                Режим
                <select onChange={(e) => setMode(e.target.value as Mode)} value={mode}>
                  <option value="text">text</option>
                  <option value="audio">audio</option>
                  <option value="oral">oral</option>
                </select>
              </label>

              <label>
                Количество вопросов
                <input min={5} max={20} type="number" value={numQuestions} onChange={(e) => setNumQuestions(Number(e.target.value))} />
              </label>

              {error && <div className="errorText">{error}</div>}

              <Button onClick={createTest} disabled={loading}>
                {loading ? "Генерируем..." : "Сгенерировать тест"}
              </Button>
            </div>
          </Card>

          <Card title="Режимы прохождения" subtitle="Подготовлено для text, audio и oral сценариев.">
            <div className={styles.modeList}>
              <div className={styles.modeItem}>
                <div className="inline"><Type size={16} /><span className={styles.modeTitle}>Text</span></div>
                <div className={styles.modeText}>Классический формат: варианты ответа, matching и short text.</div>
              </div>
              <div className={styles.modeItem}>
                <div className="inline"><Headphones size={16} /><span className={styles.modeTitle}>Audio</span></div>
                <div className={styles.modeText}>Вопросы можно воспроизводить голосом через TTS-поток.</div>
              </div>
              <div className={styles.modeItem}>
                <div className="inline"><Mic2 size={16} /><span className={styles.modeTitle}>Oral</span></div>
                <div className={styles.modeText}>Ответы в поле `spoken_answer_text`, совместимо с STT-провайдером.</div>
              </div>
            </div>
          </Card>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
