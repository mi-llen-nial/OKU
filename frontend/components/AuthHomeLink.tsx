"use client";

import Link from "next/link";

import { publicPath } from "@/src/config/domains";
import { tr, useUiLanguage } from "@/lib/i18n";

import styles from "@/app/auth.module.css";

export default function AuthHomeLink() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const label = t("На главную", "Басты бетке");

  return (
    <Link aria-label={label} className={styles.authHomeLink} href={publicPath("/")} title={label}>
      <svg className={styles.authHomeIcon} viewBox="0 0 24 24" aria-hidden>
        <path
          d="M15 6l-6 6 6 6"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
        />
      </svg>
    </Link>
  );
}
