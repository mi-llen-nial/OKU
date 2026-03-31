import { publicSiteOrigin } from "@/src/config/domains";

export const siteConfig = {
  name: "OKU",
  shortName: "OKU",
  domain: "oku.com.kz",
  locale: "ru_KZ",
  description:
    "OKU — образовательная AI-платформа для персонализированных тестов, подготовки к ЕНТ и IELTS, анализа прогресса и работы над ошибками.",
  keywords: [
    "OKU",
    "образовательная платформа",
    "подготовка к ЕНТ",
    "подготовка к IELTS",
    "онлайн тесты",
    "персонализированное обучение",
    "анализ прогресса",
    "платформа для учеников и преподавателей",
  ],
  ogImage: "/assets/logo/logo.png",
  telegram: {
    okuBotUrl: "https://t.me/KOMA_OKU_bot",
    faqBotUrl: "https://t.me/KOMA_FAQ_bot",
  },
};

/** Canonical public marketing origin (no trailing slash). Same as NEXT_PUBLIC_PUBLIC_SITE_URL / NEXT_PUBLIC_SITE_URL. */
export const siteUrl = publicSiteOrigin;

export function absoluteUrl(path = "/"): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${siteUrl}${normalizedPath}`;
}
