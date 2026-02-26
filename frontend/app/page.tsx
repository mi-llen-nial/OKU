import Link from "next/link";

import { assetPaths } from "@/src/assets";
import styles from "@/app/landing.module.css";

const MODE_ITEMS = [
  {
    title: "Стандартный",
    text: "Классический режим: чтение вопроса и ответы в текстовом формате.",
    icon: assetPaths.icons.text,
  },
  {
    title: "Аудио",
    text: "Режим, где вы можете воспроизводить вопросы в аудио формате.",
    icon: assetPaths.icons.headphones,
  },
  {
    title: "Устный",
    text: "Режим для устных ответов: вы говорите, а система оценивает ответ.",
    icon: assetPaths.icons.microphone,
  },
];

const SUBJECT_ITEMS = [
  {
    title: "Математика",
    text: "Математика для средних классов",
    icon: assetPaths.icons.math,
  },
  {
    title: "Алгебра",
    text: "Математика для старших классов",
    icon: assetPaths.icons.algebra,
  },
  {
    title: "Геометрия",
    text: "Материал для старших классов",
    icon: assetPaths.icons.geometry,
  },
];

export default function LandingPage() {
  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <section className={styles.hero}>
          <img alt="OKU" className={styles.heroLogo} src={assetPaths.logo.svg} />
          <h1 className={styles.heroTitle}>OKU</h1>
          <p className={styles.heroSubtitle}>Единая платформа превращающая тестирование в инструмент обучения</p>
          <div className={styles.heroActions}>
            <Link className={styles.ctaPrimary} href="/register">
              Зарегистрироваться
            </Link>
            <Link className={styles.ctaPrimary} href="/login">
              Войти
            </Link>
          </div>
        </section>

        <section className={styles.section}>
          <header className={styles.sectionHeaderCentered}>
            <h2 className={styles.projectTitle}>Про проект</h2>
            <p className={styles.projectSubtitle}>Поможет понять то, на что способен проект OKU</p>
          </header>

          <div className={styles.goalRow}>
            <article className={styles.goalBlock}>
              <h3 className={styles.goalTitle}>ЦЕЛЬ</h3>
              <p className={styles.goalText}>
                Сформировать у студентов и педагогов практическую ИИ-грамотность как ключевую компетенцию XXI века
              </p>
            </article>

            <article className={styles.qrBlock}>
              <img alt="QR OKU bot" className={styles.qrImage} src={assetPaths.images.qrOku} />
              <a className={styles.qrButton} href="https://t.me/KOMA_OKU_bot" rel="noreferrer" target="_blank">
                Перейти в OKU
              </a>
            </article>
          </div>
        </section>

        <section className={styles.section}>
          <header className={styles.sectionHeaderCentered}>
            <h2 className={styles.sectionTitle}>Режим прохождения</h2>
            <p className={styles.sectionSubtitle}>Формат в которых возможно сдавать тесты</p>
          </header>

          <div className={styles.modeGrid}>
            {MODE_ITEMS.map((item) => (
              <article className={styles.modeItem} key={item.title}>
                <img alt={item.title} className={styles.modeIcon} src={item.icon} />
                <div className={styles.modeBody}>
                  <h3 className={styles.modeTitle}>{item.title}</h3>
                  <p className={styles.modeText}>{item.text}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <header className={styles.sectionHeaderCentered}>
            <h2 className={styles.sectionTitle}>Общеобразовательные предметы</h2>
            <p className={styles.sectionSubtitle}>Сначала определите предмет, затем настройте параметры теста.</p>
          </header>

          <div className={styles.subjectGrid}>
            {SUBJECT_ITEMS.map((item) => (
              <article className={styles.subjectItem} key={item.title}>
                <img alt={item.title} className={styles.subjectIcon} src={item.icon} />
                <div>
                  <h3 className={styles.subjectTitle}>{item.title}</h3>
                  <p className={styles.subjectText}>{item.text}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <header className={styles.sectionHeaderCentered}>
            <h2 className={styles.sectionTitle}>Подготовка к важному</h2>
            <p className={styles.sectionSubtitle}>Подготовка под самые популярные направления</p>
          </header>

          <div className={styles.examGrid}>
            <article className={styles.examItem}>
              <img alt="ЕНТ" className={styles.examIcon} src={assetPaths.icons.ent} />
              <div>
                <h3 className={styles.examTitle}>ЕНТ</h3>
                <p className={styles.examText}>Единое национальное тестирование</p>
              </div>
            </article>

            <article className={styles.examItem}>
              <img alt="IELTS" className={styles.examIcon} src={assetPaths.icons.ielts} />
              <div>
                <h3 className={styles.examTitle}>IELTS</h3>
                <p className={styles.examText}>Международная система тестирования по английскому языку</p>
              </div>
            </article>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.goalRow}>
            <article className={styles.goalBlock}>
              <h3 className={styles.goalTitle}>FAQ</h3>
              <p className={styles.goalText}>
                Получите ответ на все интересующие вас вопросы по проекте и более, мы будем рады на них ответить 24/7
              </p>
            </article>

            <article className={styles.qrBlock}>
              <img alt="QR FAQ bot" className={styles.qrImage} src={assetPaths.images.qrFaq} />
              <a className={styles.qrButton} href="https://t.me/KOMA_FAQ_bot" rel="noreferrer" target="_blank">
                Перейти в FAQ
              </a>
            </article>
          </div>
        </section>
      </main>

      <footer className={styles.footer}>OKU.com</footer>
    </div>
  );
}
