import type { Metadata } from "next";

import InstitutionsPageContent from "@/components/public/InstitutionsPageContent";

export const metadata: Metadata = {
  title: "Для учреждений",
  description: "OKU для школ и колледжей: администрирование, заявки преподавателей, методическая поддержка.",
  alternates: { canonical: "/institutions" },
};

export default function InstitutionsPage() {
  return <InstitutionsPageContent />;
}
