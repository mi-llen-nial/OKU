"use client";

import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import {
  getTeacherGroupMembers,
  getTeacherInvitations,
  sendTeacherInvitation,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { TeacherGroupMembers, TeacherInvitation } from "@/lib/types";
import styles from "@/app/teacher/groups/[id]/group-detail.module.css";

function buildStudentAnalyticsHref(studentId: number, studentName?: string) {
  const params = new URLSearchParams();
  const normalizedName = (studentName || "").trim();
  if (normalizedName) {
    params.set("name", normalizedName);
  }
  const query = params.toString();
  return query ? `/teacher/students/${studentId}?${query}` : `/teacher/students/${studentId}`;
}

export default function TeacherGroupDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const groupId = Number(params.id);

  const [group, setGroup] = useState<TeacherGroupMembers | null>(null);
  const [invitations, setInvitations] = useState<TeacherInvitation[]>([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(true);
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [inviteUsername, setInviteUsername] = useState("");
  const [inviteLoading, setInviteLoading] = useState(false);

  const groupInvitations = useMemo(
    () => invitations.filter((item) => item.group_id === groupId).slice(0, 8),
    [groupId, invitations],
  );

  const loadData = async (silent = false) => {
    const token = getToken();
    if (!token || !Number.isFinite(groupId)) return;

    if (!silent) {
      setLoading(true);
    }
    try {
      const [membersPayload, invitationsPayload] = await Promise.all([
        getTeacherGroupMembers(token, groupId),
        getTeacherInvitations(token),
      ]);
      setGroup(membersPayload);
      setInvitations(invitationsPayload);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить группу");
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    loadData().catch((err) => {
      setLoading(false);
      setError(err instanceof Error ? err.message : "Не удалось загрузить группу");
    });

    const timer = window.setInterval(() => {
      loadData(true).catch(() => undefined);
    }, 12000);

    return () => {
      window.clearInterval(timer);
    };
  }, [groupId]);

  const sendInviteToGroup = async () => {
    const token = getToken();
    if (!token || !Number.isFinite(groupId)) return;

    const username = inviteUsername.trim();
    if (!username) {
      setError("Введите username ученика.");
      return;
    }

    try {
      setInviteLoading(true);
      setError("");
      setSuccess("");
      await sendTeacherInvitation(token, { username, group_id: groupId });
      setInviteUsername("");
      setInviteModalOpen(false);
      setSuccess("Приглашение отправлено. После принятия ученик автоматически появится в группе.");
      await loadData(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить приглашение");
    } finally {
      setInviteLoading(false);
    }
  };

  return (
    <AuthGuard roles={["teacher"]}>
      <AppShell>
        <div className={styles.page}>
          <header className={styles.header}>
            <div>
              <h2>{group?.name || "Группа"}</h2>
              <p>Список участников и быстрый переход к аналитике ученика.</p>
            </div>
            <Button onClick={() => setInviteModalOpen(true)}>Добавить ученика</Button>
          </header>

          {loading && <p className="muted">Загрузка...</p>}
          {error && <div className="errorText">{error}</div>}
          {success && <p className={styles.success}>{success}</p>}

          {!loading && group && (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Ученик</th>
                    <th>Username</th>
                    <th>Тестов</th>
                    <th>Средний балл</th>
                    <th>Предупреждения</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {group.members.map((member) => (
                    <tr key={member.student_id}>
                      <td>{member.full_name || member.username}</td>
                      <td>@{member.username}</td>
                      <td>{member.tests_count}</td>
                      <td>{member.avg_percent}%</td>
                      <td>{member.warnings_count}</td>
                      <td>
                        <Button
                          variant="secondary"
                          onClick={() => router.push(buildStudentAnalyticsHref(member.student_id, member.full_name || member.username))}
                        >
                          Открыть
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!loading && group && group.members.length === 0 && (
            <p className="muted">В этой группе пока нет учеников.</p>
          )}

          <section className={styles.invitationSection}>
            <h3>Приглашения в группу</h3>
            {groupInvitations.length === 0 ? (
              <p className="muted">Пока приглашений для этой группы нет.</p>
            ) : (
              <div className={styles.invitationList}>
                {groupInvitations.map((invitation) => (
                  <article className={styles.invitationCard} key={invitation.id}>
                    <div>
                      <h4>{invitation.student_name || invitation.student_username}</h4>
                      <p>@{invitation.student_username}</p>
                    </div>
                    <span className={`${styles.status} ${styles[invitation.status]}`}>{statusLabel(invitation.status)}</span>
                  </article>
                ))}
              </div>
            )}
          </section>
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
              <h3>Добавить ученика в группу</h3>
              <p>Введите username ученика. Он получит приглашение в разделе профиля.</p>
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
                <Button onClick={sendInviteToGroup} disabled={inviteLoading}>
                  {inviteLoading ? "Отправляем..." : "Отправить приглашение"}
                </Button>
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
