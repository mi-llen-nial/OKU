import { ButtonHTMLAttributes } from "react";

import { classNames } from "@/components/ui/classNames";
import styles from "@/components/ui/Button.module.css";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  block?: boolean;
}

export default function Button({
  className,
  variant = "primary",
  block = false,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      className={classNames(styles.button, styles[variant], block && styles.block, className)}
      type={type}
      {...props}
    />
  );
}
