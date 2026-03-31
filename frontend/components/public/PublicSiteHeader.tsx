"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { appPath } from "@/src/config/domains";
import { tr, useUiLanguage } from "@/lib/i18n";
import { assetPaths } from "@/src/assets";

import styles from "./publicSite.module.css";

/** Порядок как в макете: … Цены, О нас */
const NAV_PATHS = [
  { href: "/students", ru: "Для учеников", kz: "Оқушыларға" },
  { href: "/teachers", ru: "Для преподавателей", kz: "Оқытушыларға" },
  { href: "/institutions", ru: "Для учреждений", kz: "Оқу орындарына" },
  { href: "/price", ru: "Цены", kz: "Бағалар" },
  { href: "/about", ru: "О нас", kz: "Біз туралы" },
] as const;

const PAGE_LABELS = [
  { href: "/", ru: "Главная", kz: "Басты бет" },
  ...NAV_PATHS,
] as const;

function labelForPath(pathname: string | null): (typeof PAGE_LABELS)[number] {
  if (!pathname) return PAGE_LABELS[0];
  const normalized = pathname === "/" ? "/" : pathname.replace(/\/+$/, "") || "/";
  return PAGE_LABELS.find((p) => p.href === normalized) ?? PAGE_LABELS[0];
}

export default function PublicSiteHeader() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);
  const pathname = usePathname();
  const pageLabel = labelForPath(pathname);
  const [open, setOpen] = useState(false);

  return (
    <div className={styles.headerShell}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/" onClick={() => setOpen(false)}>
          <img className={styles.okuWordmark} src={assetPaths.logo.textColor} alt="OKU" />
        </Link>

        <p className={styles.mobilePageTitle}>{t(pageLabel.ru, pageLabel.kz)}</p>

        <nav className={styles.nav} aria-label="Main">
          {NAV_PATHS.map((item) => (
            <Link key={item.href} className={styles.navLink} href={item.href}>
              {t(item.ru, item.kz)}
            </Link>
          ))}
        </nav>

        <div className={styles.ctaRow}>
          <button
            type="button"
            className={styles.mobileMenuBtn}
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={t("Меню", "Мәзір")}
          >
            <span className={styles.mobileMenuIcon} aria-hidden>
              <span />
              <span />
              <span />
            </span>
          </button>
          <Link className={styles.btnRegister} href={appPath("/register")}>
            {t("Регистрация", "Тіркелу")}
          </Link>
          <Link className={styles.ctaLogin} href={appPath("/login")}>
            {t("Войти", "Кіру")}
          </Link>
        </div>
      </header>

      <div
        className={`${styles.mobileDropdownOuter} ${open ? styles.mobileDropdownOuterOpen : ""}`}
        aria-hidden={!open}
      >
        <div className={styles.mobileDropdownInner}>
          <nav
            className={styles.mobileDropdownContent}
            aria-label={t("Мобильная навигация", "Мобильді навигация")}
          >
            {NAV_PATHS.map((item) => (
              <Link
                key={item.href}
                className={styles.mobileNavLink}
                href={item.href}
                onClick={() => setOpen(false)}
              >
                {t(item.ru, item.kz)}
              </Link>
            ))}
            <Link className={styles.ctaLogin} href={appPath("/login")} onClick={() => setOpen(false)}>
              {t("Войти", "Кіру")}
            </Link>
            <Link className={styles.btnRegister} href={appPath("/register")} onClick={() => setOpen(false)}>
              {t("Регистрация", "Тіркелу")}
            </Link>
          </nav>
        </div>
      </div>
    </div>
  );
}
