"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { confirmPasswordReset } from "@/lib/api";
import { checkPassword, checkPasswordConfirm, type FieldHint } from "@/lib/registerValidation";
import { tr, useUiLanguage } from "@/lib/i18n";

import AuthHomeLink from "@/components/AuthHomeLink";
import { assetPaths } from "@/src/assets";
import styles from "@/app/auth.module.css";

export default function ResetPasswordPage() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);
  const searchParams = useSearchParams();

  const token = useMemo(() => (searchParams.get("token") || "").trim(), [searchParams]);

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [newHint, setNewHint] = useState<FieldHint | null>(null);
  const [confirmHint, setConfirmHint] = useState<FieldHint | null>(null);
  const [touched, setTouched] = useState(false);

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const lockClass = "auth-viewport-locked";
    document.documentElement.classList.add(lockClass);
    document.body.classList.add(lockClass);
    return () => {
      document.documentElement.classList.remove(lockClass);
      document.body.classList.remove(lockClass);
    };
  }, []);

  const passwordClass = !touched
    ? styles.input
    : newHint
      ? `${styles.input} ${styles.inputInvalid}`
      : `${styles.input} ${styles.inputValid}`;

  const confirmClass = !touched
    ? styles.input
    : confirmHint
      ? `${styles.input} ${styles.inputInvalid}`
      : `${styles.input} ${styles.inputValid}`;

  const pickHint = (h: FieldHint | null) => (h ? (uiLanguage === "KZ" ? h.kz : h.ru) : "");

  const validateAll = () => {
    const p = checkPassword(newPassword);
    const c = checkPasswordConfirm(newPassword, confirmPassword);
    if (!p.ok) setNewHint(p.hint);
    else setNewHint(null);
    if (!c.ok) setConfirmHint(c.hint);
    else setConfirmHint(null);

    const ok = p.ok && c.ok;
    return ok;
  };

  const onBlur = () => {
    setTouched(true);
    validateAll();
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      setTouched(true);
      const ok = validateAll();
      if (!ok) return;

      if (!token) {
        setError(t("Ссылка для восстановления недействительна или отсутствует.", "Қалпына келтіру сілтемесі жарамсыз немесе жоқ."));
        return;
      }

      await confirmPasswordReset({
        token,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });

      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось обновить пароль", "Құпиясөзді жаңарту мүмкін болмады"));
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
            <h1 className={styles.title}>{t("Новый пароль", "Жаңа құпиясөз")}</h1>
            <p className={styles.subtitle}>
              {t(
                "Введите новый пароль и подтвердите его. После этого вы сможете войти снова.",
                "Жаңа құпиясөз енгізіп, оны растаңыз. Содан кейін қайта кіре аласыз.",
              )}
            </p>

            {!done ? (
              <>
                <label className={styles.label}>
                  <span>{t("Новый пароль", "Жаңа құпиясөз")}</span>
                  <input
                    className={passwordClass}
                    onBlur={onBlur}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    type="password"
                    value={newPassword}
                  />
                </label>
                {touched && newHint ? <p className={styles.fieldHint}>{pickHint(newHint)}</p> : null}

                <label className={styles.label}>
                  <span>{t("Подтверждение пароля", "Құпиясөзді растау")}</span>
                  <input
                    className={confirmClass}
                    onBlur={onBlur}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    type="password"
                    value={confirmPassword}
                  />
                </label>
                {touched && confirmHint ? <p className={styles.fieldHint}>{pickHint(confirmHint)}</p> : null}

                {error ? <p className={styles.error}>{error}</p> : null}

                <button className={styles.primaryButton} disabled={loading} type="submit">
                  {loading ? t("Сохраняем...", "Сақтап жатырмыз...") : t("Сохранить пароль", "Құпиясөзді сақтау")}
                </button>
              </>
            ) : (
              <>
                <p className={styles.info}>{t("Пароль обновлен. Можно входить.", "Құпиясөз жаңартылды. Кіруге болады.")}</p>
                <Link className={styles.bottomLink} href="/login">
                  {t("Перейти на вход", "Кіруге өту")}
                </Link>
              </>
            )}
          </form>
        </section>
      </div>
    </>
  );
}

