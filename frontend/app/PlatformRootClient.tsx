"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { getToken, getUser } from "@/lib/auth";
import { resolveRoleHome } from "@/lib/navigation";
import { tr, useUiLanguage } from "@/lib/i18n";

export default function PlatformRootClient() {
  const router = useRouter();
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  useEffect(() => {
    const token = getToken();
    const user = getUser();
    if (!token || !user) {
      router.replace("/login");
      return;
    }
    router.replace(resolveRoleHome(user.role));
  }, [router]);

  return (
    <div className="pageLoading" style={{ padding: "3rem 1rem", textAlign: "center" }}>
      {t("Загрузка...", "Жүктелуде...")}
    </div>
  );
}
