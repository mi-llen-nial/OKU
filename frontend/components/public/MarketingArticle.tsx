"use client";

import Link from "next/link";

import { appPath } from "@/src/config/domains";
import { tr, useUiLanguage } from "@/lib/i18n";

import RevealOnScroll from "./RevealOnScroll";
import styles from "./publicSite.module.css";

interface MarketingArticleProps {
  titleRu: string;
  titleKz: string;
  leadRu: string;
  leadKz: string;
  paragraphsRu: string[];
  paragraphsKz: string[];
}

export default function MarketingArticle(props: MarketingArticleProps) {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);
  const paragraphs = uiLanguage === "KZ" ? props.paragraphsKz : props.paragraphsRu;

  return (
    <RevealOnScroll>
    <article className={styles.marketingPage}>
      <h1 className={styles.marketingTitle}>{t(props.titleRu, props.titleKz)}</h1>
      <p className={styles.marketingLead}>{t(props.leadRu, props.leadKz)}</p>
      <div className={styles.marketingBody}>
        {paragraphs.map((text, index) => (
          <p key={index}>{text}</p>
        ))}
      </div>
      <p style={{ marginTop: 28 }}>
        <Link className={styles.ctaPrimary} href={appPath("/register")} style={{ display: "inline-block" }}>
          {t("Перейти в платформу", "Платформаға өту")}
        </Link>
      </p>
    </article>
    </RevealOnScroll>
  );
}
