"use client";

import { useState } from "react";

import landingStyles from "@/app/landing.module.css";

export type FaqItem = {
  qRu: string;
  qKz: string;
  aRu: ReadonlyArray<string>;
  aKz: ReadonlyArray<string>;
};

type Props = {
  items: ReadonlyArray<FaqItem>;
  t: (ru: string, kz: string) => string;
  initialOpenIndex?: number;
};

export default function FaqAccordion({ items, t, initialOpenIndex = 0 }: Props) {
  const [openFaq, setOpenFaq] = useState<number>(initialOpenIndex);

  return (
    <div className={landingStyles.faqList}>
      {items.map((item, index) => {
        const expanded = openFaq === index;

        return (
          <div key={item.qRu} className={landingStyles.faqCard}>
            <button
              type="button"
              className={landingStyles.faqQuestionBtn}
              aria-expanded={expanded}
              id={`faq-q-${index}`}
              aria-controls={`faq-a-${index}`}
              onClick={() => setOpenFaq((prev) => (prev === index ? -1 : index))}
            >
              <span className={landingStyles.faqQuestion}>{t(item.qRu, item.qKz)}</span>
              <svg
                className={expanded ? landingStyles.faqChevronIconOpen : landingStyles.faqChevronIcon}
                viewBox="0 0 24 24"
                aria-hidden
              >
                <path
                  d="M6 9l6 6 6-6"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>

            <div
              id={`faq-a-${index}`}
              role="region"
              aria-labelledby={`faq-q-${index}`}
              className={`${landingStyles.faqAnswerPanel} ${expanded ? landingStyles.faqAnswerPanelOpen : ""}`}
            >
              <div className={landingStyles.faqAnswerMeasure}>
                <div className={landingStyles.faqAnswerBody}>
                  {item.aRu.map((_, i) => (
                    <p key={i} className={landingStyles.faqAnswer}>
                      {t(item.aRu[i], item.aKz[i])}
                    </p>
                  ))}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

