import type { Metadata } from "next";

import StudentsPageContent from "@/components/public/StudentsPageContent";

export const metadata: Metadata = {
  title: "Для учеников",
  description:
    "OKU для учеников: более 10 направлений, современное тестирование, подготовка к ЕНТ и IELTS, персонализированное обучение.",
  alternates: { canonical: "/students" },
};

export default function StudentsPage() {
  return <StudentsPageContent />;
}
