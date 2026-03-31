"use client";

import { useState } from "react";

import { assetPaths } from "@/src/assets";
import { tr, useUiLanguage } from "@/lib/i18n";

import RevealOnScroll from "./RevealOnScroll";
import styles from "./teachersPage.module.css";

type TabId = "manual" | "ai" | "file";

const TABS: { id: TabId; labelRu: string; labelKz: string }[] = [
  { id: "manual", labelRu: "Создать вручную", labelKz: "Қолмен құру" },
  { id: "ai", labelRu: "Создать с AI", labelKz: "AI арқылы құру" },
  { id: "file", labelRu: "Создать из файла", labelKz: "Файлдан құру" },
];

function TabSwitcher({
  active,
  onChange,
  t,
}: {
  active: TabId;
  onChange: (t: TabId) => void;
  t: (ru: string, kz: string) => string;
}) {
  const ind =
    active === "manual" ? styles.tabIndicatorManual : active === "ai" ? styles.tabIndicatorAi : styles.tabIndicatorFile;

  return (
    <div className={styles.tabSwitcherWrap}>
      <div className={styles.tabSwitcher}>
        <div className={`${styles.tabIndicator} ${ind}`} aria-hidden />
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`${styles.tabBtn} ${active === tab.id ? styles.tabBtnActive : styles.tabBtnInactive}`}
            onClick={() => onChange(tab.id)}
          >
            {t(tab.labelRu, tab.labelKz)}
          </button>
        ))}
      </div>
    </div>
  );
}

function TeachersModePanel({
  t,
  imageSrc,
  leadRu,
  leadKz,
  featureIconSrc,
  featureTitleRu,
  featureTitleKz,
  featureSubRu,
  featureSubKz,
}: {
  t: (ru: string, kz: string) => string;
  imageSrc: string;
  leadRu: string;
  leadKz: string;
  featureIconSrc: string;
  featureTitleRu: string;
  featureTitleKz: string;
  featureSubRu: string;
  featureSubKz: string;
}) {
  return (
    <div className={styles.twoCol}>
      <div className={styles.leftCol}>
        <p className={styles.lead}>{t(leadRu, leadKz)}</p>
        <div className={styles.featureCard}>
          <img className={styles.featureIconImg} src={featureIconSrc} alt="" />
          <p className={styles.featureTitle}>{t(featureTitleRu, featureTitleKz)}</p>
          <p className={styles.featureSub}>{t(featureSubRu, featureSubKz)}</p>
        </div>
      </div>
      <div className={`${styles.rightCol} ${styles.rightColBleed}`}>
        <div className={styles.modeImageWrap}>
          <img className={styles.modeImage} src={imageSrc} alt="" />
        </div>
      </div>
    </div>
  );
}

const WARNINGS_COL1_RU = ["Выход из вкладки", "Открытие консоли", "Стороннее приложение", "Вставка текста"];
const WARNINGS_COL1_KZ = ["Қойыннан шығу", "Консольді ашу", "Сыртқы қолданба", "Мәтінді қою"];
const WARNINGS_COL2_RU = ["Переключение окна", "Разделение экрана", "Паттерны", "Перезагрузка"];
const WARNINGS_COL2_KZ = ["Терезені ауыстыру", "Экранды бөлу", "Үлгілер", "Қайта жүктеу"];

