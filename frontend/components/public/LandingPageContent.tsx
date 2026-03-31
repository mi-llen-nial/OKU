"use client";

import Link from "next/link";

import { appPath } from "@/src/config/domains";
import { tr, useUiLanguage } from "@/lib/i18n";
import { assetPaths } from "@/src/assets";
import styles from "@/app/landing.module.css";

import RevealOnScroll from "./RevealOnScroll";
import FaqAccordion from "./FaqAccordion";

const FAQ_ITEMS = [
  {
    qRu: "Что такое OKU?",
    qKz: "OKU деген не?",
    aRu: [
      "OKU — это образовательная платформа для тестирования, анализа знаний и персонализированного обучения.",
      "Она помогает ученикам лучше понимать свои слабые темы, преподавателям — быстрее работать с тестами и материалами, а учебным учреждениям — более удобно управлять процессом оценки знаний.",
    ],
    aKz: [
      "OKU — білімді тексеру, талдау және жекелендірілген оқу үшін білім беру платформасы.",
      "Ол оқушыларға әлсіз тақырыптарды жақсырақ түсінуге, оқытушыларға тесттер мен материалдармен жылдамырақ жұмыс істеуге, ал оқу орындарына білімді бағалау процесін ыңғайлырақ басқаруға көмектеседі.",
    ],
  },
  {
    qRu: "Чем OKU отличается от обычных платформ для тестов?",
    qKz: "OKU қарапайым тест платформаларынан несімен ерекшеленеді?",
    aRu: [
      "OKU — это не просто система для прохождения тестов.",
      "Платформа объединяет тестирование, аналитику, объяснения, рекомендации и роли для разных участников учебного процесса. Это делает ее не только инструментом проверки, но и частью современного обучения.",
    ],
    aKz: [
      "OKU — тек тест өткізу жүйесі емес.",
      "Платформа тестілеу, аналитика, түсіндірмелер, ұсыныстар және оқу процесінің әртүрлі қатысушыларының рөлдерін біріктіреді. Сондықтан ол тек тексеру құралы ғана емес, заманауи оқудың бір бөлігі.",
    ],
  },
  {
    qRu: "Почему платформа особенно актуальна в эпоху AI?",
    qKz: "Неге платформа AI дәуірінде ерекше өзекті?",
    aRu: [
      "Потому что традиционные формы проверки знаний уже не всегда отражают реальный уровень подготовки.",
      "Когда готовый ответ можно быстро получить с помощью AI, особенно важно использовать более современные подходы к оцениванию. OKU помогает с высокой вероятностью делать оценку знаний более достоверной и полезной для дальнейшего обучения.",
    ],
    aKz: [
      "Дәстүрлі білім тексеру формалары дайындықтың нақты деңгейін әрқашан көрсете бермейді.",
      "Дайын жауапты AI арқылы жылдамырақ алуға болатын кезде, бағалаудың заманауи тәсілдерін пайдалану ерекше маңызды. OKU білімді бағалауды сенімдірек және одан әрі оқуға пайдалы етуге көмектеседі.",
    ],
  },
  {
    qRu: "Для кого подходит OKU?",
    qKz: "OKU кімге арналған?",
    aRu: [
      "OKU подходит ученикам, преподавателям и учебным учреждениям.",
      "Ученики получают обратную связь и прогресс, преподаватели — инструменты для создания и проведения тестов, а учреждения — централизованную систему с ролями, управлением и аналитикой.",
    ],
    aKz: [
      "OKU оқушыларға, оқытушыларға және оқу орындарына сай келеді.",
      "Оқушылар кері байланыс және прогресс алады, оқытушылар — тесттерді құру және өткізу құралдары, ал оқу орындары — рөлдер, басқару және аналитикасы бар орталықтандырылған жүйе.",
    ],
  },
  {
    qRu: "Можно ли использовать OKU в школе, колледже или университете?",
    qKz: "OKU мектепте, колледжде немесе университетте қолданыла ма?",
    aRu: [
      "Да, платформа как раз рассчитана на работу в образовательной среде.",
      "OKU поддерживает распределение ролей между учеником, преподавателем, методистом и администратором, что позволяет выстраивать более удобный и прозрачный учебный процесс внутри учреждения.",
    ],
    aKz: [
      "Иә, платформа дәл білім беру ортасында жұмыс істеуге есептелген.",
      "OKU оқушы, оқытушы, әдістемелік және әкімші арасындағы рөлдерді қолдайды, бұл оқу орны ішінде ыңғайлырақ және ашық оқу процесін құруға мүмкіндік береді.",
    ],
  },
  {
    qRu: "OKU — это уже готовый продукт или пока только идея?",
    qKz: "OKU дайын өнім бе әлде әлі идея ма?",
    aRu: [
      "OKU — это развивающийся продукт, а не просто концепция.",
      "Платформа уже тестировалась на пользователях и продолжает развиваться как современное решение для образования, которое объединяет технологичность, удобство и практическую ценность.",
    ],
    aKz: [
      "OKU — жалпы концепция емес, дамып келе жатқан өнім.",
      "Платформа пайдаланушыларда сыналды және білім беру үшін заманауи шешім ретінде дамуда — технологиялылық, ыңғайлылық және практикалық құндылықты біріктіреді.",
    ],
  },
  {
    qRu: "Почему результаты тестов в OKU имеют высокий уровень достоверности?",
    qKz: "Неге OKU тест нәтижелері жоғары сенімділікке ие?",
    aRu: [
      "OKU использует систему детекции подозрительных действий во время прохождения теста, что помогает с высокой вероятностью делать результаты более достоверными.",
      "Такой подход уже был протестирован на более чем 500 пользователях.",
      "Важное условие — ученик должен проходить тест только с одного устройства: либо с телефона, либо с компьютера.",
    ],
    aKz: [
      "OKU тест өткізу кезінде күдікті әрекеттерді анықтау жүйесін қолданады, бұл нәтижелерді сенімдірек етуге көмектеседі.",
      "Бұл тәсіл 500-ден астам пайдаланушыға сыналды.",
      "Маңызды шарт — оқушы тестті тек бір құрылғыдан өтуі керек: телефоннан немесе компьютерден.",
    ],
  },
] as const;

