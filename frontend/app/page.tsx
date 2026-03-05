"use client";

import Link from "next/link";

import { tr, useUiLanguage } from "@/lib/i18n";
import { assetPaths } from "@/src/assets";
import styles from "@/app/landing.module.css";

const MODE_ITEMS = [
  {
    title: "Стандартный",
    title_kz: "Стандартты",
    text: "Классический режим: чтение вопроса и ответы в текстовом формате.",
    text_kz: "Классикалық режим: сұрақты оқу және мәтін түрінде жауап беру.",
    icon: assetPaths.icons.text,
  },
  {
    title: "Аудио",
    title_kz: "Аудио",
    text: "Режим, где вы можете воспроизводить вопросы в аудио формате.",
    text_kz: "Сұрақтарды аудио форматта тыңдауға болатын режим.",
    icon: assetPaths.icons.headphones,
  },
  {
    title: "Устный",
    title_kz: "Ауызша",
    text: "Режим для устных ответов: вы говорите, а система оценивает ответ.",
    text_kz: "Ауызша жауап беру режимі: сіз сөйлейсіз, жүйе жауапты бағалайды.",
    icon: assetPaths.icons.microphone,
  },
];

const TEACHER_TAGS = [
  {
    ru: "Создавайте группы и приглашайте учеников",
    kz: "Топтар құрып, оқушыларды шақырыңыз",
  },
  {
    ru: "Детальная аналитика",
    kz: "Толық аналитика",
  },
  {
    ru: "Контролируйте класс по метрикам",
    kz: "Сыныпты метрикалар арқылы бақылаңыз",
  },
  {
    ru: "Создание материала",
    kz: "Материал жасау",
  },
];

export default function LandingPage() {
  const uiLanguage = useUiLanguage();
  const t = (ru: string, kz: string) => tr(uiLanguage, ru, kz);

  const modeItems = MODE_ITEMS.map((item) => ({
    ...item,
    title: t(item.title, item.title_kz),
    text: t(item.text, item.text_kz),
  }));
  const teacherTags = TEACHER_TAGS.map((item) => t(item.ru, item.kz));

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <section className={styles.hero}>
          <img alt="OKU" className={styles.heroLogo} src={assetPaths.logo.svg} />
          <h1 className={styles.heroBrand}>OKU</h1>
          <p className={styles.heroText}>
            {t(
              "Единая платформа превращающая тестирование в инструмент обучения",
              "Тестілеуді оқу құралына айналдыратын бірыңғай платформа",
            )}
          </p>
          <div className={styles.heroActions} data-nosnippet="true">
            <Link className={styles.ctaPrimary} href="/register">
              {t("Регистрация", "Тіркелу")}
            </Link>
            <Link className={styles.ctaPrimary} href="/login">
              {t("Войти", "Кіру")}
            </Link>
          </div>
        </section>

        <section className={styles.section}>
          <header className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>{t("Про проект", "Жоба туралы")}</h2>
            <p className={styles.sectionText}>{t("Поможет понять то, на что способен проект OKU", "OKU жобасының мүмкіндіктерін түсінуге көмектеседі")}</p>
          </header>

          <article className={styles.goalCard}>
            <img className={styles.goalImage} src={assetPaths.illustrations.landingBooks} alt="" aria-hidden="true" />
            <div className={styles.goalBody}>
              <h3 className={styles.displayTitle}>{t("ЦЕЛЬ", "МАҚСАТ")}</h3>
              <p className={styles.displayTextOnColor}>
                {t(
                  "Сформировать у студентов и педагогов практическую ИИ-грамотность как ключевую компетенцию XXI века",
                  "Студенттер мен педагогтарда XXI ғасырдың негізгі құзыреті ретінде практикалық ЖИ-сауаттылықты қалыптастыру",
                )}
              </p>
            </div>
          </article>
        </section>

        <section className={styles.section}>
          <header className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>{t("Режим прохождения", "Өту режимі")}</h2>
            <p className={styles.sectionText}>{t("Формат в которых возможно сдавать тесты", "Тест тапсыруға болатын форматтар")}</p>
          </header>

          <div className={styles.modesGrid}>
            {modeItems.map((item) => (
              <article className={styles.modeItem} key={item.title}>
                <img alt="" aria-hidden="true" className={styles.modeIcon} src={item.icon} />
                <h3 className={styles.modeTitle}>{item.title}</h3>
                <p className={styles.modeText}>{item.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.featureRow}>
            <div className={styles.featureTextBlock}>
              <h2 className={styles.displayTitleColor}>
                {t("Общеобразовательные", "Жалпы білім беру")}
                <br />
                {t("предметы", "пәндері")}
              </h2>
              <p className={styles.featureText}>
                {t(
                  "Мы собрали материалы как для средней, так и для старшей школы. Для каждого предмета доступны разные конфигурации и форматы прохождения, которые можно подстроить под цель. При этом сами тесты и задания формируются с опорой на общепринятую систему школьного образования.",
                  "Біз орта және жоғары мектепке арналған материалдарды жинадық. Әр пән бойынша мақсатқа сай бейімделетін әртүрлі конфигурация мен өту форматтары бар. Тесттер мен тапсырмалар мектептегі стандартты білім беру жүйесіне сүйеніп құрастырылады.",
                )}
              </p>
            </div>
            <img className={styles.featureImage} src={assetPaths.illustrations.landingSubjects} alt="" aria-hidden="true" />
          </div>
        </section>

        <section className={styles.section}>
          <div className={`${styles.featureRow} ${styles.featureRowReverse}`}>
            <img className={styles.featureImage} src={assetPaths.illustrations.landingPrep} alt="" aria-hidden="true" />
            <div className={styles.featureTextBlock}>
              <h2 className={styles.displayTitleColor}>{t("Подготовка к важному", "Маңыздыға дайындық")}</h2>
              <p className={styles.featureText}>
                {t(
                  "ЕНТ и IELTS — на разных уровнях подготовки, от базового до продвинутого. Задания и тесты формируются по логике официальных требований и структуры экзаменов, поэтому тренировка максимально приближена к реальному формату.",
                  "ЕНТ және IELTS — базалық деңгейден жоғары деңгейге дейінгі дайындық. Тапсырмалар мен тесттер ресми талаптар мен емтихан құрылымына сай құралады, сондықтан дайындық нақты форматқа барынша жақын.",
                )}
              </p>
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <article className={styles.teacherCard}>
            <div className={styles.teacherBody}>
              <h2 className={styles.teacherTitle}>{t("Роль преподавателя", "Мұғалім рөлі")}</h2>
              <div className={styles.teacherTags}>
                {teacherTags.map((tag) => (
                  <span className={styles.teacherTag} key={tag}>
                    {tag}
                  </span>
                ))}
              </div>
            </div>
            <img className={styles.teacherImage} src={assetPaths.illustrations.landingTeacher} alt="" aria-hidden="true" />
          </article>
        </section>
      </main>

      <footer className={styles.footer} data-nosnippet="true">OKU.com.kz</footer>
    </div>
  );
}
