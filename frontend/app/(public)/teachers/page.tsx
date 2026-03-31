import type { Metadata } from "next";

import TeachersPageContent from "@/components/public/TeachersPageContent";

export const metadata: Metadata = {
  title: "Для преподавателей",
  description:
    "OKU для преподавателей: создание тестов вручную, с AI и из файла, система предупреждений и достоверность результатов.",
  alternates: { canonical: "/teachers" },
};

export default function TeachersPage() {
  return <TeachersPageContent />;
}
