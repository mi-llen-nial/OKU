"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Accordion from "@/components/ui/Accordion";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { getTestResult, regenerateRecommendation } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { TestResult } from "@/lib/types";
import styles from "@/app/results/[id]/results.module.css";

export default function ResultPage() {
  const params = useParams<{ id: string }>();
  const testId = Number(params.id);

  const [data, setData] = useState<TestResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token || Number.isNaN(testId)) return;

    getTestResult(token, testId)
      .then((result) => setData(result))
      .catch((err) => setError(err instanceof Error ? err.message : "Cannot load result"))
      .finally(() => setLoading(false));
  }, [testId]);

  const regenerate = async () => {
    const token = getToken();
    if (!token) return;

    try {
      setBusy(true);
      const recommendation = await regenerateRecommendation(token, testId);
      setData((prev) => (prev ? { ...prev, recommendation } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Regeneration failed");
    } finally {
      setBusy(false);
    }
  };

  const accuracy = data?.result.percent ?? 0;

  const accordionItems = useMemo(
    () =>
      (data?.feedback || []).map((item) => ({
        id: String(item.question_id),
        title: `Q${item.question_id}: ${item.topic}`,
        subtitle: item.is_correct ? "Верно" : "Ошибка",
        content: (
          <>
            <div><b>Вопрос:</b> {sanitizeQuestionPrompt(item.prompt)}</div>
            <div><b>Балл:</b> {item.score}</div>
            <div><b>Пояснение:</b> {item.explanation}</div>
          </>
        ),
      })),
    [data?.feedback],
  );

  if (loading) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <Card title="Результаты">Загружаем данные...</Card>
        </AppShell>
      </AuthGuard>
    );
  }

  if (!data) {
    return (
      <AuthGuard roles={["student"]}>
        <AppShell>
          <Card title="Результат не найден">Проверьте ID теста или историю попыток.</Card>
        </AppShell>
      </AuthGuard>
    );
  }

  return (
    <AuthGuard roles={["student"]}>
      <AppShell>
        <section className={styles.scoreGrid}>
          <Card title={`Итог теста #${data.test_id}`} subtitle="Результат и персональные рекомендации.">
            <div className={styles.scoreValue}>{accuracy.toFixed(1)}%</div>
            <p className="muted">
              Баллы: <b>{data.result.total_score}</b> / {data.result.max_score}
            </p>
            <p className="muted">
              Время: <b>{formatDuration(data.result.elapsed_seconds)}</b>
              {typeof data.result.time_limit_seconds === "number" ? ` / лимит ${formatDuration(data.result.time_limit_seconds)}` : ""}
            </p>
            <p className="muted">
              Предупреждений: <b>{data.result.warning_count}</b>
            </p>
            <div className={styles.badgeList}>
              {data.recommendation.weak_topics.map((topic) => (
                <Badge key={topic}>{topic}</Badge>
              ))}
            </div>
            {error && <div className="errorText">{error}</div>}
          </Card>

          <Card title="Recommendations" subtitle="Что повторить и какие задания выполнить дальше.">
            <p>{data.recommendation.advice_text}</p>
            <Button variant="secondary" disabled={busy} onClick={regenerate}>
              {busy ? "Обновляем задания..." : "Сгенерировать доп. задания"}
            </Button>
          </Card>
        </section>

        <Card title="Ошибки и объяснения" subtitle="Откройте вопрос, чтобы увидеть детали.">
          <Accordion items={accordionItems} />
        </Card>

        <Card title="Integrity Warnings" subtitle="События, зафиксированные во время прохождения теста.">
          {data.integrity_warnings.length === 0 ? (
            <p className="muted">Предупреждений не зафиксировано.</p>
          ) : (
            <div className={styles.taskGrid}>
              {data.integrity_warnings.map((item, index) => (
                <article className={styles.taskItem} key={`${item.type}-${item.at_seconds}-${index}`}>
                  <div className="inline">
                    <Badge variant="danger">{item.type}</Badge>
                    <Badge>t={formatDuration(item.at_seconds)}</Badge>
                    {item.question_id ? <Badge>Q{item.question_id}</Badge> : null}
                  </div>
                </article>
              ))}
            </div>
          )}
        </Card>

        <Card title="Дополнительные задания">
          <div className={styles.taskGrid}>
            {data.recommendation.generated_tasks.map((task, index) => (
              <article className={styles.taskItem} key={`${task.topic}-${index}`}>
                <div className="inline">
                  <Badge variant="info">{task.topic}</Badge>
                  <Badge>{task.difficulty}</Badge>
                </div>
                <p>{task.task}</p>
              </article>
            ))}
          </div>
        </Card>

        <Card>
          <div className="inline">
            <Link href="/test">Новый тест</Link>
            <span className="muted">|</span>
            <Link href="/history">История</Link>
          </div>
        </Card>
      </AppShell>
    </AuthGuard>
  );
}

function formatDuration(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds || 0));
  const minutes = Math.floor(safe / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (safe % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function sanitizeQuestionPrompt(prompt: string): string {
  return prompt.replace(/\s*\((вариант|нұсқа)\s*\d+\)\s*$/i, "").trim();
}
