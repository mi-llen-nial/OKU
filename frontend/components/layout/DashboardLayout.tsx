"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  Bell,
  BookOpenCheck,
  ChartSpline,
  Clock3,
  FolderPlus,
  LayoutGrid,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Users,
} from "lucide-react";
import { ReactNode, useEffect, useMemo, useState } from "react";

import Button from "@/components/ui/Button";
import SidebarItem from "@/components/ui/SidebarItem";
import { clearSession, getUser } from "@/lib/auth";
import { Language } from "@/lib/types";
import { assetPaths } from "@/src/assets";
import styles from "@/components/layout/DashboardLayout.module.css";

const SIDEBAR_STORAGE_KEY = "oku_sidebar_collapsed";
const UI_LANG_STORAGE_KEY = "oku_ui_lang";

interface DashboardLayoutProps {
  children: ReactNode;
}

interface NavItem {
  href: string;
  label: string;
  icon: ReactNode;
}

function getPageTitle(pathname: string, role?: string) {
  if (pathname.startsWith("/dashboard")) return "Главная";
  if (pathname.startsWith("/test")) return "Тесты";
  if (pathname.startsWith("/results")) return "Результаты";
  if (pathname.startsWith("/history")) return "История";
  if (pathname.startsWith("/progress")) return "Аналитика";
  if (pathname.startsWith("/teacher/create-group")) return "Создать группу";
  if (pathname.startsWith("/teacher/groups")) return "Группа";
  if (pathname.startsWith("/teacher/students")) return "Аналитика студента";
  if (pathname === "/teacher") return "Группы";
  if (pathname.startsWith("/profile")) return "Профиль";
  return role === "teacher" ? "Группы" : "OKU";
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const router = useRouter();
  const pathname = usePathname();
  const user = getUser();

  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [uiLanguage, setUiLanguage] = useState<Language>("RU");

  useEffect(() => {
    const saved = localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (saved === "1") {
      setCollapsed(true);
    }

    const savedLang = localStorage.getItem(UI_LANG_STORAGE_KEY);
    if (savedLang === "RU" || savedLang === "KZ") {
      setUiLanguage(savedLang);
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.uiLanguage = uiLanguage;
    localStorage.setItem(UI_LANG_STORAGE_KEY, uiLanguage);
  }, [uiLanguage]);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const navItems: NavItem[] = useMemo(() => {
    if (user?.role === "teacher") {
      return [
        {
          href: "/teacher",
          label: "Группы",
          icon: <Users size={18} />,
        },
        {
          href: "/teacher/create-group",
          label: "Создать группу",
          icon: <FolderPlus size={18} />,
        },
      ];
    }

    return [
      {
        href: "/dashboard",
        label: "Главная",
        icon: <LayoutGrid size={18} />,
      },
      {
        href: "/test",
        label: "Тест",
        icon: <BookOpenCheck size={18} />,
      },
      {
        href: "/history",
        label: "История",
        icon: <Clock3 size={18} />,
      },
      {
        href: "/progress",
        label: "Аналитика",
        icon: <ChartSpline size={18} />,
      },
    ];
  }, [user?.role]);

  const isActive = (href: string) => {
    if (href === "/teacher") {
      return pathname === "/teacher" || pathname.startsWith("/teacher/groups/") || pathname.startsWith("/teacher/students/");
    }
    if (href === "/teacher/create-group") {
      return pathname === "/teacher/create-group";
    }
    if (href === "/test") {
      return pathname.startsWith("/test") || pathname.startsWith("/results");
    }
    if (href === "/dashboard") {
      return pathname === "/dashboard";
    }
    return pathname === href || pathname.startsWith(`${href}/`);
  };

  const pageTitle = getPageTitle(pathname, user?.role);
  const pageSubtitle = user?.role === "teacher" ? "Панель преподавателя" : "Панель студента";
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
        onClick={() => setUiLanguage("RU")}
      >
        RU
      </button>
      <button
        className={`${styles.langBtn} ${uiLanguage === "KZ" ? styles.langActive : ""}`}
        type="button"
        onClick={() => setUiLanguage("KZ")}
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
          <img alt="Логотип OKU" className={styles.logo} src={assetPaths.logo.png} />
          <div className={styles.brandText}>
            <strong>OKU</strong>
            <small>Образовательная платформа</small>
          </div>
        </div>

        <div className={styles.collapseRow}>
          {isMobileVariant ? (
            <Button variant="ghost" onClick={() => setMobileOpen(false)} aria-label="Закрыть меню">
              <PanelLeftClose size={16} />
            </Button>
          ) : (
            <Button variant="ghost" onClick={toggleCollapsed} aria-label={collapsed ? "Раскрыть меню" : "Свернуть меню"}>
              {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
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
                <Button className={styles.mobileToolButton} variant="ghost" aria-label="Уведомления">
                  <Bell size={16} />
                  <span>Уведомления</span>
                </Button>
                <Button className={styles.mobileToolButton} variant="ghost" aria-label="Тема">
                  <Moon size={16} />
                  <span>Тема</span>
                </Button>
              </div>
              <button type="button" className={`${styles.mobileProfile} ${styles.profileButton}`} onClick={() => router.push("/profile")}>
                <span className={styles.avatar}>{userInitial}</span>
                <div className={styles.mobileProfileMeta}>
                  <span className={styles.userName}>{user?.username ?? "user"}</span>
                  <span className={styles.userRole}>{user?.role === "teacher" ? "Учитель" : "Студент"}</span>
                </div>
              </button>
              <Button block variant="ghost" onClick={logout}>
                <LogOut size={16} /> Выход
              </Button>
            </>
          ) : (
            <Button block variant="ghost" onClick={logout}>
              <LogOut size={16} /> {!collapsed ? "Выход" : ""}
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
            <Button className={styles.mobileMenuButton} variant="ghost" onClick={() => setMobileOpen(true)} aria-label="Открыть меню">
              <Menu size={18} />
            </Button>
            <div className={styles.topbarTitle}>
              <h1>{pageTitle}</h1>
              <p>{pageSubtitle}</p>
            </div>
          </div>

          <div className={styles.topbarRight}>
            {renderLanguageSwitch()}

            <Button className={styles.iconButton} variant="ghost" aria-label="Уведомления">
              <Bell size={16} />
            </Button>
            <Button className={styles.iconButton} variant="ghost" aria-label="Тема">
              <Moon size={16} />
            </Button>

            <button type="button" className={`${styles.profile} ${styles.profileButton}`} onClick={() => router.push("/profile")}>
              <span className={styles.avatar}>{userInitial}</span>
              <div className={styles.profileMeta}>
                <span className={styles.userName}>{user?.username ?? "user"}</span>
                <span className={styles.userRole}>{user?.role === "teacher" ? "Учитель" : "Студент"}</span>
              </div>
            </button>

            <Button className={styles.iconButton} variant="ghost" onClick={logout} aria-label="Выйти">
              <LogOut size={16} />
            </Button>
          </div>
        </header>

        <main className={styles.content}>{children}</main>
      </div>
    </div>
  );
}
