"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { requestPasswordReset } from "@/lib/api";
import { checkEmail, type FieldHint } from "@/lib/registerValidation";
import { tr, useUiLanguage } from "@/lib/i18n";

import AuthHomeLink from "@/components/AuthHomeLink";
import { assetPaths } from "@/src/assets";
import styles from "@/app/auth.module.css";

export default function ForgotPasswordPage() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [email, setEmail] = useState("");
  const [hint, setHint] = useState<FieldHint | null>(null);
  const [touched, setTouched] = useState(false);

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    const lockClass = "auth-viewport-locked";
    document.documentElement.classList.add(lockClass);
    document.body.classList.add(lockClass);
    return () => {
      document.documentElement.classList.remove(lockClass);
      document.body.classList.remove(lockClass);
    };
  }, []);

  const validate = (rawEmail: string) => {
    const res = checkEmail(rawEmail);
    if (res.ok) return { ok: true as const, hint: null as FieldHint | null };
    return { ok: false as const, hint: res.hint };
  };

  const onBlurEmail = () => {
    const v = validate(email);
    setHint(v.hint);
    setTouched(true);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const v = validate(email);
      setHint(v.hint);
      setTouched(true);
      if (!v.ok) return;

      await requestPasswordReset({ email });
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось отправить запрос", "Сұранысты жіберу мүмкін болмады"));
    } finally {
      setLoading(false);
    }
  };

  const emailClass = !touched
    ? styles.input
    : hint
      ? `${styles.input} ${styles.inputInvalid}`
      : `${styles.input} ${styles.inputValid}`;

  return (
    <>
      <AuthHomeLink />
      <div className={styles.authSplit}>
        <section className={styles.brandPanel}>
          <img className={styles.brandLogo} src={assetPaths.logo.svg} alt="OKU" />
        </section>

        <section className={styles.formPanel}>
          <form className={styles.formCard} onSubmit={handleSubmit}>
            <h1 className={styles.title}>{t("Восстановление пароля", "Құпиясөзді қалпына келтіру")}</h1>
            <p className={styles.subtitle}>
              {t(
                "Введите адрес электронной почты. Мы отправим инструкции для восстановления.",
                "Электрондық пошта мекенжайын енгізіңіз. Біз қалпына келтіру нұсқауларын жібереміз.",
              )}
            </p>

            <label className={styles.label}>
              <span>{t("Почта", "Электрондық пошта")}</span>
              <input
                className={emailClass}
                onBlur={onBlurEmail}
                onChange={(e) => setEmail(e.target.value)}
                required
                type="email"
                value={email}
              />
            </label>

            {touched && hint ? <p className={styles.fieldHint}>{uiLanguage === "KZ" ? hint.kz : hint.ru}</p> : null}

            {error ? <p className={styles.error}>{error}</p> : null}

            {sent ? (
              <>
                <p className={styles.info}>
                  {t(
                    "Если аккаунт с такой почтой существует, мы отправили инструкции для восстановления.",
                    "Егер осы пошта арқылы аккаунт бар болса, біз қалпына келтіру нұсқауларын жібердік.",
                  )}
                </p>
                <Link className={styles.bottomLink} href="/login" style={{ marginTop: 8 }}>
                  {t("Перейти к входу", "Кіруге өту")}
                </Link>
              </>
            ) : (
              <>
                <button className={styles.primaryButton} disabled={loading} type="submit">
                  {loading ? t("Отправляем...", "Жіберіп жатырмыз...") : t("Отправить", "Жіберу")}
                </button>
                <p className={styles.bottomText}>
                  {t("Уже есть аккаунт?", "Аккаунт бар ма?")}{" "}
                  <Link className={styles.bottomLink} href="/login">
                    {t("Войти", "Кіру")}
                  </Link>
                </p>
              </>
            )}
          </form>
        </section>
      </div>
    </>
  );
}