const FEATURE_CARDS = [
  {
    labelRu: "Ученик",
    labelKz: "Оқушы",
    titleRu: "Современное тестирование",
    titleKz: "Қазіргі заманғы тестілеу",
    textRu:
      "OKU объединяет прохождение тестов, анализ ошибок, объяснения, рекомендации и учебную аналитику в одной системе",
    textKz:
      "OKU тесттерді өту, қателерді талдау, түсіндірмелер, ұсыныстар және оқу аналитикасын бір жүйеде біріктіреді",
    icon: assetPaths.illustrations.landingModernTest,
  },
  {
    labelRu: "Преподаватель",
    labelKz: "Оқытушы",
    titleRu: "Инструменты",
    titleKz: "Құралдар",
    textRu:
      "Быстрое создание тестов и презентаций, AI-генерация, и удобная работа с учебными материалами для всех учеников",
    textKz:
      "Тесттер мен презентацияларды жылдам жасау, AI-генерация және барлық оқушылар үшін оқу материалдарымен ыңғайлы жұмыс",
    icon: assetPaths.illustrations.landingMainTeacher,
  },
  {
    labelRu: "Учреждение",
    labelKz: "Оқу орны",
    titleRu: "Система для учреждения",
    titleKz: "Оқу орнына арналған жүйе",
    textRu:
      "Единая среда для учеников, преподавателей, методистов и администраторов с прозрачным управлением процессами",
    textKz:
      "Оқушылар, оқытушылар, әдістемелік және әкімшілер үшін процестерді ашық басқарумен біртұтас орта",
    icon: assetPaths.illustrations.landingMainOrg,
  },
] as const;

const STATS = [
  {
    key: "users",
    iconSrc: assetPaths.icons.landingStatUsers,
    labelRu: "Пользователи",
    labelKz: "Пайдаланушылар",
    valueRu: "+300",
    valueKz: "+300",
    variant: "accent" as const,
  },
  {
    key: "price",
    iconSrc: assetPaths.icons.landingStatPrice,
    labelRu: "Всего от",
    labelKz: "барлығы",
    valueRu: "660 тг",
    valueKz: "660 тг",
    variant: "light" as const,
  },
  {
    key: "eff",
    iconSrc: assetPaths.icons.landingStatEfficiency,
    labelRu: "Эффективность",
    labelKz: "Тиімділік",
    valueRu: "80%",
    valueKz: "80%",
    variant: "light" as const,
  },
  {
    key: "tests",
    iconSrc: assetPaths.icons.landingStatTests,
    labelRu: "Пройдено тестов",
    labelKz: "Өтілген тесттер",
    valueRu: "+1200",
    valueKz: "+1200",
    variant: "light" as const,
  },
];

