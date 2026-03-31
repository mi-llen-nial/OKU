"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import {
  assignTeacherToInstitutionGroup,
  createInstitutionGroup,
  decideInstitutionTeacherApplication,
  getAdminInstitutions,
  getInstitutionGroups,
  getInstitutionStaff,
  getInstitutionTeacherApplications,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { tr, useUiLanguage } from "@/lib/i18n";
import { toast } from "@/lib/toast";
import { InstitutionGroup, InstitutionListItem, InstitutionMember, TeacherApplication } from "@/lib/types";
import styles from "@/app/institution-admin/page.module.css";

export default function InstitutionAdminPage() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [institutions, setInstitutions] = useState<InstitutionListItem[]>([]);
  const [selectedInstitutionId, setSelectedInstitutionId] = useState<number | null>(null);
  const [applications, setApplications] = useState<TeacherApplication[]>([]);
  const [groups, setGroups] = useState<InstitutionGroup[]>([]);
  const [staff, setStaff] = useState<InstitutionMember[]>([]);
  const [newGroupName, setNewGroupName] = useState("");
  const [assignGroupId, setAssignGroupId] = useState<number>(0);
  const [assignTeacherMembershipId, setAssignTeacherMembershipId] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const resolveTeacherMembershipId = (member: InstitutionMember): number =>
    Number(member.teacher_membership_id || 0) > 0 ? Number(member.teacher_membership_id) : Number(member.id);

  const teacherMemberships = useMemo(
    () =>
      staff.filter(
        (item) =>
          item.roles.includes("teacher") &&
          item.statuses.includes("active") &&
          resolveTeacherMembershipId(item) > 0,
      ),
    [staff],
  );

  const refreshInstitutionData = async (institutionId: number) => {
    const token = getToken();
    if (!token) return;
    setSyncing(true);
    try {
      const [applicationsPayload, groupsPayload, staffPayload] = await Promise.all([
        getInstitutionTeacherApplications(token, institutionId),
        getInstitutionGroups(token, institutionId),
        getInstitutionStaff(token, institutionId),
      ]);
      setApplications(applicationsPayload);
      setGroups(groupsPayload);
      setStaff(staffPayload);
      if (!groupsPayload.some((group) => group.id === assignGroupId)) {
        setAssignGroupId(groupsPayload[0]?.id ?? 0);
      }
      const nextTeacherMembershipIds = new Set(
        staffPayload
          .filter((item) => item.roles.includes("teacher") && item.statuses.includes("active"))
          .map((item) => resolveTeacherMembershipId(item))
          .filter((value) => value > 0),
      );
      if (!nextTeacherMembershipIds.has(assignTeacherMembershipId)) {
        setAssignTeacherMembershipId(0);
      }
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : t("Не удалось загрузить данные учреждения.", "Оқу орнының деректерін жүктеу мүмкін болмады."),
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
        const institutionsPayload = await getAdminInstitutions(token);
        if (cancelled) return;
        setInstitutions(institutionsPayload);
        const firstInstitution = institutionsPayload[0];
        if (firstInstitution) {
          setSelectedInstitutionId(firstInstitution.id);
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
    void refreshInstitutionData(selectedInstitutionId);
  }, [selectedInstitutionId]);

  const handleApplicationDecision = async (applicationId: number, action: "approve" | "reject") => {
    const token = getToken();
    if (!token || !selectedInstitutionId) return;
    try {
      await decideInstitutionTeacherApplication(token, selectedInstitutionId, applicationId, { action });
      toast.success(
        action === "approve"
          ? t("Заявка одобрена.", "Өтінім мақұлданды.")
          : t("Заявка отклонена.", "Өтінім қабылданбады."),
      );
      await refreshInstitutionData(selectedInstitutionId);
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : t("Не удалось обработать заявку.", "Өтінімді өңдеу мүмкін болмады."),
      );
    }
  };

  const handleCreateGroup = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const token = getToken();
    if (!token || !selectedInstitutionId) return;
    const normalized = newGroupName.trim();
    if (!normalized) return;
    try {
      await createInstitutionGroup(token, selectedInstitutionId, normalized);
      setNewGroupName("");
      toast.success(t("Группа создана.", "Топ құрылды."));
      await refreshInstitutionData(selectedInstitutionId);
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : t("Не удалось создать группу.", "Топ құру мүмкін болмады."),
      );
    }
  };

  const handleAssignTeacher = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const token = getToken();
    if (!token || !selectedInstitutionId || assignGroupId <= 0 || assignTeacherMembershipId <= 0) return;
    try {
      await assignTeacherToInstitutionGroup(token, selectedInstitutionId, assignGroupId, assignTeacherMembershipId);
      toast.success(t("Преподаватель назначен.", "Оқытушы тағайындалды."));
      await refreshInstitutionData(selectedInstitutionId);
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : t("Не удалось назначить преподавателя.", "Оқытушыны тағайындау мүмкін болмады."),
      );
    }
  };

  return (
    <AuthGuard roles={["institution_admin"]}>
      <AppShell>
        <div className={styles.page}>
          <header className={styles.header}>
            <h1>{t("Управление учреждением", "Оқу орнын басқару")}</h1>
            <p>{t("Заявки преподавателей, группы и назначения.", "Оқытушы өтінімдері, топтар және тағайындаулар.")}</p>
          </header>

          {loading ? <p className={styles.muted}>{t("Загрузка...", "Жүктелуде...")}</p> : null}

          {!loading && institutions.length === 0 ? (
            <p className={styles.muted}>{t("Нет доступных учреждений.", "Қолжетімді оқу орындары жоқ.")}</p>
          ) : null}

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

          {selectedInstitutionId ? (
            <>
              <section className={styles.section}>
                <h2>{t("Заявки преподавателей", "Оқытушы өтінімдері")}</h2>
                {syncing ? <p className={styles.muted}>{t("Обновляем...", "Жаңартылуда...")}</p> : null}
                <div className={styles.grid}>
                  {applications.filter((item) => item.status === "pending").map((item) => (
                    <article key={item.id} className={styles.card}>
                      <h3>{item.full_name}</h3>
                      <p>{item.email}</p>
                      <p>{item.subject || t("Без предмета", "Пән көрсетілмеген")}</p>
                      <div className={styles.actions}>
                        <Button onClick={() => void handleApplicationDecision(item.id, "approve")}>
                          {t("Одобрить", "Мақұлдау")}
                        </Button>
                        <Button variant="ghost" onClick={() => void handleApplicationDecision(item.id, "reject")}>
                          {t("Отклонить", "Қабылдамау")}
                        </Button>
                      </div>
                    </article>
                  ))}
                </div>
                {applications.filter((item) => item.status === "pending").length === 0 ? (
                  <p className={styles.muted}>{t("Новых заявок нет.", "Жаңа өтінімдер жоқ.")}</p>
                ) : null}
              </section>

              <section className={styles.section}>
                <h2>{t("Группы", "Топтар")}</h2>
                <form className={styles.inlineForm} onSubmit={handleCreateGroup}>
                  <input
                    value={newGroupName}
                    onChange={(event) => setNewGroupName(event.target.value)}
                    placeholder={t("Название новой группы", "Жаңа топ атауы")}
                  />
                  <Button type="submit">{t("Создать", "Құру")}</Button>
                </form>
                <div className={styles.grid}>
                  {groups.map((group) => (
                    <article key={group.id} className={styles.card}>
                      <h3>{group.name}</h3>
                      <p>{t("Участников", "Қатысушылар")}: {group.members_count}</p>
                      <p>
                        {t("Преподаватели", "Оқытушылар")}:{" "}
                        {group.teachers.length > 0 ? group.teachers.map((teacher) => teacher.full_name || teacher.username).join(", ") : "—"}
                      </p>
                    </article>
                  ))}
                </div>
              </section>

              <section className={styles.section}>
                <h2>{t("Назначение преподавателя на группу", "Оқытушыны топқа тағайындау")}</h2>
                <form className={styles.inlineForm} onSubmit={handleAssignTeacher}>
                  <select value={assignGroupId} onChange={(event) => setAssignGroupId(Number(event.target.value))}>
                    <option value={0}>{t("Выберите группу", "Топты таңдаңыз")}</option>
                    {groups.map((group) => (
                      <option key={group.id} value={group.id}>
                        {group.name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={assignTeacherMembershipId}
                    onChange={(event) => setAssignTeacherMembershipId(Number(event.target.value))}
                  >
                    <option value={0}>{t("Выберите преподавателя", "Оқытушыны таңдаңыз")}</option>
                    {teacherMemberships.map((member) => (
                      <option key={`${member.user_id}:${resolveTeacherMembershipId(member)}`} value={resolveTeacherMembershipId(member)}>
                        {member.full_name || member.username}
                      </option>
                    ))}
                  </select>
                  <Button type="submit">{t("Назначить", "Тағайындау")}</Button>
                </form>
              </section>
            </>
          ) : null}
        </div>
      </AppShell>
    </AuthGuard>
  );
}
