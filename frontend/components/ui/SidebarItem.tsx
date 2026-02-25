import Link from "next/link";
import { ReactNode } from "react";

import { classNames } from "@/components/ui/classNames";
import styles from "@/components/ui/SidebarItem.module.css";

interface SidebarItemProps {
  href: string;
  icon: ReactNode;
  label: string;
  active?: boolean;
  collapsed?: boolean;
  onClick?: () => void;
}

export default function SidebarItem({ href, icon, label, active = false, collapsed = false, onClick }: SidebarItemProps) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className={classNames(styles.link, active && styles.active, collapsed && styles.collapsed)}
      title={label}
    >
      <span className={styles.icon}>{icon}</span>
      <span className={styles.label}>{label}</span>
    </Link>
  );
}