export default function LandingPageContent() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        {/* Hero */}
        <section className={styles.hero} aria-labelledby="landing-hero-title">
          <img alt="" className={styles.heroLogo} src={assetPaths.logo.svg} />
          <img
            id="landing-hero-title"
            alt="OKU"
            className={styles.heroWordmark}
            src={assetPaths.logo.textBlack}
          />
          <p className={styles.heroTagline}>
            {t(
              "Платформа для тестирования, анализа знаний и персонализированного обучения",
              "Білімді тексеру, талдау және жекелендірілген оқу платформасы",
            )}
          </p>
        </section>

        {/* Mission */}
        <RevealOnScroll>
        <section className={styles.section} aria-labelledby="mission-title">
          <div className={styles.missionCard}>
            <img className={styles.missionImage} src={assetPaths.illustrations.landingBooks} alt="" />
            <div className={styles.missionBody}>
              <h2 id="mission-title" className={styles.sectionHeading}>
                {t("Наша миссия", "Біздің миссиямыз")}
              </h2>
              <p className={styles.missionText}>
                {t(
                  "Сформировать у студентов и педагогов практическую AI-грамотность как ключевую компетенцию XXI века",
                  "Студенттер мен педагогтарда XXI ғасырдың негізгі құзыреті ретінде практикалық AI-сауаттылықты қалыптастыру",
                )}
              </p>
              <Link className={styles.missionButton} href="/about">
                {t("Подробнее", "Толығырақ")}
              </Link>
            </div>
          </div>
        </section>
        </RevealOnScroll>

        {/* What is OKU */}
        <RevealOnScroll>
        <section className={`${styles.section} ${styles.sectionWithTitle}`} aria-labelledby="what-title">
          <h2 id="what-title" className={styles.sectionHeadingCenter}>
            {t("Что такое OKU ?", "OKU деген не?")}
          </h2>
          <div className={styles.featureGrid}>
            {FEATURE_CARDS.map((card) => (
              <article key={card.titleRu} className={styles.featureCard}>
                <img className={styles.featureCardIcon} src={card.icon} alt="" />
                <span className={styles.featureLabel}>{t(card.labelRu, card.labelKz)}</span>
                <h3 className={styles.featureCardTitle}>{t(card.titleRu, card.titleKz)}</h3>
                <p className={styles.featureCardText}>{t(card.textRu, card.textKz)}</p>
              </article>
            ))}
          </div>
        </section>
        </RevealOnScroll>

        {/* Relevance */}
        <RevealOnScroll>
        <section className={`${styles.section} ${styles.sectionWithTitle}`} aria-labelledby="relevance-title">
          <h2 id="relevance-title" className={styles.sectionHeadingCenter}>
            {t("Это актуально", "Бұл өзекті")}
          </h2>
          <div className={styles.relevanceRow}>
            <div className={styles.relevanceText}>
              <p className={styles.relevanceLead}>
                {t(
                  "В условиях широкого доступа к AI привычные формы проверки знаний уже не всегда отражают реальный уровень подготовки",
                  "AI-ға кең қолжетімділік жағдайында дәстүрлі білім тексеру формалары дайындықтың нақты деңгейін әрқашан көрсете бермейді",
                )}
              </p>
              <p className={styles.relevanceHighlight}>
                {t(
                  "OKU предлагает современный подход к тестированию, который помогает с высокой вероятностью делать оценку знаний более достоверной",
                  "OKU білімді бағалауды сенімдірек етуге көмектесетін заманауи тестілеу тәсілін ұсынады",
                )}
              </p>
            </div>
            <div className={styles.statsGrid}>
              {STATS.map((row) => (
                <div
                  key={row.key}
                  className={row.variant === "accent" ? styles.statCardAccent : styles.statCard}
                >
                  <img className={styles.statIconImg} src={row.iconSrc} alt="" aria-hidden />
                  <div className={styles.statTextCol}>
                    <span className={styles.statLabel}>{t(row.labelRu, row.labelKz)}</span>
                    <span className={styles.statValue}>{t(row.valueRu, row.valueKz)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
        </RevealOnScroll>

        {/* FAQ */}
        <RevealOnScroll>
        <section className={`${styles.section} ${styles.sectionWithTitle}`} aria-labelledby="faq-title">
          <h2 id="faq-title" className={styles.sectionHeadingCenter}>
            {t("FAQ", "Сұрақ-жауап")}
          </h2>
          <FaqAccordion items={FAQ_ITEMS} t={t} />
        </section>
        </RevealOnScroll>

        <RevealOnScroll>
        <div className={styles.bottomCta}>
          <Link className={styles.ctaSolid} href={appPath("/register")}>
            {t("Начать в OKU", "OKU-да бастау")}
          </Link>
        </div>
        </RevealOnScroll>
      </main>
    </div>
  );
}
