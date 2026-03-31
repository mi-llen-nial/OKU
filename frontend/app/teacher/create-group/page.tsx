"use client";

import { useRouter } from "next/navigation";

import AppShell from "@/components/AppShell";
import AuthGuard from "@/components/AuthGuard";
import Button from "@/components/ui/Button";
import { tr, useUiLanguage } from "@/lib/i18n";
import styles from "@/app/teacher/create-group/create-group.module.css";

export default function CreateGroupPage() {
  const router = useRouter();
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  return (
    <AuthGuard roles={["teacher"]}>
      <AppShell>
        <div className={styles.page}>
          <section className={styles.section}>
            <header className={styles.header}>
              <h2>{t("Создание групп", "Топ құру")}</h2>
              <p>
                {t(
                  "Официальные группы создаёт администратор учебного учреждения.",
                  "Ресми топтарды оқу орнының әкімшісі құрады.",
                )}
              </p>
            </header>

            <div className={styles.actions}>
              <Button variant="secondary" onClick={() => router.push("/teacher")}>
                {t("К моим группам", "Менің топтарыма")}
              </Button>
              <Button variant="ghost" onClick={() => router.push("/teacher/tests")}>
                {t("К моим тестам", "Менің тесттеріме")}
              </Button>
            </div>
          </section>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