export default function TeachersPageContent() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);
  const [activeTab, setActiveTab] = useState<TabId>("manual");

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <h1 className={styles.heroTitle}>{t("Педагогу", "Педагогқа")}</h1>
        <p className={styles.heroSubtitle}>{t("Удобство и эффективность", "Ыңғайлылық және тиімділік")}</p>
        <TabSwitcher active={activeTab} onChange={setActiveTab} t={t} />
        <div className={styles.heroPanel}>
          {/* Без `key` контейнер не размонтируется при смене вкладки. Это убирает краткие "провалы" высоты и визуальные дерганья. */}
          <div className={styles.tabPanelRoot}>
            {activeTab === "manual" && (
              <TeachersModePanel
                t={t}
                imageSrc={assetPaths.images.teachersModeManual}
                featureIconSrc={assetPaths.icons.landingStatEfficiency}
                leadRu="Соберите тест самостоятельно, вручную добавляя вопросы, изображения, варианты ответов и правильные ответы"
                leadKz="Сұрақтарды, суреттерді, жауап нұсқаларын және дұрыс жауаптарды қолмен қоса отырып, тестті өзіңіз жинаңыз"
                featureTitleRu="Автоматическое выявление сложности составленного теста"
                featureTitleKz="Құралған тесттің қиындығын автоматты анықтау"
                featureSubRu="Лёгкий, средний или сложный"
                featureSubKz="Жеңіл, орта немесе қиын"
              />
            )}
            {activeTab === "ai" && (
              <TeachersModePanel
                t={t}
                imageSrc={assetPaths.images.teachersModeAi}
                featureIconSrc={assetPaths.icons.aiGenerate}
                leadRu="Сгенерируйте тест автоматически с помощью AI по выбранной теме и нужным параметрам"
                leadKz="Таңдалған тақырып және қажетті параметрлер бойынша AI көмегімен тестті автоматты түрде генерациялаңыз"
                featureTitleRu="Генерация теста по любой выбранной теме"
                featureTitleKz="Кез келген таңдалған тақырып бойынша тест генерациясы"
                featureSubRu="от точных наук до философии"
                featureSubKz="дәл ғылымдардан философияға дейін"
              />
            )}
            {activeTab === "file" && (
              <TeachersModePanel
                t={t}
                imageSrc={assetPaths.images.teachersModeFile}
                featureIconSrc={assetPaths.icons.testCreated}
                leadRu="Загрузите документ или шаблонный файл, чтобы быстро сформировать тест на его основе"
                leadKz="Тестті оның негізінде жылдам қалыптастыру үшін құжатты немесе үлгі файлды жүктеңіз"
                featureTitleRu="Перенести тесты с других платформ — не проблема"
                featureTitleKz="Басқа платформалардан тесттерді көшіру — мәселе емес"
                featureSubRu=".docx · .csv"
                featureSubKz=".docx · .csv"
              />
            )}
          </div>
        </div>
      </section>

      <RevealOnScroll>
        <section className={styles.reliability}>
          <h2 className={styles.relTitle}>{t("Достоверность", "Сенімділік")}</h2>
          <div className={styles.relInner}>
            <div className={styles.relCopy}>
              <div className={styles.relBlockHead}>
                <div className={styles.relHeadingRow}>
                  <img className={styles.relDiamond} src={assetPaths.icons.warningDiamond} alt="" />
                  <h3 className={styles.relHeading}>{t("Система предупреждений", "Ескерту жүйесі")}</h3>
                </div>
                <p className={styles.relBody}>
                  {t(
                    "OKU помогает преподавателю с высокой вероятностью получать более достоверную картину знаний ученика. Платформа использует систему предупреждений и фиксирует подозрительные действия во время прохождения теста, чтобы преподаватель видел не только итоговый балл, но и возможные сигналы риска.",
                    "OKU оқытушыға оқушының білімінің сенімдірек суретін алуға көмектеседі. Платформа ескерту жүйесін қолданады және тест өту кезінде күдікті әрекеттерді тіркейді — оқытушы тек қорытынды баллды ғана емес, тәуекел сигналдарын да көре алады.",
                  )}
                </p>
              </div>
              <div>
                <p className={styles.warnTitle}>{t("За что мы даем предупреждения:", "Ескертулерді неліктен береміз:")}</p>
                <div className={styles.warnCols}>
                  <div className={styles.warnCol}>
                    {WARNINGS_COL1_RU.map((ru, i) => (
                      <div key={ru} className={styles.warnRow}>
                        <img className={styles.warnCheckImg} src={assetPaths.icons.checkFill} alt="" />
                        <span className={styles.warnText}>{t(ru, WARNINGS_COL1_KZ[i] ?? ru)}</span>
                      </div>
                    ))}
                  </div>
                  <div className={styles.warnCol}>
                    {WARNINGS_COL2_RU.map((ru, i) => (
                      <div key={ru} className={styles.warnRow}>
                        <img className={styles.warnCheckImg} src={assetPaths.icons.checkFill} alt="" />
                        <span className={styles.warnText}>{t(ru, WARNINGS_COL2_KZ[i] ?? ru)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            <div className={styles.relIllustration}>
              <img src={assetPaths.illustrations.landingMainTeacher} alt="" />
            </div>
          </div>
        </section>
      </RevealOnScroll>
    </div>
  );
}
