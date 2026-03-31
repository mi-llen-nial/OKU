"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { tr, useUiLanguage } from "@/lib/i18n";
import { assetPaths } from "@/src/assets";

import styles from "./publicSite.module.css";

export default function PublicSiteFooter() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);
  const [email, setEmail] = useState("");

  const onSubscribe = (e: FormEvent) => {
    e.preventDefault();
    /* Заглушка: интеграция рассылки позже */
    setEmail("");
  };

  return (
    <footer className={styles.footer} data-nosnippet="true">
      <div className={styles.footerGrid}>
        <div className={styles.footerBrand}>
          <img className={styles.okuWordmark} src={assetPaths.logo.textColor} alt="OKU" />
        </div>

        <div>
          <p className={styles.footerColTitle}>OKU</p>
          <ul className={styles.footerList}>
            <li>
              <Link href="/about">{t("О нас", "Біз туралы")}</Link>
            </li>
            <li>
              <Link href="/">{t("Главная", "Басты бет")}</Link>
            </li>
            <li>
              <Link href="/students">{t("Для учеников", "Оқушыларға")}</Link>
            </li>
            <li>
              <Link href="/teachers">{t("Для преподавателей", "Оқытушыларға")}</Link>
            </li>
            <li>
              <Link href="/institutions">{t("Для учреждений", "Оқу орындарына")}</Link>
            </li>
          </ul>
        </div>

        <div>
          <p className={styles.footerColTitle}>{t("Ресурсы", "Ресурстар")}</p>
          <ul className={styles.footerList}>
            <li>
              <Link href="/user-agreement">{t("Пользовательское соглашение", "Пайдаланушы келісімі")}</Link>
            </li>
            <li>
              <a href="mailto:oku.official@outlook.com">okuofficial@outlook.com</a>
            </li>
          </ul>
        </div>

        <div>
          <p className={styles.newsletterTitle}>
            {t("Подпишитесь на обновления и новости", "Жаңалықтар мен жаңартуларға жазылыңыз")}
          </p>
          <form className={styles.newsletterForm} onSubmit={onSubscribe}>
            <input
              className={styles.newsletterInput}
              type="email"
              name="email"
              autoComplete="email"
              placeholder={t("Введите e-mail", "Поштаңызды енгізіңіз")}
              value={email}
              onChange={(ev) => setEmail(ev.target.value)}
            />
            <button className={styles.newsletterBtn} type="submit">
              {t("Подписаться", "Жазылу")}
            </button>
          </form>
        </div>
      </div>

      <p className={styles.footerBottom}>
        {t("©Все права защищены 2026", "©Барлық құқықтар қорғалған 2026")}
      </p>
    </footer>
  );
}
