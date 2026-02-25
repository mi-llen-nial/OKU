import { ReactNode } from "react";

import { classNames } from "@/components/ui/classNames";
import styles from "@/components/ui/Card.module.css";

interface CardProps {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}

export default function Card({ title, subtitle, action, className, children }: CardProps) {
  return (
    <section className={classNames(styles.card, className)}>
      {(title || subtitle || action) && (
        <div className={styles.header}>
          <div>
            {title && <h3 className={styles.title}>{title}</h3>}
            {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      <div className={styles.content}>{children}</div>
    </section>
  );
}
