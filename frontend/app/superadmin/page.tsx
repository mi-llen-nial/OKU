"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import {
  createInstitutionAdminBootstrapInvite,
  createSuperadminInstitution,
  getSuperadminInstitutions,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { tr, useUiLanguage } from "@/lib/i18n";
import { toast } from "@/lib/toast";
import { InstitutionAdminBootstrapInviteResponse, SuperadminInstitutionListItem } from "@/lib/types";
import styles from "@/app/superadmin/page.module.css";

export default function SuperadminPage() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [loading, setLoading] = useState(true);
  const [institutions, setInstitutions] = useState<SuperadminInstitutionListItem[]>([]);
  const [name, setName] = useState("");
  const [selectedInstitutionId, setSelectedInstitutionId] = useState<number | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteNote, setInviteNote] = useState("");
  const [invite, setInvite] = useState<InstitutionAdminBootstrapInviteResponse | null>(null);
  const [syncing, setSyncing] = useState(false);

  const activeInstitutions = useMemo(
    () => institutions.filter((item) => item.is_active),
    [institutions],
  );

  const refresh = async () => {
    const token = getToken();
    if (!token) return;
    setSyncing(true);
    try {
      const payload = await getSuperadminInstitutions(token);
      setInstitutions(payload.institutions);
      if (!payload.institutions.some((item) => item.id === selectedInstitutionId)) {
        setSelectedInstitutionId(payload.institutions[0]?.id ?? null);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Не удалось загрузить учреждения.", "Оқу орындарын жүктеу мүмкін болмады."));
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
        const payload = await getSuperadminInstitutions(token);
        if (cancelled) return;
        setInstitutions(payload.institutions);
        setSelectedInstitutionId(payload.institutions[0]?.id ?? null);
      } catch (err) {
        if (!cancelled) {
          toast.error(err instanceof Error ? err.message : t("Не удалось загрузить учреждения.", "Оқу орындарын жүктеу мүмкін болмады."));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const createInstitution = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const token = getToken();
    if (!token) return;
    const normalized = name.trim();
    if (!normalized) return;
    try {
      await createSuperadminInstitution(token, { name: normalized });
      setName("");
      toast.success(t("Учреждение создано.", "Оқу орны құрылды."));
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Не удалось создать учреждение.", "Оқу орнын құру мүмкін болмады."));
    }
  };

  const createInvite = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const token = getToken();
    if (!token || !selectedInstitutionId) return;
    const email = inviteEmail.trim().toLowerCase();
    if (!email) return;
    try {
      const payload = await createInstitutionAdminBootstrapInvite(token, selectedInstitutionId, {
        email,
        note: inviteNote.trim() || undefined,
        expires_in_hours: 72,
      });
      setInvite(payload);
      toast.success(t("Приглашение создано.", "Шақыру жасалды."));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Не удалось создать приглашение.", "Шақыруды жасау мүмкін болмады."));
    }
  };

  return (
    <AuthGuard roles={["superadmin"]}>
      <AppShell>
        <div className={styles.page}>
          <header className={styles.header}>
            <h1>{t("Superadmin", "Superadmin")}</h1>
            <p className={styles.muted}>
              {t("Bootstrap учреждений и назначение первого администратора.", "Оқу орындарын bootstrap және алғашқы әкімшіні тағайындау.")}
            </p>
          </header>

          {loading ? <p className={styles.muted}>{t("Загрузка...", "Жүктелуде...")}</p> : null}

          <section className={styles.section}>
            <h2>{t("Создать учреждение", "Оқу орнын құру")}</h2>
            <form className={styles.inlineForm} onSubmit={createInstitution}>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={t("Название учреждения", "Оқу орнының атауы")}
                required
              />
              <Button type="submit">{t("Создать", "Құру")}</Button>
              <Button type="button" variant="ghost" onClick={() => void refresh()} disabled={syncing}>
                {syncing ? t("Обновляем...", "Жаңартылуда...") : t("Обновить", "Жаңарту")}
              </Button>
            </form>
          </section>

          <section className={styles.section}>
            <h2>{t("Учреждения", "Оқу орындары")}</h2>
            {activeInstitutions.length === 0 ? (
              <p className={styles.muted}>{t("Пока нет учреждений.", "Әзірге оқу орындары жоқ.")}</p>
            ) : (
              <div className={styles.grid}>
                {activeInstitutions.map((item) => (
                  <article key={item.id} className={styles.card}>
                    <strong>{item.name}</strong>
                    <span className={styles.muted}>#{item.id}</span>
                    <Button type="button" onClick={() => setSelectedInstitutionId(item.id)}>
                      {t("Выбрать", "Таңдау")}
                    </Button>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className={styles.section}>
            <h2>{t("Bootstrap первого institution_admin", "Алғашқы institution_admin bootstrap")}</h2>
            <p className={styles.muted}>
              {t("Создайте одноразовый токен и передайте его администратору учреждения.", "Бір реттік токен жасап, оны оқу орны әкімшісіне беріңіз.")}
            </p>
            <form className={styles.inlineForm} onSubmit={createInvite}>
              <input
                value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)}
                placeholder={t("Email будущего администратора", "Болашақ әкімшінің email")}
                type="email"
                required
              />
              <textarea
                value={inviteNote}
                onChange={(event) => setInviteNote(event.target.value)}
                placeholder={t("Заметка (опционально)", "Ескерту (міндетті емес)")}
                rows={1}
              />
              <Button type="submit" disabled={!selectedInstitutionId}>
                {selectedInstitutionId ? t("Создать приглашение", "Шақыру жасау") : t("Выберите учреждение", "Оқу орнын таңдаңыз")}
              </Button>
            </form>

            {invite ? (
              <div className={styles.row}>
                <div className={styles.tokenBox}>
                  {t("Токен:", "Токен:")} {invite.token}
                  <br />
                  {t("Ссылка:", "Сілтеме:")} {`/activate/institution-admin?token=${encodeURIComponent(invite.token)}&email=${encodeURIComponent(invite.email)}`}
                </div>
              </div>
            ) : null}
          </section>
        </div>
      </AppShell>
    </AuthGuard>
  );
}

