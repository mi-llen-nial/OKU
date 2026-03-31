"use client";

import { assetPaths } from "@/src/assets";
import { tr, useUiLanguage } from "@/lib/i18n";

import RevealOnScroll from "./RevealOnScroll";
import styles from "./pricingPage.module.css";

const FEATURE_KEYS = ["f1", "f2", "f3"] as const;

const FEATURE_I18N: Record<(typeof FEATURE_KEYS)[number], { ru: string; kz: string }> = {
  f1: {
    ru: "Поддержка 24/7 и обслуживание",
    kz: "24/7 қолдау және қызмет көрсету",
  },
  f2: {
    ru: "Руководство и интеграция платформы",
    kz: "Басшылық және платформаны интеграциялау",
  },
  f3: {
    ru: "Неограниченное кол-во генерации",
    kz: "Шексіз генерация саны",
  },
};

const TIERS = [
  {
    id: "small" as const,
    titleLead: { ru: "Для ", kz: "Үшін " },
    titleBold: { ru: "малых", kz: "шағын" },
    titleTrail: { ru: " учебных учреждений", kz: " білім беру ұйымдары" },
    priceValue: "990₸",
    priceSuffix: { ru: "/ месяц за 1 ученика", kz: "/ айға 1 оқушы" },
  },
  {
    id: "medium" as const,
    titleLead: { ru: "Для ", kz: "Үшін " },
    titleBold: { ru: "средних", kz: "орта" },
    titleTrail: { ru: " учебных учреждений", kz: " білім беру ұйымдары" },
    priceValue: "860₸",
    priceSuffix: { ru: "/ месяц за 1 ученика", kz: "/ айға 1 оқушы" },
  },
  {
    id: "large" as const,
    titleLead: { ru: "Для ", kz: "Үшін " },
    titleBold: { ru: "крупных", kz: "ірі" },
    titleTrail: { ru: " учебных учреждений", kz: " білім беру ұйымдары" },
    priceValue: "640₸",
    priceSuffix: { ru: "/ месяц за 1 ученика", kz: "/ айға 1 оқушы" },
  },
] as const;

const FOOTNOTE = {
  ru: "Все для преподавателей, активных студентов, методистов и администрации учебных организаций.",
  kz: "Оқытушылар, белсенді студенттер, әдістемелік және оқу ұйымдары әкімшілігі үшін барлығы.",
};

function CapacityLine({
  tierId,
  t,
}: {
  tierId: (typeof TIERS)[number]["id"];
  t: (ru: string, kz: string) => string;
}) {
  if (tierId === "small") {
    return (
      <p className={styles.capacity}>
        {t("до ", "")}
        <strong>1000</strong>
        {t(" учеников", " оқушыға дейін")}
      </p>
    );
  }
  if (tierId === "medium") {
    return (
      <p className={styles.capacity}>
        {t("от ", "")}
        <strong>1000</strong>
        {t(" до ", "–")}
        <strong>2000</strong>
        {t(" учеников", " оқушы")}
      </p>
    );
  }
  return (
    <p className={styles.capacity}>
      {t("от ", "")}
      <strong>2000</strong>
      {t(" до ", "–")}
      <strong>2500</strong>
      {t(" учеников", " оқушы")}
    </p>
  );
}

export default function PricingPageContent() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{t("Цены", "Бағалар")}</h1>
      <p className={styles.lead}>
        {t(
          "Тарифы для учебных заведений зависят от численности учащихся. Ниже — ориентировочные пакеты.",
          "Оқу орындарының тарифтері оқушылар санына байланысты. Төменде бағдарлық пакеттер ұсынылады.",
        )}
      </p>

      <RevealOnScroll>
        <div className={styles.grid}>
          {TIERS.map((tier) => (
            <article key={tier.id} className={styles.card}>
              <h2 className={styles.cardTitle}>
                <span>{t(tier.titleLead.ru, tier.titleLead.kz)}</span>
                <strong>{t(tier.titleBold.ru, tier.titleBold.kz)}</strong>
                <span>{t(tier.titleTrail.ru, tier.titleTrail.kz)}</span>
              </h2>

              <CapacityLine tierId={tier.id} t={t} />

              <div className={styles.priceRow}>
                <span className={styles.priceValue}>{tier.priceValue}</span>
                <span className={styles.priceSuffix}>{t(tier.priceSuffix.ru, tier.priceSuffix.kz)}</span>
              </div>

              <ul className={styles.features}>
                {FEATURE_KEYS.map((key) => (
                  <li key={key} className={styles.feature}>
                    <span className={styles.checkWrap}>
                      <img className={styles.checkIcon} src={assetPaths.icons.checkFill} alt="" />
                    </span>
                    <span>{t(FEATURE_I18N[key].ru, FEATURE_I18N[key].kz)}</span>
                  </li>
                ))}
              </ul>

              <p className={styles.cardFootnote}>{t(FOOTNOTE.ru, FOOTNOTE.kz)}</p>
            </article>
          ))}
        </div>
      </RevealOnScroll>
    </div>
  );
}
