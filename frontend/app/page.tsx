import { headers } from "next/headers";

import LandingPageContent from "@/components/public/LandingPageContent";
import PublicSiteLayout from "@/components/public/PublicSiteLayout";
import { isAppHostname, isLocalDevHostname } from "@/src/config/domains";

import PlatformRootClient from "./PlatformRootClient";

export default function HomePage() {
  const host = headers().get("x-forwarded-host") ?? headers().get("host") ?? "";

  if (isAppHostname(host) && !isLocalDevHostname(host)) {
    return <PlatformRootClient />;
  }

  return (
    <PublicSiteLayout>
      <LandingPageContent />
    </PublicSiteLayout>
  );
}
