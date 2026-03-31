"use client";

import { FormEvent, useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import {
  getMethodistInstitutions,
  getMethodistReviewDetails,
  getMethodistReviewQueue,
  submitMethodistReviewDecision,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { tr, useUiLanguage } from "@/lib/i18n";
import { toast } from "@/lib/toast";
import { InstitutionListItem, ReviewDetails, ReviewQueueItem, TestModerationStatus } from "@/lib/types";
import styles from "@/app/methodist/page.module.css";

function moderationLabel(status: TestModerationStatus, language: "RU" | "KZ"): string {
  const t = (ru: string, kz: string) => tr(language, ru, kz);
  if (status === "submitted_for_review") return t("На проверке", "Тексеруде");
  if (status === "in_review") return t("В работе", "Жұмыста");
  if (status === "needs_revision") return t("Нужны доработки", "Түзету керек");
  if (status === "approved") return t("Одобрено", "Мақұлданды");
  if (status === "rejected") return t("Отклонено", "Қабылданбады");
  if (status === "archived") return t("Архив", "Мұрағат");
  return t("Черновик", "Черновик");
}

export default function MethodistPage() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [institutions, setInstitutions] = useState<InstitutionListItem[]>([]);
  const [selectedInstitutionId, setSelectedInstitutionId] = useState<number | null>(null);
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [selectedTestId, setSelectedTestId] = useState<number | null>(null);
  const [details, setDetails] = useState<ReviewDetails | null>(null);
  const [decisionStatus, setDecisionStatus] = useState<"approved" | "rejected" | "needs_revision">("approved");
  const [decisionComment, setDecisionComment] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const refreshQueue = async (institutionId: number) => {
    const token = getToken();
    if (!token) return;
    setSyncing(true);
    try {
      const queuePayload = await getMethodistReviewQueue(token, institutionId);
      setQueue(queuePayload);
      if (!queuePayload.some((item) => item.test_id === selectedTestId)) {
        setSelectedTestId(queuePayload[0]?.test_id ?? null);
        setDetails(null);
      }
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : t("Не удалось загрузить очередь модерации.", "Модерация кезегін жүктеу мүмкін болмады."),
      );
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const institutionsPayload = await getMethodistInstitutions(token);
        if (cancelled) return;
        setInstitutions(institutionsPayload);
        if (institutionsPayload[0]) {
          setSelectedInstitutionId(institutionsPayload[0].id);
          await refreshQueue(institutionsPayload[0].id);
        }
      } catch (err) {
        if (!cancelled) {
          toast.error(
            err instanceof Error
              ? err.message
              : t("Не удалось загрузить учреждения.", "Оқу орындарын жүктеу мүмкін болмады."),
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedInstitutionId) return;
    void refreshQueue(selectedInstitutionId);
  }, [selectedInstitutionId]);

  useEffect(() => {
    const token = getToken();
    if (!token || !selectedInstitutionId || !selectedTestId) return;
    let cancelled = false;
    (async () => {
      try {
        const payload = await getMethodistReviewDetails(token, selectedInstitutionId, selectedTestId);
        if (cancelled) return;
        setDetails(payload);
      } catch (err) {
        if (!cancelled) {
          toast.error(
            err instanceof Error
              ? err.message
              : t("Не удалось открыть тест на модерацию.", "Тесті модерацияға ашу мүмкін болмады."),
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedInstitutionId, selectedTestId]);

  const handleDecisionSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const token = getToken();
    if (!token || !selectedInstitutionId || !selectedTestId) return;
    try {
      await submitMethodistReviewDecision(token, selectedInstitutionId, selectedTestId, {
        status: decisionStatus,
        comment: decisionComment.trim() || undefined,
      });
      toast.success(t("Решение сохранено.", "Шешім сақталды."));
      setDecisionComment("");
      await refreshQueue(selectedInstitutionId);
      const payload = await getMethodistReviewDetails(token, selectedInstitutionId, selectedTestId);
      setDetails(payload);
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : t("Не удалось сохранить решение.", "Шешімді сақтау мүмкін болмады."),
      );
    }
  };

  return (
    <AuthGuard roles={["methodist"]}>
      <AppShell>
        <div className={styles.page}>
          <header className={styles.header}>
            <h1>{t("Модерация тестов", "Тест модерациясы")}</h1>
            <p>{t("Проверка тестов преподавателей вашего учреждения.", "Оқу орныңыздағы оқытушы тесттерін тексеру.")}</p>
          </header>

          {loading ? <p className={styles.muted}>{t("Загрузка...", "Жүктелуде...")}</p> : null}

          {institutions.length > 0 ? (
            <div className={styles.institutions}>
              {institutions.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`${styles.institutionButton} ${selectedInstitutionId === item.id ? styles.institutionButtonActive : ""}`}
                  onClick={() => setSelectedInstitutionId(item.id)}
                >
                  {item.name}
                </button>
              ))}
            </div>
          ) : null}

          <section className={styles.section}>
            <h2>{t("Очередь", "Кезек")}</h2>
            {syncing ? <p className={styles.muted}>{t("Обновляем...", "Жаңартылуда...")}</p> : null}
            <div className={styles.queue}>
              {queue.map((item) => (
                <button
                  key={item.test_id}
                  type="button"
                  className={`${styles.queueItem} ${selectedTestId === item.test_id ? styles.queueItemActive : ""}`}
                  onClick={() => setSelectedTestId(item.test_id)}
                >
                  <strong>{item.title}</strong>
                  <span>{item.teacher_name}</span>
                  <span>{moderationLabel(item.moderation_status, uiLanguage)}</span>
                </button>
              ))}
            </div>
            {!syncing && queue.length === 0 ? (
              <p className={styles.muted}>{t("Очередь пуста.", "Кезек бос.")}</p>
            ) : null}
          </section>

          {details ? (
            <section className={styles.section}>
              <h2>{details.title}</h2>
              <p className={styles.muted}>
                {t("Преподаватель", "Оқытушы")}: {details.teacher_name} · {t("Версия", "Нұсқа")} {details.current_draft_version}
              </p>
              <ul className={styles.questions}>
                {details.questions.map((item) => (
                  <li key={item.id}>
                    {item.order_index}. {item.prompt}
                  </li>
                ))}
              </ul>
              <form className={styles.decisionForm} onSubmit={handleDecisionSubmit}>
                <select value={decisionStatus} onChange={(event) => setDecisionStatus(event.target.value as "approved" | "rejected" | "needs_revision")}>
                  <option value="approved">{t("Одобрить", "Мақұлдау")}</option>
                  <option value="needs_revision">{t("На доработку", "Түзетуге жіберу")}</option>
                  <option value="rejected">{t("Отклонить", "Қабылдамау")}</option>
                </select>
                <textarea
                  placeholder={t("Комментарий (опционально)", "Пікір (міндетті емес)")}
                  value={decisionComment}
                  onChange={(event) => setDecisionComment(event.target.value)}
                />
                <Button type="submit">{t("Сохранить решение", "Шешімді сақтау")}</Button>
              </form>
            </section>
          ) : null}
        </div>
      </AppShell>
    </AuthGuard>
  );
}
