"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  checkInstitutionJoinCode,
  checkUsernameAvailable,
  createTeacherApplication,
  register,
  sendRegisterCode,
} from "@/lib/api";
import { saveSession } from "@/lib/auth";
import { tr, useUiLanguage } from "@/lib/i18n";
import {
  checkEmail,
  checkFullName,
  checkPassword,
  checkPasswordConfirm,
  checkUsername,
  checkVerificationCode,
  resolveDirectionOrOther,
  resolveSubjectOrOther,
  USERNAME_CHECK_FAILED_HINT,
  USERNAME_TAKEN_HINT,
} from "@/lib/registerValidation";
import { EducationLevel } from "@/lib/types";
import { publicPath } from "@/src/config/domains";
import AuthHomeLink from "@/components/AuthHomeLink";
import { assetPaths } from "@/src/assets";
import styles from "@/app/auth.module.css";

import { OTHER_SELECT_VALUE, STUDENT_DIRECTION_OPTIONS, TEACHER_SUBJECT_OPTIONS } from "./registerOptions";

const ICON_TEACHER = "/assets/icons/fa7-solid_chalkboard-teacher.svg";
const ICON_STUDENT = "/assets/icons/ph_student-bold.svg";

type WizardRole = "student" | "teacher";
type FlowStep = 1 | 2 | 3 | 4;
type Screen = "choose-role" | "wizard" | "teacher-sent";

