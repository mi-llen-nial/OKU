import { ReactNode } from "react";

import styles from "@/components/ui/StatWidget.module.css";

interface StatWidgetProps {
  label: string;
  value: string;
  meta?: string;
  icon?: ReactNode;
}

export default function StatWidget({ label, value, meta, icon }: StatWidgetProps) {
  return (
    <article className={styles.widget}>
      <div className={styles.head}>
        <span className={styles.label}>{label}</span>
        {icon}
      </div>
      <div className={styles.value}>{value}</div>
      {meta && <div className={styles.meta}>{meta}</div>}
    </article>
  );
}
