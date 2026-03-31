"use client";

import Link from "next/link";

import { appPath } from "@/src/config/domains";
import { assetPaths } from "@/src/assets";
import { tr, useUiLanguage } from "@/lib/i18n";
import {
  STUDENTS_SUBJECTS_MOBILE_ROW_1,
  STUDENTS_SUBJECTS_MOBILE_ROW_2,
  STUDENTS_SUBJECTS_MOBILE_ROW_3,
  STUDENTS_SUBJECTS_ROW_1,
  STUDENTS_SUBJECTS_ROW_2,
} from "@/lib/constants/studentsPage";

import StudentSchoolLevelCard from "./StudentSchoolLevelCard";
import RevealOnScroll from "./RevealOnScroll";
import styles from "./studentsPage.module.css";

export default function StudentsPageContent() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const row1Marquee = (suffix: string) =>
    STUDENTS_SUBJECTS_ROW_1.map((s) => (
      <img
        key={`${s.id}-${suffix}`}
        className={styles.subjectMarqueeImg}
        src={s.illustrationSrc}
        alt={t(s.titleRu, s.titleKz)}
      />
    ));

  const row2Marquee = (suffix: string) =>
    STUDENTS_SUBJECTS_ROW_2.map((s) => (
      <img
        key={`${s.id}-${suffix}`}
        className={styles.subjectMarqueeImg}
        src={s.illustrationSrc}
        alt={t(s.titleRu, s.titleKz)}
      />
    ));

  const mobileRowMarquee =
    (items: typeof STUDENTS_SUBJECTS_MOBILE_ROW_1) => (suffix: string) =>
      items.map((s) => (
        <img
          key={`${s.id}-${suffix}`}
          className={styles.subjectMarqueeImg}
          src={s.illustrationSrc}
          alt={t(s.titleRu, s.titleKz)}
        />
      ));

  const mobileRow1 = mobileRowMarquee(STUDENTS_SUBJECTS_MOBILE_ROW_1);
  const mobileRow2 = mobileRowMarquee(STUDENTS_SUBJECTS_MOBILE_ROW_2);
  const mobileRow3 = mobileRowMarquee(STUDENTS_SUBJECTS_MOBILE_ROW_3);

  return (
    <div className={styles.page}>
      <section className={styles.hero} aria-labelledby="students-hero-title">
        <div>
          <h1 id="students-hero-title" className={styles.heroTitle}>
            {t("Ученику", "Оқушыға")}
          </h1>
          <p className={styles.heroSubtitle}>{t("Более 10 направлений", "10-нан астам бағыт")}</p>
        </div>

        <div className={styles.scrollBand}>
          <div className={styles.scrollFadeLeft} aria-hidden />
          <div className={styles.scrollFadeRight} aria-hidden />
          <div className={styles.marqueeStack}>
            <div className={styles.marqueeRow}>
              <div className={styles.marqueeViewport}>
                <div className={`${styles.marqueeTrack} ${styles.marqueeTrackLeft}`}>
                  <div className={styles.marqueeGroup}>{row1Marquee("a")}</div>
                  <div className={styles.marqueeGroup} aria-hidden="true">
                    {row1Marquee("b")}
                  </div>
                </div>
              </div>
            </div>
            <div className={styles.marqueeRow}>
              <div className={styles.marqueeViewport}>
                <div className={`${styles.marqueeTrack} ${styles.marqueeTrackRight}`}>
                  <div className={styles.marqueeGroup}>{row2Marquee("a")}</div>
                  <div className={styles.marqueeGroup} aria-hidden="true">
                    {row2Marquee("b")}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className={styles.marqueeStackMobile}>
            <div className={styles.marqueeRow}>
              <div className={styles.marqueeViewport}>
                <div className={`${styles.marqueeTrack} ${styles.marqueeTrackLeft}`}>
                  <div className={styles.marqueeGroup}>{mobileRow1("a")}</div>
                  <div className={styles.marqueeGroup} aria-hidden="true">
                    {mobileRow1("b")}
                  </div>
                </div>
              </div>
            </div>
            <div className={styles.marqueeRow}>
              <div className={styles.marqueeViewport}>
                <div className={`${styles.marqueeTrack} ${styles.marqueeTrackRight}`}>
                  <div className={styles.marqueeGroup}>{mobileRow2("a")}</div>
                  <div className={styles.marqueeGroup} aria-hidden="true">
                    {mobileRow2("b")}
                  </div>
                </div>
              </div>
            </div>
            <div className={styles.marqueeRow}>
              <div className={styles.marqueeViewport}>
                <div className={`${styles.marqueeTrack} ${styles.marqueeTrackLeft}`}>
                  <div className={styles.marqueeGroup}>{mobileRow3("a")}</div>
                  <div className={styles.marqueeGroup} aria-hidden="true">
                    {mobileRow3("b")}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <RevealOnScroll>
      <section className={styles.section} aria-labelledby="students-testing-title">
        <div className={styles.sectionInner}>
          <h2 id="students-testing-title" className={styles.sectionTitle}>
            {t("Современное тестирование", "Қазіргі заманғы тестілеу")}
          </h2>

          <div className={`${styles.block} ${styles.blockSubjects}`}>
            <div className={styles.blockText}>
              <div>
                <h3 className={styles.blockHeading}>
                  {t("Общеобразовательные предметы", "Жалпы білім беретін пәндер")}
                </h3>
                <p className={styles.blockBody}>
                  {t(
                    "Для каждого предмета доступны разные конфигурации и форматы прохождения. При этом сами тесты и задания формируются с опорой на общепринятую систему школьного образования.",
                    "Әр пән үшін әртүрлі конфигурациялар мен өту форматтары қолжетімді. Сонымен қатар тесттер мен тапсырмалар жалпы қабылданған мектеп білім беру жүйесіне сүйене отырып қалыптасады.",
                  )}
                </p>
              </div>
              <div className={`${styles.levelRow} ${styles.levelRowSchoolLevels}`}>
                <StudentSchoolLevelCard
                  iconVariant="embed56"
                  iconSrc={assetPaths.icons.middleSchool}
                  title={t("Средняя школа", "Орта мектеп")}
                  subtitle={t("Материал 6–8 класса", "6–8 сынып материалы")}
                />
                <StudentSchoolLevelCard
                  iconVariant="embed56"
                  iconSrc={assetPaths.icons.highSchool}
                  title={t("Старшая школа", "Жоғары сынып")}
                  subtitle={t("Материал 9–11 класса", "9–11 сынып материалы")}
                />
              </div>
            </div>
            <div className={styles.illustration}>
              <img src={assetPaths.illustrations.studentGeneralSubjects} alt="" />
            </div>
          </div>

          <div className={styles.block}>
            <div className={styles.illustration}>
              <img src={assetPaths.illustrations.landingModernTest} alt="" />
            </div>
            <div className={styles.blockText}>
              <div>
                <h3 className={`${styles.blockHeading} ${styles.blockHeadingSemibold}`}>
                  {t("Подготовка к важному", "Маңызды дайындық")}
                </h3>
                <p className={styles.blockBody}>
                  {t(
                    "ЕНТ и IELTS — на разных уровнях подготовки, от базового до продвинутого. Задания и тесты формируются по логике официальных требований и структуры этих экзаменов, поэтому тренировка максимально приближена к реальному формату.",
                    "ҰБТ және IELTS — базалықтан деңгейліге дейінгі әртүрлі дайындық деңгейлерінде. Тапсырмалар мен тесттер ресми талаптар мен емтихан құрылымы логикасы бойынша қалыптасады, сондықтан жаттығу нақты форматқа мүмкіндігінше жақын.",
                  )}
                </p>
              </div>
              <div className={`${styles.levelRow} ${styles.levelRowEnt}`}>
                <StudentSchoolLevelCard
                  iconVariant="whiteBox56"
                  iconSrc={assetPaths.icons.ent}
                  title={t("ЕНТ и IELTS", "ҰБТ және IELTS")}
                  subtitle={t("Подготовительный материал", "Дайындық материалы")}
                />
              </div>
            </div>
          </div>
        </div>
      </section>
      </RevealOnScroll>

      <RevealOnScroll>
      <section className={styles.personalSection} aria-labelledby="students-personal-title">
        <h2 id="students-personal-title" className={styles.personalHeading}>
          {t("Персонализированное обучение", "Жекелендірілген оқу")}
        </h2>
        <div className={styles.personalRow}>
          <div className={styles.personalCopy}>
            <p className={styles.personalLabel}>{t("Для тебя", "Сен үшін")}</p>
            <p className={styles.personalLead}>
              {t(
                "OKU помогает выстраивать более индивидуальный подход к обучению. Платформа анализирует результаты тестирования, выявляет слабые темы и показывает, на что стоит обратить внимание в первую очередь. Это помогает лучше понимать свои знания и двигаться в обучении более осознанно.",
                "OKU оқуға жекерек тәсіл құруға көмектеседі. Платформа тестілеу нәтижелерін талдайды, әлсіз тақырыптарды анықтайды және алдымен нелерге назар аудару керектігін көрсетеді. Бұл біліміңді жақсырақ түсінуге және оқуды саналырақ жалғастыруға көмектеседі.",
              )}
            </p>
            <Link className={styles.cta} href={appPath("/register")}>
              {t("Попробовать бесплатно", "Тегін сынап көру")}
            </Link>
          </div>
          <div className={styles.sphereWrap} aria-hidden>
            <img className={styles.sphereImg} src={assetPaths.illustrations.studentSphere} alt="" />
          </div>
        </div>
      </section>
      </RevealOnScroll>
    </div>
  );
}
