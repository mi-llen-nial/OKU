"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { register, sendRegisterCode } from "@/lib/api";
import { saveSession } from "@/lib/auth";
import { tr, useUiLanguage } from "@/lib/i18n";
import { EducationLevel, UserRole } from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/app/auth.module.css";

type RegisterStep = "details" | "code";

export default function RegisterPage() {
  const router = useRouter();
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);
  const [step, setStep] = useState<RegisterStep>("details");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<UserRole>("student");
  const [educationLevel, setEducationLevel] = useState<EducationLevel>("school");
  const [direction, setDirection] = useState("");
  const [password, setPassword] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [codeHint, setCodeHint] = useState("");
  const [sendingCode, setSendingCode] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const validateDetailsStep = () => {
    const emailValue = email.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(emailValue)) {
      return t("Сначала укажите корректную почту.", "Алдымен дұрыс email енгізіңіз.");
    }
    if (!fullName.trim()) {
      return t("Укажите имя и фамилию.", "Аты-жөніңізді енгізіңіз.");
    }
    const usernameValue = username.trim();
    if (!/^[A-Za-z0-9_]{3,25}$/.test(usernameValue)) {
      return t(
        "Имя пользователя: только латинские буквы, цифры и _, длина 3-25 символов.",
        "Пайдаланушы аты: тек латын әріптері, сандар және _, ұзындығы 3-25 таңба.",
      );
    }
    if (role === "student" && !direction.trim()) {
      return t("Укажите направление обучения.", "Оқу бағытын енгізіңіз.");
    }
    if (password.length < 6) {
      return t("Пароль должен быть не короче 6 символов.", "Құпиясөз кемінде 6 таңба болуы керек.");
    }
    return null;
  };

  const sendCode = async (nextStep: RegisterStep = "code") => {
    const validationError = validateDetailsStep();
    if (validationError) {
      setError(validationError);
      return false;
    }
    setError("");
    setCodeHint("");
    setSendingCode(true);
    try {
      const response = await sendRegisterCode({ email: email.trim() });
      const minutes = Math.max(1, Math.round(response.expires_in_seconds / 60));
      setCodeHint(
        t(
          `Код отправлен на почту. Срок действия: ${minutes} мин.`,
          `Код поштаға жіберілді. Жарамдылық мерзімі: ${minutes} мин.`,
        ),
      );
      setStep(nextStep);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось отправить код", "Код жіберілмеді"));
      return false;
    } finally {
      setSendingCode(false);
    }
  };

  const handleContinue = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await sendCode("code");
  };

  const handleConfirmRegister = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    const usernameValue = username.trim();
    if (!/^[A-Za-z0-9_]{3,25}$/.test(usernameValue)) {
      setLoading(false);
      setError(
        t(
          "Имя пользователя: только латинские буквы, цифры и _, длина 3-25 символов.",
          "Пайдаланушы аты: тек латын әріптері, сандар және _, ұзындығы 3-25 таңба.",
        ),
      );
      return;
    }
    const normalizedCode = verificationCode.replace(/\s+/g, "").trim();
    if (!/^\d{6}$/.test(normalizedCode)) {
      setLoading(false);
      setError(t("Введите 6-значный код из письма.", "Поштадан келген 6 таңбалы кодты енгізіңіз."));
      return;
    }

    try {
      const payload = await register({
        email,
        full_name: fullName,
        username: usernameValue,
        email_verification_code: normalizedCode,
        education_level: role === "student" ? educationLevel : undefined,
        direction: role === "student" ? direction.trim() : undefined,
        password,
        role,
        preferred_language: "RU",
      });
      saveSession(payload, { rememberMe: true });
      router.push(payload.user.role === "teacher" ? "/teacher" : "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось создать аккаунт", "Аккаунт құру мүмкін болмады"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.authSplit}>
      <section className={styles.brandPanel}>
        <img className={styles.brandLogo} src={assetPaths.logo.svg} alt="OKU" />
      </section>
      <section className={styles.formPanel}>
        {step === "details" ? (
          <form className={`${styles.formCard} ${styles.registerCard}`} onSubmit={handleContinue}>
            <h1 className={styles.title}>{t("Регистрация", "Тіркелу")}</h1>
            <p className={styles.subtitle}>{t("Введите данные и продолжите подтверждение почты.", "Деректерді енгізіп, email растауға өтіңіз.")}</p>

            <label className={styles.label}>
              <span>{t("Почта", "Электрондық пошта")}</span>
              <input className={styles.input} onChange={(e) => setEmail(e.target.value)} required type="email" value={email} />
            </label>

            <label className={styles.label}>
              <span>{t("Имя и фамилия", "Аты-жөні")}</span>
              <input className={styles.input} onChange={(e) => setFullName(e.target.value)} required value={fullName} />
            </label>

            <label className={styles.label}>
              <span>{t("Имя пользователя", "Пайдаланушы аты")}</span>
              <input
                className={styles.input}
                maxLength={25}
                onChange={(e) => setUsername(e.target.value)}
                pattern="[A-Za-z0-9_]{3,25}"
                required
                title={t("Только латинские буквы, цифры и _, длина 3-25 символов", "Тек латын әріптері, сандар және _, ұзындығы 3-25 таңба")}
                value={username}
              />
            </label>

            <label className={styles.label}>
              <span>{t("Роль", "Рөлі")}</span>
              <select className={styles.input} onChange={(e) => setRole(e.target.value as UserRole)} value={role}>
                <option value="student">{t("Студент", "Оқушы")}</option>
                <option value="teacher">{t("Преподаватель (админ)", "Оқытушы (админ)")}</option>
              </select>
            </label>

            {role === "student" && (
              <label className={styles.label}>
                <span>{t("Статус обучения", "Оқу мәртебесі")}</span>
                <select className={styles.input} onChange={(e) => setEducationLevel(e.target.value as EducationLevel)} value={educationLevel}>
                  <option value="school">{t("Школьник", "Мектеп оқушысы")}</option>
                  <option value="college">{t("Студент колледжа", "Колледж студенті")}</option>
                  <option value="university">{t("Студент университета", "Университет студенті")}</option>
                </select>
              </label>
            )}

            {role === "student" && (
              <label className={styles.label}>
                <span>{t("Направление", "Бағыты")}</span>
                <input
                  className={styles.input}
                  onChange={(e) => setDirection(e.target.value)}
                  placeholder={t("Например: ИТ, медицина, экономика", "Мысалы: IT, медицина, экономика")}
                  required
                  value={direction}
                />
              </label>
            )}

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

            {error ? <p className={styles.error}>{error}</p> : null}

            <button className={styles.primaryButton} disabled={sendingCode} type="submit">
              {sendingCode ? t("Отправляем код...", "Код жіберіліп жатыр...") : t("Продолжить", "Жалғастыру")}
            </button>

            <p className={styles.bottomText}>
              {t("Уже есть аккаунт?", "Аккаунтыңыз бар ма?")}{" "}
              <Link className={styles.bottomLink} href="/login">
                {t("Войти", "Кіру")}
              </Link>
            </p>
          </form>
        ) : (
          <form className={`${styles.formCard} ${styles.registerCard}`} onSubmit={handleConfirmRegister}>
            <h1 className={styles.title}>{t("Введите код", "Кодты енгізіңіз")}</h1>
            <p className={styles.subtitle}>
              {t("К вам на почту пришел код, также проверьте папку спама", "Код email-ға жіберілді, спам бумасын да тексеріңіз")}
            </p>
            {codeHint ? <p className={styles.info}>{codeHint}</p> : null}

            <label className={styles.label}>
              <span>{t("Код из письма", "Поштадағы код")}</span>
              <input
                className={`${styles.input} ${styles.codeInput}`}
                inputMode="numeric"
                maxLength={6}
                onChange={(e) => setVerificationCode(e.target.value)}
                placeholder="______"
                required
                value={verificationCode}
              />
            </label>

            {error ? <p className={styles.error}>{error}</p> : null}

            <button className={styles.primaryButton} disabled={loading} type="submit">
              {loading ? t("Подтверждаем...", "Расталып жатыр...") : t("Подтвердить", "Растау")}
            </button>

            <button className={styles.secondaryButton} disabled={sendingCode} onClick={() => void sendCode("code")} type="button">
              {sendingCode ? t("Отправляем код...", "Код жіберіліп жатыр...") : t("Отправить код повторно", "Кодты қайта жіберу")}
            </button>

            <button className={styles.secondaryButton} onClick={() => setStep("details")} type="button">
              {t("Изменить данные", "Деректерді өзгерту")}
            </button>
          </form>
        )}
      </section>
    </div>
  );
}
