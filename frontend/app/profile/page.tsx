"use client";

import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import { getMyProfile, respondInvitation } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { ProfileData, ProfileInvitation } from "@/lib/types";
import styles from "@/app/profile/profile.module.css";

export default function ProfilePage() {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState<number | null>(null);

  const loadProfile = async () => {
    const token = getToken();
    if (!token) return;
    const payload = await getMyProfile(token);
    setProfile(payload);
  };

  useEffect(() => {
    let cancelled = false;
    let intervalId: number | null = null;
    (async () => {
      try {
        setLoading(true);
        setError("");
        const token = getToken();
        if (!token) return;
        const payload = await getMyProfile(token);
        if (!cancelled) {
          setProfile(payload);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Не удалось загрузить профиль");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }

      intervalId = window.setInterval(async () => {
        if (cancelled) return;
        const token = getToken();
        if (!token) return;
        try {
          const payload = await getMyProfile(token);
          if (!cancelled) {
            setProfile(payload);
          }
        } catch {
          // Silent polling errors: keep UI stable.
        }
      }, 3000);
    })();
    return () => {
      cancelled = true;
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, []);

  const handleInvitation = async (invitation: ProfileInvitation, action: "accept" | "decline") => {
    const token = getToken();
    if (!token) return;
    try {
      setUpdatingId(invitation.id);
      setError("");
      await respondInvitation(token, invitation.id, action);
      await loadProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось обновить приглашение");
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <AuthGuard>
      <AppShell>
        <div className={styles.page}>
          <section className={styles.section}>
            <header className={styles.header}>
              <h2>Профиль</h2>
              <p>Основная информация вашего аккаунта.</p>
            </header>

            {loading && <p className="muted">Загрузка...</p>}
            {error && <div className="errorText">{error}</div>}

            {profile && (
              <div className={styles.infoGrid}>
                <article className={styles.infoCard}>
                  <h3>Пользователь</h3>
                  <p><b>Имя:</b> {profile.full_name || "—"}</p>
                  <p><b>Username:</b> @{profile.username}</p>
                  <p><b>Роль:</b> {profile.role === "teacher" ? "Преподаватель" : "Студент"}</p>
                </article>
                <article className={styles.infoCard}>
                  <h3>Обучение</h3>
                  <p><b>Почта:</b> {profile.email}</p>
                  <p><b>Язык:</b> {profile.preferred_language || "—"}</p>
                  <p><b>Статус:</b> {educationLabel(profile.education_level)}</p>
                  <p><b>Направление:</b> {profile.direction || "—"}</p>
                  <p><b>Группа:</b> {profile.group_name || "Не назначена"}</p>
                </article>
              </div>
            )}
          </section>

          <section className={styles.section}>
            <header className={styles.header}>
              <h3>Приглашения</h3>
              <p>
                {profile?.role === "teacher"
                  ? "Статусы приглашений, которые вы отправили ученикам."
                  : "Здесь отображаются приглашения от преподавателей."}
              </p>
              <div className={styles.actions}>
                <Button variant="ghost" onClick={loadProfile}>
                  Обновить
                </Button>
              </div>
            </header>

            {profile && profile.invitations.length > 0 ? (
              <div className={styles.invitationList}>
                {profile.invitations.map((invitation) => (
                  <article className={styles.invitationCard} key={invitation.id}>
                    <div className={styles.invitationMeta}>
                      <p className={styles.teacherName}>
                        {profile.role === "teacher" ? `Ученик: ${invitation.teacher_name}` : invitation.teacher_name}
                      </p>
                      <span className={`${styles.status} ${styles[invitation.status]}`}>{statusLabel(invitation.status)}</span>
                    </div>
                    <p className={styles.invitationDate}>
                      Отправлено: {new Date(invitation.created_at).toLocaleString("ru-RU")}
                    </p>
                    {invitation.group_name && (
                      <p className={styles.invitationDate}>
                        Группа: {invitation.group_name}
                      </p>
                    )}
                    {invitation.status === "pending" && profile.role === "student" && (
                      <div className={styles.actions}>
                        <Button
                          onClick={() => handleInvitation(invitation, "accept")}
                          disabled={updatingId === invitation.id}
                        >
                          Принять
                        </Button>
                        <Button
                          variant="secondary"
                          onClick={() => handleInvitation(invitation, "decline")}
                          disabled={updatingId === invitation.id}
                        >
                          Отклонить
                        </Button>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted">Приглашений пока нет.</p>
            )}
          </section>
        </div>
      </AppShell>
    </AuthGuard>
  );
}

function educationLabel(value?: string | null): string {
  if (value === "school") return "Школьник";
  if (value === "college") return "Студент колледжа";
  if (value === "university") return "Студент университета";
  return "—";
}

function statusLabel(value: ProfileInvitation["status"]): string {
  if (value === "accepted") return "Принято";
  if (value === "declined") return "Отклонено";
  return "Ожидает ответа";
}
