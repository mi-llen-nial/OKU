"use client";

import { UsersRound, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import {
  createTeacherGroup,
  getTeacherInvitations,
  sendTeacherInvitation,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { TeacherInvitation } from "@/lib/types";
import styles from "@/app/teacher/create-group/create-group.module.css";

export default function CreateGroupPage() {
  const router = useRouter();
  const [groupName, setGroupName] = useState("");
  const [invitations, setInvitations] = useState<TeacherInvitation[]>([]);
  const [selectedStudents, setSelectedStudents] = useState<number[]>([]);
  const [inviteUsername, setInviteUsername] = useState("");
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const acceptedInvitations = useMemo(
    () => invitations.filter((item) => item.status === "accepted" && !item.group_id),
    [invitations],
  );

  const loadInvitations = async () => {
    const token = getToken();
    if (!token) return;
    const payload = await getTeacherInvitations(token);
    setInvitations(payload);
  };

  useEffect(() => {
    loadInvitations().catch((err) => {
      setError(err instanceof Error ? err.message : "Не удалось загрузить приглашения");
    });
  }, []);

  const sendInvite = async () => {
    const token = getToken();
    if (!token) return;

    const username = inviteUsername.trim();
    if (!username) {
      setError("Введите username ученика.");
      return;
    }

    try {
      setLoading(true);
      setError("");
      setSuccess("");
      await sendTeacherInvitation(token, { username });
      setInviteUsername("");
      setInviteModalOpen(false);
      setSuccess("Приглашение отправлено.");
      await loadInvitations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить приглашение");
    } finally {
      setLoading(false);
    }
  };

  const submitGroup = async () => {
    const token = getToken();
    if (!token) return;
    const name = groupName.trim();
    if (!name) {
      setError("Укажите название группы.");
      return;
    }

    try {
      setLoading(true);
      setError("");
      setSuccess("");
      const group = await createTeacherGroup(token, {
        name,
        student_ids: selectedStudents,
      });
      router.push(`/teacher/groups/${group.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать группу");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthGuard roles={["teacher"]}>
      <AppShell>
        <div className={styles.page}>
          <section className={styles.section}>
            <header className={styles.header}>
              <h2>Создать группу</h2>
              <p>Добавьте учеников через приглашения и сформируйте группу.</p>
            </header>

            <div className={styles.form}>
              <label>
                Название группы
                <input
                  maxLength={120}
                  onChange={(event) => setGroupName(event.target.value)}
                  placeholder="Например: Программисты 23-1"
                  value={groupName}
                />
              </label>

              <div className={styles.actions}>
                <Button onClick={() => setInviteModalOpen(true)}>Добавить ученика</Button>
                <Button variant="secondary" onClick={submitGroup} disabled={loading}>
                  {loading ? "Сохраняем..." : "Создать группу"}
                </Button>
              </div>
            </div>
          </section>

          <section className={styles.section}>
            <header className={styles.header}>
              <h3>Принятые приглашения</h3>
              <p>Только эти ученики могут быть добавлены в новую группу.</p>
            </header>

            <div className={styles.inviteGrid}>
              {acceptedInvitations.map((item) => {
                const checked = selectedStudents.includes(item.student_id);
                return (
                  <label className={styles.inviteCard} key={item.id}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        if (event.target.checked) {
                          setSelectedStudents((prev) => [...prev, item.student_id]);
                        } else {
                          setSelectedStudents((prev) => prev.filter((id) => id !== item.student_id));
                        }
                      }}
                    />
                    <UsersRound size={24} className={styles.icon} />
                    <div>
                      <h4>{item.student_name || item.student_username}</h4>
                      <p>@{item.student_username}</p>
                    </div>
                  </label>
                );
              })}
            </div>

            {acceptedInvitations.length === 0 && (
              <p className="muted">Пока нет принятых приглашений.</p>
            )}
          </section>

          <section className={styles.section}>
            <header className={styles.header}>
              <h3>Все приглашения</h3>
            </header>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Ученик</th>
                    <th>Username</th>
                    <th>Статус</th>
                    <th>Дата</th>
                  </tr>
                </thead>
                <tbody>
                  {invitations.map((item) => (
                    <tr key={item.id}>
                      <td>{item.student_name || item.student_username}</td>
                      <td>@{item.student_username}</td>
                      <td>
                        <span className={`${styles.status} ${styles[item.status]}`}>{statusLabel(item.status)}</span>
                      </td>
                      <td>{new Date(item.created_at).toLocaleDateString("ru-RU")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {error && <div className="errorText">{error}</div>}
          {success && <div className={styles.success}>{success}</div>}
        </div>

        {inviteModalOpen && (
          <div className={styles.modalOverlay} onClick={() => setInviteModalOpen(false)} role="presentation">
            <section className={styles.modal} onClick={(event) => event.stopPropagation()}>
              <button
                type="button"
                className={styles.close}
                onClick={() => setInviteModalOpen(false)}
                aria-label="Закрыть"
              >
                <X size={16} />
              </button>
              <h3>Пригласить ученика</h3>
              <p>Введите username ученика, чтобы отправить приглашение.</p>
              <label>
                Username ученика
                <input
                  maxLength={25}
                  placeholder="например student_demo_1"
                  value={inviteUsername}
                  onChange={(event) => setInviteUsername(event.target.value)}
                />
              </label>
              <div className={styles.modalActions}>
                <Button onClick={sendInvite} disabled={loading}>Отправить приглашение</Button>
                <Button variant="ghost" onClick={() => setInviteModalOpen(false)}>Отмена</Button>
              </div>
            </section>
          </div>
        )}
      </AppShell>
    </AuthGuard>
  );
}

function statusLabel(status: TeacherInvitation["status"]): string {
  if (status === "accepted") return "Принято";
  if (status === "declined") return "Отклонено";
  return "Ожидает";
}
