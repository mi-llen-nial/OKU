import type { ReactNode } from "react";

import PublicSiteLayout from "@/components/public/PublicSiteLayout";

export default function PublicMarketingLayout({ children }: { children: ReactNode }) {
  return <PublicSiteLayout>{children}</PublicSiteLayout>;
}
