import { ReactNode } from "react";

import { classNames } from "@/components/ui/classNames";
import styles from "@/components/ui/Badge.module.css";

type BadgeVariant = "normal" | "success" | "danger" | "info";

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

export default function Badge({ children, variant = "normal", className }: BadgeProps) {
  return <span className={classNames(styles.badge, styles[variant], className)}>{children}</span>;
}
