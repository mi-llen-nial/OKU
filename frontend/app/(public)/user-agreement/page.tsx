import type { Metadata } from "next";

import UserAgreementPageContent from "@/components/public/UserAgreementPageContent";

export const metadata: Metadata = {
  title: "Пользовательское соглашение",
  description: "Пользовательское соглашение сервиса OKU.",
  alternates: { canonical: "/user-agreement" },
};

export default function UserAgreementPage() {
  return <UserAgreementPageContent />;
}
