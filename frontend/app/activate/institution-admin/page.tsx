"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { acceptInstitutionAdminBootstrap } from "@/lib/api";
import { saveSession } from "@/lib/auth";
import { tr, useUiLanguage } from "@/lib/i18n";
import { toast } from "@/lib/toast";
import AuthHomeLink from "@/components/AuthHomeLink";
import styles from "@/app/auth.module.css";

export default function ActivateInstitutionAdminPage() {
  const router = useRouter();
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setToken((params.get("token") || "").trim());
    setEmail((params.get("email") || "").trim().toLowerCase());
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const response = await acceptInstitutionAdminBootstrap({
        token,
        email,
        full_name: fullName,
        username,
        password,
      });
      saveSession(response, { rememberMe: true });
      toast.success(t("Доступ активирован.", "Қолжетімділік белсендірілді."));
      router.push("/institution-admin");
    } catch (err) {
      const message = err instanceof Error ? err.message : t("Не удалось активировать доступ.", "Қолжетімділікті белсендіру мүмкін болмады.");
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <AuthHomeLink />
      <div className={styles.authSplit}>
      <section className={styles.formPanel}>
        <form className={styles.formCard} onSubmit={handleSubmit}>
          <h1 className={styles.title}>{t("Активация администратора учреждения", "Оқу орны әкімшісін белсендіру")}</h1>
          <p className={styles.subtitle}>
            {t("Введите токен приглашения и создайте аккаунт.", "Шақыру токенін енгізіп, аккаунт жасаңыз.")}
          </p>

          <label className={styles.label}>
            <span>{t("Токен", "Токен")}</span>
            <input className={styles.input} value={token} onChange={(e) => setToken(e.target.value)} required />
          </label>

          <label className={styles.label}>
            <span>{t("Почта", "Электрондық пошта")}</span>
            <input
              className={styles.input}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              type="email"
            />
          </label>

          <label className={styles.label}>
            <span>{t("ФИО", "Аты-жөні")}</span>
            <input className={styles.input} value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </label>

          <label className={styles.label}>
            <span>{t("Имя пользователя", "Пайдаланушы аты")}</span>
            <input className={styles.input} value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>

          <label className={styles.label}>
            <span>{t("Пароль", "Құпиясөз")}</span>
            <input
              className={styles.input}
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              type="password"
            />
          </label>

          {error ? <p className={styles.error}>{error}</p> : null}

          <button className={styles.primaryButton} disabled={loading} type="submit">
            {loading ? t("Активируем...", "Белсендірілуде...") : t("Активировать", "Белсендіру")}
          </button>

          <p className={styles.bottomText}>
            <Link className={styles.bottomLink} href="/login">
              {t("Войти", "Кіру")}
            </Link>
          </p>
        </form>
      </section>
    </div>
    </>
  );
}

