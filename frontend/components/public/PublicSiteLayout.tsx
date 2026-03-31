import type { ReactNode } from "react";

import PublicSiteFooter from "./PublicSiteFooter";
import PublicSiteHeader from "./PublicSiteHeader";

import styles from "./publicSite.module.css";

export default function PublicSiteLayout({ children }: { children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <PublicSiteHeader />
      <div className={styles.main}>{children}</div>
      <PublicSiteFooter />
    </div>
  );
}