export default function RegisterForm() {
  const router = useRouter();
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const [screen, setScreen] = useState<Screen>("choose-role");
  const [role, setRole] = useState<WizardRole>("student");
  const [step, setStep] = useState<FlowStep>(1);

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [educationLevel, setEducationLevel] = useState<EducationLevel>("school");
  const [directionSelect, setDirectionSelect] = useState(STUDENT_DIRECTION_OPTIONS[0]?.value ?? "");
  const [directionOther, setDirectionOther] = useState("");
  const [institutionCode, setInstitutionCode] = useState("");
  const [institutionId, setInstitutionId] = useState<number | null>(null);
  const [institutionNameResolved, setInstitutionNameResolved] = useState("");
  const [subjectSelect, setSubjectSelect] = useState(TEACHER_SUBJECT_OPTIONS[0]?.value ?? "");
  const [subjectOther, setSubjectOther] = useState("");
  const [teacherAdditionalInfo, setTeacherAdditionalInfo] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [verificationCode, setVerificationCode] = useState("");
  const [codeHint, setCodeHint] = useState("");

  const [sendingCode, setSendingCode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [usernameRemote, setUsernameRemote] = useState<
    "idle" | "checking" | "available" | "taken" | "error"
  >("idle");
  const [institutionRemote, setInstitutionRemote] = useState<
    "idle" | "checking" | "valid" | "invalid" | "error"
  >("idle");

  const [blurred, setBlurred] = useState({
    email: false,
    fullName: false,
    username: false,
    password: false,
    passwordConfirm: false,
    directionOther: false,
    subjectOther: false,
    institutionCode: false,
    code: false,
  });

  useEffect(() => {
    const lockClass = "auth-viewport-locked";
    document.documentElement.classList.add(lockClass);
    document.body.classList.add(lockClass);
    return () => {
      document.documentElement.classList.remove(lockClass);
      document.body.classList.remove(lockClass);
    };
  }, []);

  useEffect(() => {
    const local = checkUsername(username);
    if (!local.ok) {
      setUsernameRemote("idle");
      return;
    }
    const trimmed = username.trim();
    let cancelled = false;
    setUsernameRemote("checking");
    const timer = window.setTimeout(async () => {
      try {
        const res = await checkUsernameAvailable(trimmed);
        if (cancelled) return;
        if (res.available) setUsernameRemote("available");
        else if (res.reason === "taken") setUsernameRemote("taken");
        else setUsernameRemote("idle");
      } catch {
        if (cancelled) return;
        setUsernameRemote("error");
      }
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [username]);

  useEffect(() => {
    const raw = institutionCode.trim();
    if (!raw) {
      setInstitutionRemote("idle");
      setInstitutionId(null);
      setInstitutionNameResolved("");
      return;
    }
    let cancelled = false;
    setInstitutionRemote("checking");
    const timer = window.setTimeout(async () => {
      try {
        const res = await checkInstitutionJoinCode(raw);
        if (cancelled) return;
        if (res.valid && res.institution_id != null) {
          setInstitutionRemote("valid");
          setInstitutionId(res.institution_id);
          setInstitutionNameResolved(res.name ?? "");
        } else {
          setInstitutionRemote("invalid");
          setInstitutionId(null);
          setInstitutionNameResolved("");
        }
      } catch {
        if (cancelled) return;
        setInstitutionRemote("error");
        setInstitutionId(null);
      }
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [institutionCode]);

  const studentDirectionFinal = resolveDirectionOrOther(
    directionSelect,
    directionOther,
    OTHER_SELECT_VALUE,
  );
  const teacherSubjectFinal = resolveSubjectOrOther(subjectSelect, subjectOther, OTHER_SELECT_VALUE);

  const emailCheck = checkEmail(email);
  const fullNameCheck = checkFullName(fullName);
  const usernameCheck = checkUsername(username);
  const passwordCheck = checkPassword(password);
  const passwordConfirmCheck = checkPasswordConfirm(password, passwordConfirm);
  const codeCheck = checkVerificationCode(verificationCode);

  const fieldClass = (isBlurred: boolean, result: { ok: boolean }) =>
    [styles.input, isBlurred && (result.ok ? styles.inputValid : styles.inputInvalid)].filter(Boolean).join(" ");

  const usernameBorderNeutral =
    blurred.username &&
    usernameCheck.ok &&
    (usernameRemote === "idle" || usernameRemote === "checking" || usernameRemote === "error");
  const usernameBorderOk = blurred.username && usernameCheck.ok && usernameRemote === "available";
  const usernameBorderBad = blurred.username && (!usernameCheck.ok || usernameRemote === "taken");
  const usernameInputClass = blurred.username
    ? usernameBorderNeutral
      ? styles.input
      : usernameBorderOk
        ? `${styles.input} ${styles.inputValid}`
        : `${styles.input} ${styles.inputInvalid}`
    : styles.input;

  const institutionInputClass =
    blurred.institutionCode && institutionCode.trim()
      ? institutionRemote === "valid"
        ? `${styles.input} ${styles.inputValid}`
        : institutionRemote === "invalid" || institutionRemote === "error"
          ? `${styles.input} ${styles.inputInvalid}`
          : styles.input
      : styles.input;

  const progressPct = step * 25;

  const stepSubtitle = () => {
    if (step === 1) return t("Основная информация", "Негізгі ақпарат");
    if (step === 2) {
      return role === "student"
        ? t("Учебная информация", "Оқу туралы ақпарат")
        : t("Информация для заявки", "Өтінім туралы ақпарат");
    }
    if (step === 3) return t("Безопасность", "Қауіпсіздік");
    return t("Подтверждение почты", "Поштаны растау");
  };

  const ensureUsernameAvailableForSubmit = async (): Promise<boolean> => {
    try {
      const availRes = await checkUsernameAvailable(username.trim());
      if (!availRes.available) {
        if (availRes.reason === "taken") {
          setUsernameRemote("taken");
          setError(t(USERNAME_TAKEN_HINT.ru, USERNAME_TAKEN_HINT.kz));
        } else {
          setError(t(USERNAME_CHECK_FAILED_HINT.ru, USERNAME_CHECK_FAILED_HINT.kz));
        }
        return false;
      }
      setUsernameRemote("available");
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t(USERNAME_CHECK_FAILED_HINT.ru, USERNAME_CHECK_FAILED_HINT.kz),
      );
      return false;
    }
  };

  const validateStep1 = (): boolean => {
    setError("");
    const fn = checkFullName(fullName);
    if (!fn.ok) {
      setError(t(fn.hint.ru, fn.hint.kz));
      setBlurred((b) => ({ ...b, fullName: true }));
      return false;
    }
    const u = checkUsername(username);
    if (!u.ok) {
      setError(t(u.hint.ru, u.hint.kz));
      setBlurred((b) => ({ ...b, username: true }));
      return false;
    }
    if (usernameCheck.ok && usernameRemote !== "available") {
      if (usernameRemote === "taken") {
        setError(t(USERNAME_TAKEN_HINT.ru, USERNAME_TAKEN_HINT.kz));
      } else if (usernameRemote === "error") {
        setError(t(USERNAME_CHECK_FAILED_HINT.ru, USERNAME_CHECK_FAILED_HINT.kz));
      } else {
        setError(t("Дождитесь проверки никнейма", "Никнейм тексеріліп жатыр, күтіңіз"));
      }
      setBlurred((b) => ({ ...b, username: true }));
      return false;
    }
    const e = checkEmail(email);
    if (!e.ok) {
      setError(t(e.hint.ru, e.hint.kz));
      setBlurred((b) => ({ ...b, email: true }));
      return false;
    }
    return true;
  };

  const validateStep2Student = (): boolean => {
    setError("");
    const dir = studentDirectionFinal;
    if (!dir) {
      setError(
        t(
          "Выберите направление или укажите своё",
          "Бағытты таңдаңыз немесе өзіңіздікін жазыңыз",
        ),
      );
      setBlurred((b) => ({ ...b, directionOther: true }));
      return false;
    }
    return true;
  };

  const validateStep2Teacher = (): boolean => {
    setError("");
    if (!institutionCode.trim()) {
      setError(t("Введите код учебного учреждения", "Оқу орнының кодын енгізіңіз"));
      setBlurred((b) => ({ ...b, institutionCode: true }));
      return false;
    }
    if (institutionRemote === "checking") {
      setError(t("Дождитесь проверки кода", "Код тексеріліп жатыр, күтіңіз"));
      setBlurred((b) => ({ ...b, institutionCode: true }));
      return false;
    }
    if (institutionRemote !== "valid" || institutionId == null) {
      setError(
        t(
          "Проверьте код учебного учреждения",
          "Оқу орнының кодын тексеріңіз",
        ),
      );
      setBlurred((b) => ({ ...b, institutionCode: true }));
      return false;
    }
    const subj = teacherSubjectFinal;
    if (!subj) {
      setError(t("Укажите предмет", "Пәнді көрсетіңіз"));
      setBlurred((b) => ({ ...b, subjectOther: true }));
      return false;
    }
    return true;
  };

  const validateStep3 = (): boolean => {
    setError("");
    const p = checkPassword(password);
    if (!p.ok) {
      setError(t(p.hint.ru, p.hint.kz));
      setBlurred((b) => ({ ...b, password: true }));
      return false;
    }
    const pc = checkPasswordConfirm(password, passwordConfirm);
    if (!pc.ok) {
      setError(t(pc.hint.ru, pc.hint.kz));
      setBlurred((b) => ({ ...b, password: true, passwordConfirm: true }));
      return false;
    }
    if (!acceptedTerms) {
      setError(
        t(
          "Примите пользовательское соглашение, чтобы продолжить регистрацию",
          "Тіркелуді жалғастыру үшін пайдаланушы келісімін қабылдаңыз",
        ),
      );
      return false;
    }
    return true;
  };

  const runSendCode = async (): Promise<boolean> => {
    if (!(await ensureUsernameAvailableForSubmit())) return false;
    setSendingCode(true);
    setError("");
    setCodeHint("");
    try {
      const response = await sendRegisterCode({ email: email.trim() });
      const minutes = Math.max(1, Math.round(response.expires_in_seconds / 60));
      setCodeHint(
        t(
          `Код отправлен на почту. Срок действия: ${minutes} мин.`,
          `Код поштаға жіберілді. Жарамдылық мерзімі: ${minutes} мин.`,
        ),
      );
      setStep(4);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Не удалось отправить код", "Код жіберілмеді"));
      return false;
    } finally {
      setSendingCode(false);
    }
  };

  const handleWizardNext = async (e: FormEvent) => {
    e.preventDefault();
    if (step === 1) {
      if (!validateStep1()) return;
      if (!(await ensureUsernameAvailableForSubmit())) return;
      setStep(2);
      return;
    }
    if (step === 2) {
      if (role === "student") {
        if (!validateStep2Student()) return;
        setStep(3);
        return;
      }
      if (!validateStep2Teacher()) return;
      setStep(3);
      return;
    }
    if (step === 3) {
      if (!validateStep3()) return;
      await runSendCode();
      return;
    }
  };

  const handleWizardBack = () => {
    setError("");
    if (step === 1) {
      setScreen("choose-role");
      return;
    }
    if (step === 4) {
      setStep(3);
      return;
    }
    setStep((s) => (s > 1 ? ((s - 1) as FlowStep) : s));
  };

  const handleConfirmRegister = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    const c = checkVerificationCode(verificationCode);
    if (!c.ok) {
      setLoading(false);
      setError(t(c.hint.ru, c.hint.kz));
      setBlurred((b) => ({ ...b, code: true }));
      return;
    }
    if (!(await ensureUsernameAvailableForSubmit())) {
      setLoading(false);
      setStep(1);
      return;
    }
    const normalizedCode = verificationCode.replace(/\s+/g, "").trim();
    try {
      const payload = await register({
        email,
        full_name: fullName,
        username: username.trim(),
        email_verification_code: normalizedCode,
        education_level: role === "student" ? educationLevel : undefined,
        direction: role === "student" ? studentDirectionFinal : undefined,
        password,
        role,
        preferred_language: "RU",
      });

      if (role === "teacher" && institutionId != null) {
        await createTeacherApplication(payload.access_token, {
          institution_id: institutionId,
          full_name: fullName.trim(),
          email: email.trim(),
          subject: teacherSubjectFinal || undefined,
          additional_info: teacherAdditionalInfo.trim() || undefined,
        });
      }

      saveSession(payload, { rememberMe: true });

      if (role === "teacher") {
        setScreen("teacher-sent");
        setLoading(false);
        return;
      }

      router.push(payload.user.role === "teacher" ? "/teacher" : "/dashboard");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t("Не удалось создать аккаунт", "Аккаунт құру мүмкін болмады"),
      );
    } finally {
      setLoading(false);
    }
  };

  const chooseRole = (r: WizardRole) => {
    setRole(r);
    setScreen("wizard");
    setStep(1);
    setError("");
  };

  const resendCode = async () => {
    if (!validateStep3()) return;
    await runSendCode();
  };

  if (screen === "teacher-sent") {
    return (
      <>
        <AuthHomeLink />
        <div className={styles.authSplit}>
          <section className={styles.brandPanel}>
            <img className={styles.brandLogo} src={assetPaths.logo.svg} alt="OKU" />
          </section>
          <section className={styles.formPanel}>
            <div className={`${styles.formCard} ${styles.registerWizardCard}`}>
              <h1 className={styles.title}>{t("Заявка отправлена", "Өтінім жіберілді")}</h1>
              <p className={styles.subtitle}>
                {t(
                  "Заявка успешно отправлена. Пожалуйста, дождитесь рассмотрения администратором учебного учреждения",
                  "Өтінім сәтті жіберілді. Оқу орны әкімшісінің шешімін күтіңіз",
                )}
              </p>
              <p className={styles.info}>
                {institutionNameResolved
                  ? t(`Учреждение: ${institutionNameResolved}`, `Оқу орны: ${institutionNameResolved}`)
                  : null}
              </p>
              <button
                className={styles.primaryButton}
                onClick={() => router.push("/dashboard?teacherApplication=submitted")}
                type="button"
              >
                {t("Перейти в личный кабинет", "Жеке кабинетке өту")}
              </button>
            </div>
          </section>
        </div>
      </>
    );
  }

  if (screen === "choose-role") {
    return (
      <>
        <AuthHomeLink />
        <div className={styles.authSplit}>
          <section className={styles.brandPanel}>
            <img className={styles.brandLogo} src={assetPaths.logo.svg} alt="OKU" />
          </section>
          <section className={styles.formPanel}>
            <div className={`${styles.formCard} ${styles.registerWizardCard} ${styles.registerRoleScreen}`}>
              <h1 className={styles.title}>{t("Регистрация", "Тіркелу")}</h1>
              <p className={styles.subtitle}>{t("Кто вы?", "Сіз кімсіз?")}</p>
              <div className={styles.rolePickGrid}>
                <button
                  className={styles.rolePickCard}
                  onClick={() => chooseRole("teacher")}
                  type="button"
                >
                  <div className={styles.rolePickCardInner}>
                    <span className={styles.rolePickIcon}>
                      <img alt="" src={ICON_TEACHER} />
                    </span>
                    <div className={styles.rolePickText}>
                      <span className={styles.rolePickTitle}>{t("Преподаватель", "Оқытушы")}</span>
                      <span className={styles.rolePickHint}>
                        {t("Заявка в учебное учреждение", "Оқу орнына өтінім")}
                      </span>
                    </div>
                  </div>
                </button>
                <button
                  className={styles.rolePickCard}
                  onClick={() => chooseRole("student")}
                  type="button"
                >
                  <div className={styles.rolePickCardInner}>
                    <span className={styles.rolePickIcon}>
                      <img alt="" src={ICON_STUDENT} />
                    </span>
                    <div className={styles.rolePickText}>
                      <span className={styles.rolePickTitle}>{t("Ученик", "Оқушы")}</span>
                      <span className={styles.rolePickHint}>
                        {t("Обучение и тестирование", "Оқу және тестілеу")}
                      </span>
                    </div>
                  </div>
                </button>
              </div>
              <p className={styles.bottomText}>
                {t("Есть аккаунт?", "Аккаунтыңыз бар ма?")}{" "}
                <Link className={styles.bottomLink} href="/login">
                  {t("Войти", "Кіру")}
                </Link>
              </p>
            </div>
          </section>
        </div>
      </>
    );
  }

  return (
    <>
      <div className={styles.authSplit}>
        <section className={styles.brandPanel}>
          <img className={styles.brandLogo} src={assetPaths.logo.svg} alt="OKU" />
        </section>
        <section className={styles.formPanel}>
          {step < 4 ? (
            <form
              className={`${styles.formCard} ${styles.registerWizardCard}`}
              noValidate
              onSubmit={handleWizardNext}
            >
              <div className={styles.registerWizardHeader}>
                <button
                  aria-label={t("Назад", "Артқа")}
                  className={styles.registerBackChevron}
                  onClick={handleWizardBack}
                  type="button"
                >
                  <svg className={styles.registerBackChevronIcon} viewBox="0 0 24 24" aria-hidden>
                    <path
                      d="M15 6l-6 6 6 6"
                      fill="none"
                      stroke="currentColor"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="3"
                    />
                  </svg>
                </button>
                <div className={styles.registerProgressTrack} aria-hidden>
                  <div className={styles.registerProgressFill} style={{ width: `${progressPct}%` }} />
                </div>
              </div>
              <h1 className={styles.title}>{t("Регистрация", "Тіркелу")}</h1>
              <p className={styles.subtitle}>{stepSubtitle()}</p>

              <div className={styles.registerStepFields} key={`${role}-s${step}`}>
              {step === 1 ? (
                <>
                  <label className={styles.label}>
                    <span>{t("Почта", "Электрондық пошта")}</span>
                    <input
                      autoComplete="email"
                      className={fieldClass(blurred.email, emailCheck)}
                      onBlur={() => setBlurred((b) => ({ ...b, email: true }))}
                      onChange={(e) => setEmail(e.target.value)}
                      type="email"
                      value={email}
                    />
                    {blurred.email && !emailCheck.ok ? (
                      <p className={styles.fieldHint}>{t(emailCheck.hint.ru, emailCheck.hint.kz)}</p>
                    ) : null}
                  </label>
                  <label className={styles.label}>
                    <span>{t("Имя и фамилия", "Аты-жөні")}</span>
                    <input
                      autoComplete="name"
                      className={fieldClass(blurred.fullName, fullNameCheck)}
                      onBlur={() => setBlurred((b) => ({ ...b, fullName: true }))}
                      onChange={(e) => setFullName(e.target.value)}
                      value={fullName}
                    />
                    {blurred.fullName && !fullNameCheck.ok ? (
                      <p className={styles.fieldHint}>{t(fullNameCheck.hint.ru, fullNameCheck.hint.kz)}</p>
                    ) : null}
                  </label>
                  <label className={styles.label}>
                    <span>{t("Никнейм", "Никнейм")}</span>
                    <input
                      className={usernameInputClass}
                      maxLength={25}
                      onBlur={() => setBlurred((b) => ({ ...b, username: true }))}
                      onChange={(e) => setUsername(e.target.value)}
                      value={username}
                    />
                    {blurred.username && !usernameCheck.ok ? (
                      <p className={styles.fieldHint}>{t(usernameCheck.hint.ru, usernameCheck.hint.kz)}</p>
                    ) : null}
                    {blurred.username && usernameCheck.ok && usernameRemote === "taken" ? (
                      <p className={styles.fieldHint}>{t(USERNAME_TAKEN_HINT.ru, USERNAME_TAKEN_HINT.kz)}</p>
                    ) : null}
                    {blurred.username && usernameCheck.ok && usernameRemote === "error" ? (
                      <p className={styles.fieldHint}>
                        {t(USERNAME_CHECK_FAILED_HINT.ru, USERNAME_CHECK_FAILED_HINT.kz)}
                      </p>
                    ) : null}
                  </label>
                </>
              ) : null}

              {step === 2 && role === "student" ? (
                <>
                  <label className={styles.label}>
                    <span>{t("Статус обучения", "Оқу мәртебесі")}</span>
                    <select
                      className={styles.input}
                      onChange={(e) => setEducationLevel(e.target.value as EducationLevel)}
                      value={educationLevel}
                    >
                      <option value="school">{t("Школьник", "Мектеп оқушысы")}</option>
                      <option value="college">{t("Студент колледжа", "Колледж студенті")}</option>
                      <option value="university">{t("Студент университета", "Университет студенті")}</option>
                    </select>
                  </label>
                  <label className={styles.label}>
                    <span>{t("Направление", "Бағыты")}</span>
                    <select
                      className={styles.input}
                      onChange={(e) => setDirectionSelect(e.target.value)}
                      value={directionSelect}
                    >
                      {STUDENT_DIRECTION_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {t(o.ru, o.kz)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {directionSelect === OTHER_SELECT_VALUE ? (
                    <label className={styles.label}>
                      <span>{t("Укажите направление", "Бағытты жазыңыз")}</span>
                      <input
                        className={fieldClass(blurred.directionOther, {
                          ok: directionOther.trim().length > 0,
                        })}
                        onBlur={() => setBlurred((b) => ({ ...b, directionOther: true }))}
                        onChange={(e) => setDirectionOther(e.target.value)}
                        value={directionOther}
                      />
                      {blurred.directionOther && !directionOther.trim() ? (
                        <p className={styles.fieldHint}>
                          {t("Укажите направление обучения", "Оқу бағытын көрсетіңіз")}
                        </p>
                      ) : null}
                    </label>
                  ) : null}
                </>
              ) : null}

              {step === 2 && role === "teacher" ? (
                <>
                  <label className={styles.label}>
                    <span>{t("Код учебного учреждения", "Оқу орнының коды")}</span>
                    <input
                      autoComplete="off"
                      className={institutionInputClass}
                      onBlur={() => setBlurred((b) => ({ ...b, institutionCode: true }))}
                      onChange={(e) => setInstitutionCode(e.target.value)}
                      value={institutionCode}
                    />
                    {blurred.institutionCode && institutionCode.trim() && institutionRemote === "invalid" ? (
                      <p className={styles.fieldHint}>
                        {t(
                          "Код не найден или учреждение неактивно",
                          "Код табылмады немесе оқу орны белсенді емес",
                        )}
                      </p>
                    ) : null}
                    {blurred.institutionCode && institutionRemote === "error" ? (
                      <p className={styles.fieldHint}>
                        {t(
                          "Не удалось проверить код, попробуйте ещё раз",
                          "Кодты тексеру мүмкін болмады, қайта көріңіз",
                        )}
                      </p>
                    ) : null}
                    {institutionRemote === "valid" && institutionNameResolved ? (
                      <p className={styles.fieldHintOk}>
                        {t(`Учреждение: ${institutionNameResolved}`, `Оқу орны: ${institutionNameResolved}`)}
                      </p>
                    ) : null}
                  </label>
                  <label className={styles.label}>
                    <span>{t("Предмет", "Пән")}</span>
                    <select
                      className={styles.input}
                      onChange={(e) => setSubjectSelect(e.target.value)}
                      value={subjectSelect}
                    >
                      {TEACHER_SUBJECT_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {t(o.ru, o.kz)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {subjectSelect === OTHER_SELECT_VALUE ? (
                    <label className={styles.label}>
                      <span>{t("Укажите предмет", "Пәнді жазыңыз")}</span>
                      <input
                        className={fieldClass(blurred.subjectOther, { ok: subjectOther.trim().length > 0 })}
                        onBlur={() => setBlurred((b) => ({ ...b, subjectOther: true }))}
                        onChange={(e) => setSubjectOther(e.target.value)}
                        value={subjectOther}
                      />
                      {blurred.subjectOther && !subjectOther.trim() ? (
                        <p className={styles.fieldHint}>{t("Укажите предмет", "Пәнді көрсетіңіз")}</p>
                      ) : null}
                    </label>
                  ) : null}
                  <label className={styles.label}>
                    <span>{t("Дополнительная информация о заявке", "Өтінім туралы қосымша")}</span>
                    <textarea
                      className={`${styles.input} ${styles.registerTextarea}`}
                      onChange={(e) => setTeacherAdditionalInfo(e.target.value)}
                      placeholder={t("Кратко о себе и опыте", "Өзіңіз және тәжірибеңіз қысқаша")}
                      rows={3}
                      value={teacherAdditionalInfo}
                    />
                  </label>
                </>
              ) : null}

              {step === 3 ? (
                <>
                  <label className={styles.label}>
                    <span>{t("Пароль", "Құпиясөз")}</span>
                    <input
                      autoComplete="new-password"
                      className={fieldClass(blurred.password, passwordCheck)}
                      minLength={6}
                      onBlur={() => setBlurred((b) => ({ ...b, password: true }))}
                      onChange={(e) => setPassword(e.target.value)}
                      type="password"
                      value={password}
                    />
                    {blurred.password && !passwordCheck.ok ? (
                      <p className={styles.fieldHint}>{t(passwordCheck.hint.ru, passwordCheck.hint.kz)}</p>
                    ) : null}
                  </label>
                  <label className={styles.label}>
                    <span>{t("Подтверждение пароля", "Құпиясөзді растау")}</span>
                    <input
                      autoComplete="new-password"
                      className={fieldClass(blurred.passwordConfirm, passwordConfirmCheck)}
                      onBlur={() => setBlurred((b) => ({ ...b, passwordConfirm: true }))}
                      onChange={(e) => setPasswordConfirm(e.target.value)}
                      type="password"
                      value={passwordConfirm}
                    />
                    {blurred.passwordConfirm && !passwordConfirmCheck.ok ? (
                      <p className={styles.fieldHint}>{t(passwordConfirmCheck.hint.ru, passwordConfirmCheck.hint.kz)}</p>
                    ) : null}
                  </label>
                  <label className={`${styles.rememberRow} ${styles.termsRow}`}>
                    <input
                      checked={acceptedTerms}
                      onChange={(e) => setAcceptedTerms(e.target.checked)}
                      type="checkbox"
                    />
                    <span>
                      {t("Я принимаю ", "Мен қабылдаймын ")}{" "}
                      <Link
                        className={styles.bottomLink}
                        href={publicPath("/user-agreement")}
                        rel="noopener noreferrer"
                        target="_blank"
                      >
                        {t("пользовательское соглашение", "пайдаланушы келісімін")}
                      </Link>
                    </span>
                  </label>
                </>
              ) : null}

              </div>

              {error ? <p className={styles.error}>{error}</p> : null}

              <div className={styles.registerActions}>
                <button
                  className={styles.primaryButton}
                  disabled={
                    step === 3 ? sendingCode || !acceptedTerms : step === 1 ? sendingCode : false
                  }
                  type="submit"
                >
                  {step === 3 && sendingCode
                    ? t("Отправляем код...", "Код жіберіліп жатыр...")
                    : t("Продолжить", "Жалғастыру")}
                </button>
              </div>

              <p className={styles.bottomText}>
                {t("Есть аккаунт?", "Аккаунтыңыз бар ма?")}{" "}
                <Link className={styles.bottomLink} href="/login">
                  {t("Войти", "Кіру")}
                </Link>
              </p>
            </form>
          ) : (
            <form
              className={`${styles.formCard} ${styles.registerWizardCard}`}
              noValidate
              onSubmit={handleConfirmRegister}
            >
              <div className={styles.registerWizardHeader}>
                <button
                  aria-label={t("Назад", "Артқа")}
                  className={styles.registerBackChevron}
                  onClick={handleWizardBack}
                  type="button"
                >
                  <svg className={styles.registerBackChevronIcon} viewBox="0 0 24 24" aria-hidden>
                    <path
                      d="M15 6l-6 6 6 6"
                      fill="none"
                      stroke="currentColor"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="3"
                    />
                  </svg>
                </button>
                <div className={styles.registerProgressTrack} aria-hidden>
                  <div className={styles.registerProgressFill} style={{ width: "100%" }} />
                </div>
              </div>
              <h1 className={styles.title}>{t("Введите код", "Кодты енгізіңіз")}</h1>
              <p className={styles.subtitle}>{t("Подтверждение почты", "Поштаны растау")}</p>
              <p className={styles.subtitle}>
                {t(
                  "К вам на почту пришел код, также проверьте папку спама",
                  "Код email-ға жіберілді, спам бумасын да тексеріңіз",
                )}
              </p>
              {codeHint ? <p className={styles.info}>{codeHint}</p> : null}

              <div className={styles.registerStepFields} key="code-step">
                <label className={styles.label}>
                  <span>{t("Код из письма", "Поштадағы код")}</span>
                  <input
                    className={[styles.input, styles.codeInput, blurred.code && (codeCheck.ok ? styles.inputValid : styles.inputInvalid)]
                      .filter(Boolean)
                      .join(" ")}
                    inputMode="numeric"
                    maxLength={6}
                    onBlur={() => setBlurred((b) => ({ ...b, code: true }))}
                    onChange={(e) => setVerificationCode(e.target.value)}
                    placeholder="______"
                    value={verificationCode}
                  />
                  {blurred.code && !codeCheck.ok ? (
                    <p className={styles.fieldHint}>{t(codeCheck.hint.ru, codeCheck.hint.kz)}</p>
                  ) : null}
                </label>
              </div>

              {error ? <p className={styles.error}>{error}</p> : null}

              <div className={styles.registerActions}>
                <button className={styles.primaryButton} disabled={loading} type="submit">
                  {loading ? t("Подтверждаем...", "Расталып жатыр...") : t("Подтвердить", "Растау")}
                </button>
              </div>
              <button
                className={styles.secondaryButton}
                disabled={sendingCode}
                onClick={() => void resendCode()}
                type="button"
              >
                {sendingCode
                  ? t("Отправляем код...", "Код жіберіліп жатыр...")
                  : t("Отправить код повторно", "Кодты қайта жіберу")}
              </button>
            </form>
          )}
        </section>
      </div>
    </>
  );
}
