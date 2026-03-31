"use client";

import { tr, useUiLanguage } from "@/lib/i18n";

import RevealOnScroll from "./RevealOnScroll";
import UserAgreementDocument from "./userAgreement/UserAgreementDocument";
import styles from "./userAgreementPage.module.css";

export default function UserAgreementPageContent() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);
  const docTitle = t("Пользовательское соглашение", "Пайдаланушы келісімі");

  return (
    <RevealOnScroll>
      <article className={styles.article}>
        <h1 className={styles.title}>{docTitle}</h1>
        <p className={styles.lead}>
          {t(
            "Ниже приведён полный текст документа. Дополнительно вы можете скачать PDF.",
            "Төменде құжаттың толық мәтіні берілген. PDF нұсқасын жүктеп алуға болады.",
          )}
        </p>
        <div className={styles.downloadBar}>
          <a className={styles.downloadLink} href="/legal/user-agreement.pdf" download>
            {t("Скачать PDF", "PDF жүктеу")}
          </a>
          <span className={styles.downloadHint}>
            {t(
              "Файл совпадает с текстом на странице (редакция от 21.03.2026).",
              "Файл беттегі мәтінмен сәйкес келеді (21.03.2026 редакциясы).",
            )}
          </span>
        </div>
        <UserAgreementDocument />
      </article>
    </RevealOnScroll>
  );
}
