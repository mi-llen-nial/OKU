"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  Bell,
  Bolt,
  ClipboardPenLine,
  BookOpenCheck,
  ChartSpline,
  Clock3,
  LayoutGrid,
  ListChecks,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  Users,
} from "lucide-react";
import { ReactNode, useEffect, useMemo, useState } from "react";

import Button from "@/components/ui/Button";
import SidebarItem from "@/components/ui/SidebarItem";
import { clearSession, getUser } from "@/lib/auth";
import { Language } from "@/lib/types";
import { tr, UI_LANG_STORAGE_KEY, setUiLanguage as setLanguagePreference, useUiLanguage } from "@/lib/i18n";
import { assetPaths } from "@/src/assets";
import styles from "@/components/layout/DashboardLayout.module.css";

const SIDEBAR_STORAGE_KEY = "oku_sidebar_collapsed";
const MOBILE_NAV_LOCK_CLASS = "mobile-nav-locked";

interface DashboardLayoutProps {
  children: ReactNode;
}

interface NavItem {
  href: string;
  label: string;
  icon: ReactNode;
}

function getInitialSidebarCollapsed() {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1";
}

function getPageTitle(pathname: string, role: string | undefined, language: Language) {
  if (pathname.startsWith("/dashboard")) return tr(language, "Главная", "Басты бет");
  if (pathname.startsWith("/test")) return tr(language, "Тесты", "Тесттер");
  if (pathname.startsWith("/my-group")) return tr(language, "Моя группа", "Менің тобым");
  if (pathname.startsWith("/blitz")) return tr(language, "Блиц", "Блиц");
  if (pathname.startsWith("/results")) return tr(language, "Результаты", "Нәтижелер");
  if (pathname.startsWith("/history")) return tr(language, "История", "Тарих");
  if (pathname.startsWith("/progress")) return tr(language, "Аналитика", "Аналитика");
  if (pathname.startsWith("/teacher/groups")) return tr(language, "Группа", "Топ");
  if (pathname.startsWith("/teacher/students")) return tr(language, "Аналитика студента", "Оқушы аналитикасы");
  if (pathname.startsWith("/teacher/create-test")) return tr(language, "Создать тест", "Тест құру");
  if (pathname.startsWith("/teacher/tests")) return tr(language, "Мои тесты", "Менің тесттерім");
  if (pathname === "/teacher") return tr(language, "Группы", "Топтар");
  if (pathname.startsWith("/profile")) return tr(language, "Профиль", "Профиль");
  return role === "teacher" ? tr(language, "Группы", "Топтар") : "OKU";
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const router = useRouter();
  const pathname = usePathname();
  const user = getUser();

  const [collapsed, setCollapsed] = useState<boolean>(getInitialSidebarCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const uiLanguage = useUiLanguage();

  useEffect(() => {
    const savedLang = localStorage.getItem(UI_LANG_STORAGE_KEY);
    if (savedLang === "RU" || savedLang === "KZ") {
      setLanguagePreference(savedLang);
    }
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const html = document.documentElement;
    const body = document.body;
    if (window.innerWidth > 1024) {
      html.classList.remove(MOBILE_NAV_LOCK_CLASS);
      body.classList.remove(MOBILE_NAV_LOCK_CLASS);
      body.style.position = "";
      body.style.top = "";
      body.style.left = "";
      body.style.right = "";
      body.style.width = "";
      return;
    }

    if (mobileOpen) {
      const scrollY = window.scrollY;
      body.dataset.mobileNavScrollY = String(scrollY);
      html.classList.add(MOBILE_NAV_LOCK_CLASS);
      body.classList.add(MOBILE_NAV_LOCK_CLASS);
      body.style.position = "fixed";
      body.style.top = `-${scrollY}px`;
      body.style.left = "0";
      body.style.right = "0";
      body.style.width = "100%";
    } else {
      html.classList.remove(MOBILE_NAV_LOCK_CLASS);
      body.classList.remove(MOBILE_NAV_LOCK_CLASS);
      const savedScrollY = Number(body.dataset.mobileNavScrollY || "0");
      body.style.position = "";
      body.style.top = "";
      body.style.left = "";
      body.style.right = "";
      body.style.width = "";
      if (savedScrollY > 0) {
        window.scrollTo(0, savedScrollY);
      }
      delete body.dataset.mobileNavScrollY;
    }

    return () => {
      html.classList.remove(MOBILE_NAV_LOCK_CLASS);
      body.classList.remove(MOBILE_NAV_LOCK_CLASS);
      body.style.position = "";
      body.style.top = "";
      body.style.left = "";
      body.style.right = "";
      body.style.width = "";
      delete body.dataset.mobileNavScrollY;
    };
  }, [mobileOpen]);

  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const navItems: NavItem[] = useMemo(() => {
    if (user?.role === "teacher") {
      return [
        {
          href: "/teacher",
          label: t("Группы", "Топтар"),
          icon: <Users size={18} />,
        },
        {
          href: "/teacher/create-test",
          label: t("Создать тест", "Тест құру"),
          icon: <ClipboardPenLine size={18} />,
        },
        {
          href: "/teacher/tests",
          label: t("Мои тесты", "Менің тесттерім"),
          icon: <ListChecks size={18} />,
        },
      ];
    }

    return [
      {
        href: "/dashboard",
        label: t("Главная", "Басты бет"),
        icon: <LayoutGrid size={18} />,
      },
      {
        href: "/test",
        label: t("Тест", "Тест"),
        icon: <BookOpenCheck size={18} />,
      },
      {
        href: "/blitz",
        label: t("Блиц", "Блиц"),
        icon: <Bolt size={18} />,
      },
      {
        href: "/history",
        label: t("История", "Тарих"),
        icon: <Clock3 size={18} />,
      },
      {
        href: "/progress",
        label: t("Аналитика", "Аналитика"),
        icon: <ChartSpline size={18} />,
      },
      {
        href: "/my-group",
        label: t("Моя группа", "Менің тобым"),
        icon: <Users size={18} />,
      },
    ];
  }, [t, user?.role]);

  const isActive = (href: string) => {
    if (href === "/teacher") {
      return pathname === "/teacher" || pathname.startsWith("/teacher/groups/") || pathname.startsWith("/teacher/students/");
    }
    if (href === "/teacher/create-test") {
      return pathname.startsWith("/teacher/create-test");
    }
    if (href === "/teacher/tests") {
      return pathname.startsWith("/teacher/tests");
    }
    if (href === "/test") {
      return pathname.startsWith("/test") || pathname.startsWith("/results");
    }
    if (href === "/dashboard") {
      return pathname === "/dashboard";
    }
    return pathname === href || pathname.startsWith(`${href}/`);
  };

  const pageTitle = getPageTitle(pathname, user?.role, uiLanguage);
  const pageSubtitle = user?.role === "teacher" ? t("Панель преподавателя", "Оқытушы панелі") : t("Панель студента", "Оқушы панелі");
  const userInitial = (user?.username?.charAt(0) || "U").toUpperCase();

  const logout = () => {
    clearSession();
    router.replace("/");
  };

  const toggleCollapsed = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem(SIDEBAR_STORAGE_KEY, next ? "1" : "0");
  };

  const renderLanguageSwitch = () => (
    <div className={styles.langSwitch}>
      <button
        className={`${styles.langBtn} ${uiLanguage === "RU" ? styles.langActive : ""}`}
        type="button"
        onClick={() => setLanguagePreference("RU")}
      >
        RU
      </button>
      <button
        className={`${styles.langBtn} ${uiLanguage === "KZ" ? styles.langActive : ""}`}
        type="button"
        onClick={() => setLanguagePreference("KZ")}
      >
        KZ
      </button>
    </div>
  );

  const renderSidebar = (variant: "desktop" | "mobile") => {
    const isMobileVariant = variant === "mobile";
    const isCollapsedView = isMobileVariant ? false : collapsed;

    return (
      <aside className={`${styles.sidebar} ${isCollapsedView ? styles.sidebarCollapsed : ""} ${isMobileVariant ? styles.sidebarMobile : ""}`}>
        <div className={styles.brand}>
          <img alt="Логотип OKU" className={styles.logo} src={assetPaths.logo.svg} />
          <div className={styles.brandText}>
            <img alt="OKU" className={styles.brandWordmark} src={assetPaths.logo.textColor} />
          </div>
        </div>

        <div className={styles.collapseRow}>
          {isMobileVariant ? (
            <Button variant="ghost" onClick={() => setMobileOpen(false)} aria-label={t("Закрыть меню", "Мәзірді жабу")}>
              <PanelLeftClose size={16} />
            </Button>
          ) : (
            <Button
              className={styles.collapseToggle}
              variant="ghost"
              onClick={toggleCollapsed}
              aria-label={collapsed ? t("Раскрыть меню", "Мәзірді кеңейту") : t("Свернуть меню", "Мәзірді жинау")}
            >
              <img
                src={assetPaths.icons.sidebarArrow}
                alt=""
                aria-hidden="true"
                className={`${styles.collapseArrow} ${collapsed ? styles.collapseArrowCollapsed : styles.collapseArrowExpanded}`}
              />
            </Button>
          )}
        </div>

        <nav className={styles.nav}>
          {navItems.map((item) => (
            <SidebarItem
              key={item.href}
              href={item.href}
              label={item.label}
              icon={item.icon}
              collapsed={isCollapsedView}
              active={isActive(item.href)}
              onClick={() => {
                if (isMobileVariant) {
                  setMobileOpen(false);
                }
              }}
            />
          ))}
        </nav>

        <div className={styles.footer}>
          {isMobileVariant ? (
            <>
              {renderLanguageSwitch()}
              <div className={styles.mobileToolRow}>
                <Button className={styles.mobileToolButton} variant="ghost" aria-label={t("Уведомления", "Хабарламалар")}>
                  <Bell size={16} />
                  <span>{t("Уведомления", "Хабарламалар")}</span>
                </Button>
                <Button className={styles.mobileToolButton} variant="ghost" aria-label={t("Тема", "Тақырып")}>
                  <Moon size={16} />
                  <span>{t("Тема", "Тақырып")}</span>
                </Button>
              </div>
              <button type="button" className={`${styles.mobileProfile} ${styles.profileButton}`} onClick={() => router.push("/profile")}>
                <span className={styles.avatar}>{userInitial}</span>
                <div className={styles.mobileProfileMeta}>
                  <span className={styles.userName}>{user?.username ?? "user"}</span>
                  <span className={styles.userRole}>{user?.role === "teacher" ? t("Учитель", "Оқытушы") : t("Студент", "Оқушы")}</span>
                </div>
              </button>
              <Button block variant="ghost" onClick={logout}>
                <LogOut size={16} /> {t("Выход", "Шығу")}
              </Button>
            </>
          ) : (
            <Button block variant="ghost" onClick={logout}>
              <LogOut size={16} /> {!collapsed ? t("Выход", "Шығу") : ""}
            </Button>
          )}
        </div>
      </aside>
    );
  };

  return (
    <div className={styles.frame}>
      {renderSidebar("desktop")}

      <div className={styles.overlay + (mobileOpen ? ` ${styles.overlayOpen}` : "")} onClick={() => setMobileOpen(false)} />
      <div className={styles.mobileSidebar + (mobileOpen ? ` ${styles.mobileSidebarOpen}` : "")}>{renderSidebar("mobile")}</div>

      <div className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.topbarLeft}>
            <Button className={styles.mobileMenuButton} variant="ghost" onClick={() => setMobileOpen(true)} aria-label={t("Открыть меню", "Мәзірді ашу")}>
              <Menu size={18} />
            </Button>
            <div className={styles.topbarTitle}>
              <h1>{pageTitle}</h1>
              <p>{pageSubtitle}</p>
            </div>
          </div>

          <div className={styles.topbarRight}>
            {renderLanguageSwitch()}

            <Button className={styles.iconButton} variant="ghost" aria-label={t("Уведомления", "Хабарламалар")}>
              <Bell size={16} />
            </Button>
            <Button className={styles.iconButton} variant="ghost" aria-label={t("Тема", "Тақырып")}>
              <Moon size={16} />
            </Button>

            <button type="button" className={`${styles.profile} ${styles.profileButton}`} onClick={() => router.push("/profile")}>
              <span className={styles.avatar}>{userInitial}</span>
              <div className={styles.profileMeta}>
                <span className={styles.userName}>{user?.username ?? "user"}</span>
                <span className={styles.userRole}>{user?.role === "teacher" ? t("Учитель", "Оқытушы") : t("Студент", "Оқушы")}</span>
              </div>
            </button>

            <Button className={styles.iconButton} variant="ghost" onClick={logout} aria-label={t("Выйти", "Шығу")}>
              <LogOut size={16} />
            </Button>
          </div>
        </header>

        <main className={styles.content}>{children}</main>
      </div>
    </div>
  );
}
