const DEFAULT_SITE_URL = "https://oku.com.kz";

function normalizeSiteUrl(raw: string | undefined): string {
  const value = (raw || "").trim();
  if (!value) return DEFAULT_SITE_URL;
  try {
    const parsed = new URL(value);
    const protocol = parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.protocol : "https:";
    return `${protocol}//${parsed.host}`;
  } catch {
    return DEFAULT_SITE_URL;
  }
}

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

export const siteUrl = normalizeSiteUrl(process.env.NEXT_PUBLIC_SITE_URL);

export function absoluteUrl(path = "/"): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${siteUrl}${normalizedPath}`;
}
