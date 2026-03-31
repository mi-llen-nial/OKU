import type { Metadata } from "next";

import PricingPageContent from "@/components/public/PricingPageContent";

export const metadata: Metadata = {
  title: "Цены",
  description: "Тарифы OKU для учебных заведений: малые, средние и крупные пакеты по численности учащихся.",
  alternates: { canonical: "/price" },
};

export default function PricePage() {
  return <PricingPageContent />;
}
