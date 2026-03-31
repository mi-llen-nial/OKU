"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import styles from "./reveal.module.css";

type Props = {
  children: ReactNode;
  className?: string;
};

export default function RevealOnScroll({ children, className }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setVisible(true);
      return;
    }

    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setVisible(true);
        });
      },
      { root: null, rootMargin: "0px 0px -6% 0px", threshold: [0, 0.06, 0.12] },
    );

    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Базовые inline-стили на случай, если CSS-модули успевают подгрузиться не сразу.
  // Это уменьшает "моргание" контента на доли секунды при первой отрисовке.
  const inlineStyle: React.CSSProperties = visible
    ? {
        opacity: 1,
        transform: "translate3d(0, 0, 0)",
        transition:
          "opacity 0.7s cubic-bezier(0.22, 1, 0.36, 1), transform 0.7s cubic-bezier(0.22, 1, 0.36, 1)",
        willChange: "opacity, transform",
      }
    : {
        opacity: 0,
        transform: "translate3d(0, 18px, 0)",
        transition:
          "opacity 0.7s cubic-bezier(0.22, 1, 0.36, 1), transform 0.7s cubic-bezier(0.22, 1, 0.36, 1)",
        willChange: "opacity, transform",
      };

  return (
    <div
      ref={ref}
      style={inlineStyle}
      className={`${styles.reveal} ${visible ? styles.revealVisible : ""}${className ? ` ${className}` : ""}`}
    >
      {children}
    </div>
  );
}
