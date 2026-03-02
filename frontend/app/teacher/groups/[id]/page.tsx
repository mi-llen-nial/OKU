"use client";

import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import {
  cancelTeacherInvitation,
  deleteTeacherGroup,
  getTeacherGroupMembers,
  getTeacherInvitations,
  removeTeacherGroupMember,
  sendTeacherInvitation,
  updateTeacherGroup,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { tr, useUiLanguage } from "@/lib/i18n";
import { TeacherGroupMembers, TeacherInvitation } from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/app/teacher/groups/[id]/group-detail.module.css";

const MAX_GROUP_MEMBERS = 5;

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
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [group, setGroup] = useState<TeacherGroupMembers | null>(null);
  const [invitations, setInvitations] = useState<TeacherInvitation[]>([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(true);
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [inviteUsername, setInviteUsername] = useState("");
  const [inviteLoading, setInviteLoading] = useState(false);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [settingsName, setSettingsName] = useState("");
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [deleteGroupLoading, setDeleteGroupLoading] = useState(false);
  const [memberToRemove, setMemberToRemove] = useState<{ studentId: number; name: string } | null>(null);
  const [removeLoading, setRemoveLoading] = useState(false);
  const [cancelingInvitationId, setCancelingInvitationId] = useState<number | null>(null);

  const groupInvitations = useMemo(
    () =>
      invitations
        .filter((item) => item.group_id === groupId && item.status === "pending")
        .slice(0, 8),
    [groupId, invitations],
  );
  const groupFull = Boolean(group && group.members.length >= MAX_GROUP_MEMBERS);

  const loadData = async (silent = false) => {
    const token = getToken();
    if (!token || !Number.isFinite(groupId)) return;

    if (!silent && !group) {
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
      setError(err instanceof Error ? err.message : t("Не удалось загрузить группу", "Топты жүктеу мүмкін болмады"));
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    loadData().catch((err) => {
      setLoading(false);
      setError(err instanceof Error ? err.message : t("Не удалось загрузить группу", "Топты жүктеу мүмкін болмады"));
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
    if (groupFull) {
      setError(t("В этой группе уже достигнут лимит участников.", "Бұл топта қатысушылар лимиті толды."));
      return;
    }

    const username = inviteUsername.trim();
    if (!username) {
      setError(t("Введите username ученика.", "Оқушының username-ын енгізіңіз."));
      return;
    }

    try {
      setInviteLoading(true);
      setError("");
      setSuccess("");
      await sendTeacherInvitation(token, { username, group_id: groupId });
      setInviteUsername("");
      setInviteModalOpen(false);
      setSuccess(t("Приглашение отправлено. После принятия ученик автоматически появится в группе.", "Шақыру жіберілді. Қабылдағаннан кейін оқушы топта автоматты түрде пайда болады."));
      await loadData(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось отправить приглашение", "Шақыру жіберу мүмкін болмады"));
    } finally {
      setInviteLoading(false);
    }
  };

  const removeMember = async () => {
    if (!memberToRemove) return;
    const token = getToken();
    if (!token || !Number.isFinite(groupId)) return;

    try {
      setRemoveLoading(true);
      setError("");
      setSuccess("");
      await removeTeacherGroupMember(token, groupId, memberToRemove.studentId);
      setSuccess(t("Ученик удален из группы.", "Оқушы топтан шығарылды."));
      setMemberToRemove(null);
      await loadData(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось удалить ученика", "Оқушыны шығару мүмкін болмады"));
    } finally {
      setRemoveLoading(false);
    }
  };

  const cancelInvitation = async (invitationId: number) => {
    const token = getToken();
    if (!token) return;
    try {
      setCancelingInvitationId(invitationId);
      setError("");
      setSuccess("");
      await cancelTeacherInvitation(token, invitationId);
      setSuccess(t("Приглашение отменено.", "Шақыру жойылды."));
      await loadData(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось отменить приглашение", "Шақыруды жою мүмкін болмады"));
    } finally {
      setCancelingInvitationId(null);
    }
  };

  const openSettings = () => {
    setSettingsName(group?.name || "");
    setSettingsModalOpen(true);
  };

  const saveSettings = async () => {
    const token = getToken();
    if (!token || !Number.isFinite(groupId) || !group) return;

    const nextName = settingsName.trim();
    if (!nextName) {
      setError(t("Введите название группы.", "Топ атауын енгізіңіз."));
      return;
    }

    if (nextName === group.name) {
      setSettingsModalOpen(false);
      return;
    }

    try {
      setSettingsLoading(true);
      setError("");
      setSuccess("");
      const payload = await updateTeacherGroup(token, groupId, { name: nextName });
      setGroup((prev) => (prev ? { ...prev, name: payload.name } : prev));
      setSuccess(t("Название группы обновлено.", "Топ атауы жаңартылды."));
      setSettingsModalOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось обновить группу", "Топты жаңарту мүмкін болмады"));
    } finally {
      setSettingsLoading(false);
    }
  };

  const removeGroup = async () => {
    const token = getToken();
    if (!token || !Number.isFinite(groupId)) return;

    try {
      setDeleteGroupLoading(true);
      setError("");
      setSuccess("");
      await deleteTeacherGroup(token, groupId);
      setSettingsModalOpen(false);
      router.push("/teacher");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось удалить группу", "Топты жою мүмкін болмады"));
    } finally {
      setDeleteGroupLoading(false);
    }
  };

  return (
    <AuthGuard roles={["teacher"]}>
      <AppShell>
        <div className={styles.page}>
          <header className={styles.header}>
            <div>
              <div className={styles.groupTitleRow}>
                <h2>{group?.name || t("Группа", "Топ")}</h2>
                <button
                  type="button"
                  className={styles.groupSettingsButton}
                  onClick={openSettings}
                  aria-label={t("Настройки группы", "Топ баптаулары")}
                >
                  <img className={styles.groupSettingsIcon} src={assetPaths.icons.groupEdit} alt="" aria-hidden="true" />
                </button>
              </div>
              <p>{t("Список участников и быстрый переход к аналитике ученика.", "Қатысушылар тізімі және оқушы аналитикасына жылдам өту.")}</p>
            </div>
            <Button onClick={() => setInviteModalOpen(true)} disabled={groupFull} className={styles.actionButton}>
              <img className={styles.actionIcon} src={assetPaths.icons.plus} alt="" aria-hidden="true" />
              <span>{t("Добавить ученика", "Оқушы қосу")}</span>
            </Button>
          </header>
          {group && (
            <p className="muted">
              {t("Участников", "Қатысушы")}: {group.members.length} / {MAX_GROUP_MEMBERS}
            </p>
          )}

          {loading && <p className="muted">{t("Загрузка...", "Жүктелуде...")}</p>}
          {error && <div className="errorText">{error}</div>}
          {success && <p className={styles.success}>{success}</p>}

          {!loading && group && (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <colgroup>
                  <col className={styles.colName} />
                  <col className={styles.colScore} />
                  <col className={styles.colWarnings} />
                  <col className={styles.colTopic} />
                  <col className={styles.colActivity} />
                  <col className={styles.colActions} />
                </colgroup>
                <thead>
                  <tr>
                    <th>{t("Имя", "Аты")}</th>
                    <th>{t("Успеваемость", "Үлгерім")}</th>
                    <th>{t("Предупреждения", "Ескертулер")}</th>
                    <th>{t("Слабая тема", "Әлсіз тақырып")}</th>
                    <th>{t("Активность", "Белсенділік")}</th>
                    <th className={styles.actionColumn} />
                  </tr>
                </thead>
                <tbody>
                  {group.members.map((member, index) => (
                    <tr key={member.student_id} className={styles.memberRow}>
                      <td>
                        <div className={styles.memberCell}>
                          <button
                            type="button"
                            className={styles.minusBtn}
                            onClick={() => setMemberToRemove({ studentId: member.student_id, name: member.full_name || member.username })}
                            aria-label={t("Удалить ученика", "Оқушыны өшіру")}
                          >
                            −
                          </button>
                          <span className={styles.rowIndex}>{index + 1}</span>
                          <span>{member.full_name || member.username}</span>
                        </div>
                      </td>
                      <td>{formatPercent(member.avg_percent)}</td>
                      <td>{member.warnings_count}</td>
                      <td>{member.weak_topic || "—"}</td>
                      <td>{formatActivity(member.last_activity_at, uiLanguage)}</td>
                      <td className={styles.rowActions}>
                        <button
                          type="button"
                          className={styles.openLink}
                          onClick={() => router.push(buildStudentAnalyticsHref(member.student_id, member.full_name || member.username))}
                        >
                          {t("Открыть", "Ашу")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!loading && group && group.members.length === 0 && (
            <p className="muted">{t("В этой группе пока нет учеников.", "Бұл топта әзірге оқушылар жоқ.")}</p>
          )}

          <section className={styles.invitationSection}>
            <h3>{t("Приглашения в группу", "Топқа шақырулар")}</h3>
            {groupInvitations.length === 0 ? (
              <div className={styles.emptyInvitations}>
                <img src={assetPaths.icons.soon} alt="" aria-hidden="true" />
                <p>{t("Активных приглашений нет", "Белсенді шақырулар жоқ")}</p>
              </div>
            ) : (
              <div className={styles.invitationList}>
                {groupInvitations.map((invitation) => (
                  <article className={styles.invitationCard} key={invitation.id}>
                    <div className={styles.invitationStudent}>
                      <img className={styles.invitationIcon} src={assetPaths.icons.student} alt={t("Ученик", "Оқушы")} />
                      <div>
                        <h4>{invitation.student_name || invitation.student_username}</h4>
                        <p>{statusLabel(invitation.status, uiLanguage)}</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      className={styles.invitationMinus}
                      onClick={() => cancelInvitation(invitation.id)}
                      disabled={cancelingInvitationId === invitation.id}
                      aria-label={t("Отменить приглашение", "Шақыруды жою")}
                    >
                      {cancelingInvitationId === invitation.id ? "…" : "−"}
                    </button>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>

        {settingsModalOpen && (
          <div className={styles.modalOverlay} onClick={() => setSettingsModalOpen(false)} role="presentation">
            <section className={styles.modal} onClick={(event) => event.stopPropagation()}>
              <button
                type="button"
                className={styles.close}
                onClick={() => setSettingsModalOpen(false)}
                aria-label={t("Закрыть", "Жабу")}
              >
                <X size={16} />
              </button>
              <h3>{t("Настройки группы", "Топ баптаулары")}</h3>
              <label>
                {t("Переименовать", "Атын өзгерту")}
                <input
                  maxLength={120}
                  value={settingsName}
                  onChange={(event) => setSettingsName(event.target.value)}
                />
              </label>
              <div className={styles.modalActions}>
                <Button block onClick={saveSettings} disabled={settingsLoading || deleteGroupLoading}>
                  {settingsLoading ? t("Сохраняем...", "Сақталуда...") : t("Готово", "Дайын")}
                </Button>
                <Button block variant="ghost" onClick={() => setSettingsModalOpen(false)} disabled={settingsLoading || deleteGroupLoading}>
                  {t("Отмена", "Бас тарту")}
                </Button>
              </div>
              <button
                type="button"
                className={styles.deleteGroupAction}
                onClick={removeGroup}
                disabled={settingsLoading || deleteGroupLoading}
              >
                <img src={assetPaths.icons.groupDelete} alt="" aria-hidden="true" />
                <span>{deleteGroupLoading ? t("Удаляем...", "Жойылуда...") : t("Удалить группу", "Топты жою")}</span>
              </button>
            </section>
          </div>
        )}

        {inviteModalOpen && (
          <div className={styles.modalOverlay} onClick={() => setInviteModalOpen(false)} role="presentation">
            <section className={styles.modal} onClick={(event) => event.stopPropagation()}>
              <button
                type="button"
                className={styles.close}
                onClick={() => setInviteModalOpen(false)}
                aria-label={t("Закрыть", "Жабу")}
              >
                <X size={16} />
              </button>
              <h3>{t("Добавить ученика в группу", "Оқушыны топқа қосу")}</h3>
              <p>{t("Введите username ученика. Он получит приглашение в разделе профиля.", "Оқушының username-ын енгізіңіз. Ол профиль бөлімінде шақыру алады.")}</p>
              <label>
                {t("Username ученика", "Оқушы username-ы")}
                <input
                  maxLength={25}
                  placeholder={t("например student_demo_1", "мысалы student_demo_1")}
                  value={inviteUsername}
                  onChange={(event) => setInviteUsername(event.target.value)}
                />
              </label>
              <div className={styles.modalActions}>
                <Button block onClick={sendInviteToGroup} disabled={inviteLoading}>
                  {inviteLoading ? t("Отправляем...", "Жіберілуде...") : t("Отправить приглашение", "Шақыру жіберу")}
                </Button>
                <Button block variant="ghost" onClick={() => setInviteModalOpen(false)}>{t("Отмена", "Бас тарту")}</Button>
              </div>
            </section>
          </div>
        )}

        {memberToRemove && (
          <div className={styles.modalOverlay} onClick={() => setMemberToRemove(null)} role="presentation">
            <section className={styles.modal} onClick={(event) => event.stopPropagation()}>
              <button
                type="button"
                className={styles.close}
                onClick={() => setMemberToRemove(null)}
                aria-label={t("Закрыть", "Жабу")}
              >
                <X size={16} />
              </button>
              <h3>{t("Удаление ученика", "Оқушыны өшіру")}</h3>
              <p>
                {t("Удалить ученика из группы?", "Оқушыны топтан өшіру керек пе?")}<br />
                <b>{memberToRemove.name}</b>
              </p>
              <div className={styles.modalActions}>
                <Button block onClick={removeMember} disabled={removeLoading}>
                  {removeLoading ? t("Удаляем...", "Өшірілуде...") : t("Удалить", "Өшіру")}
                </Button>
                <Button block variant="ghost" onClick={() => setMemberToRemove(null)}>
                  {t("Отмена", "Бас тарту")}
                </Button>
              </div>
            </section>
          </div>
        )}
      </AppShell>
    </AuthGuard>
  );
}

function statusLabel(status: TeacherInvitation["status"], language: "RU" | "KZ"): string {
  if (status === "accepted") return tr(language, "Принято", "Қабылданды");
  if (status === "declined") return tr(language, "Отклонено", "Қабылданбады");
  return tr(language, "Ожидает", "Күтілуде");
}

function formatPercent(value: number): string {
  const rounded = Number(value.toFixed(1));
  return `${rounded}%`;
}

function formatActivity(value: string | null | undefined, language: "RU" | "KZ"): string {
  if (!value) {
    return tr(language, "Нет данных", "Дерек жоқ");
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return tr(language, "Нет данных", "Дерек жоқ");
  }
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const dayMs = 24 * 60 * 60 * 1000;
  const diffDays = Math.round((startOfToday - startOfDate) / dayMs);
  if (diffDays <= 0) return tr(language, "Сегодня", "Бүгін");
  if (diffDays === 1) return tr(language, "Вчера", "Кеше");
  return date.toLocaleDateString(language === "KZ" ? "kk-KZ" : "ru-RU", {
    day: "2-digit",
    month: "2-digit",
  });
}
