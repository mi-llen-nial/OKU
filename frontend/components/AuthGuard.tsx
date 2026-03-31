"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { getToken, getUser } from "@/lib/auth";
import { resolveRoleHome } from "@/lib/navigation";
import { tr, useUiLanguage } from "@/lib/i18n";
import { UserRole } from "@/lib/types";

interface AuthGuardProps {
  roles?: UserRole[];
  children: React.ReactNode;
}

export default function AuthGuard({ roles, children }: AuthGuardProps) {
  const router = useRouter();
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);
  const [ready, setReady] = useState(false);
  const rolesKey = roles?.join("|") || "";
  const allowedRoles = useMemo(() => (rolesKey ? (rolesKey.split("|") as UserRole[]) : undefined), [rolesKey]);

  useEffect(() => {
    const token = getToken();
    const user = getUser();

    if (!token || !user) {
      const nextPath =
        typeof window !== "undefined"
          ? `${window.location.pathname || "/"}${window.location.search || ""}`
          : "/";
      const encodedNext = encodeURIComponent(nextPath);
      router.replace(`/login?next=${encodedNext}`);
      return;
    }

    if (user.role === "superadmin") {
      setReady(true);
      return;
    }

    if (allowedRoles && !allowedRoles.includes(user.role)) {
      router.replace(resolveRoleHome(user.role));
      return;
    }

    setReady(true);
  }, [allowedRoles, router]);

  if (!ready) {
    return <div className="pageLoading">{t("Загрузка...", "Жүктелуде...")}</div>;
  }

  return <>{children}</>;
}
