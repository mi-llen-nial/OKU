"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { login } from "@/lib/api";
import { isRememberMeEnabled, saveSession } from "@/lib/auth";
import { resolveRoleHome } from "@/lib/navigation";
import { tr, useUiLanguage } from "@/lib/i18n";
import AuthHomeLink from "@/components/AuthHomeLink";
import { assetPaths } from "@/src/assets";
import styles from "@/app/auth.module.css";

export default function LoginPage() {
  const router = useRouter();
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const lockClass = "auth-viewport-locked";
    document.documentElement.classList.add(lockClass);
    document.body.classList.add(lockClass);
    setRememberMe(isRememberMeEnabled());

    return () => {
      document.documentElement.classList.remove(lockClass);
      document.body.classList.remove(lockClass);
    };
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await login({ email, password, remember_me: rememberMe });
      saveSession(response, { rememberMe });
      const rawNext =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search).get("next")?.trim() || ""
          : "";
      const safeNext = rawNext.startsWith("/") && !rawNext.startsWith("//") ? rawNext : "";
      router.push(safeNext || resolveRoleHome(response.user.role));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось выполнить вход", "Кіру орындалмады"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <AuthHomeLink />
      <div className={styles.authSplit}>
      <section className={styles.brandPanel}>
        <img className={styles.brandLogo} src={assetPaths.logo.svg} alt="OKU" />
      </section>
      <section className={styles.formPanel}>
        <form className={styles.formCard} onSubmit={handleSubmit}>
          <h1 className={styles.title}>{t("Вход", "Кіру")}</h1>
          <p className={styles.subtitle}>
            {t("Используйте аккаунт студента или преподавателя", "Оқушы немесе оқытушы аккаунтын қолданыңыз")}
          </p>

          <label className={styles.label}>
            <span>{t("Почта", "Электрондық пошта")}</span>
            <input
              className={styles.input}
              onChange={(e) => setEmail(e.target.value)}
              required
              type="email"
              value={email}
            />
          </label>

          <label className={styles.label}>
            <span>{t("Пароль", "Құпиясөз")}</span>
            <input
              className={styles.input}
              minLength={6}
              onChange={(e) => setPassword(e.target.value)}
              required
              type="password"
              value={password}
            />
          </label>

          <div className={styles.forgotRow}>
            <Link className={styles.forgotLink} href="/forgot-password">
              {t("Забыли пароль?", "Құпиясөзді ұмыттыңыз ба?")}
            </Link>
          </div>

          <label className={styles.rememberRow}>
            <input
              checked={rememberMe}
              onChange={(event) => setRememberMe(event.target.checked)}
              type="checkbox"
            />
            <span>{t("Запомнить меня", "Мені есте сақтау")}</span>
          </label>

          {error ? <p className={styles.error}>{error}</p> : null}

          <button className={styles.primaryButton} disabled={loading} type="submit">
            {loading ? t("Выполняем вход...", "Кіру орындалып жатыр...") : t("Войти", "Кіру")}
          </button>

          <p className={styles.bottomText}>
            {t("Нет аккаунта?", "Аккаунт жоқ па?")}{" "}
            <Link className={styles.bottomLink} href="/register">
              {t("Регистрация", "Тіркелу")}
            </Link>
          </p>
        </form>
      </section>
    </div>
    </>
  );
}
