import styles from "./studentsPage.module.css";

export type SchoolLevelIconVariant = "onAccent" | "embed56" | "whiteBox56";

interface Props {
  iconSrc: string;
  title: string;
  subtitle: string;
  /** embed56 — готовые 56×56 (middle_school / high_school); whiteBox56 — иконка на белой подложке (ЕНТ) */
  iconVariant?: SchoolLevelIconVariant;
}

export default function StudentSchoolLevelCard({
  iconSrc,
  title,
  subtitle,
  iconVariant = "onAccent",
}: Props) {
  return (
    <div className={styles.levelCard}>
      {iconVariant === "embed56" ? (
        <img className={styles.levelIconEmbedded} src={iconSrc} alt="" aria-hidden />
      ) : iconVariant === "whiteBox56" ? (
        <div className={styles.levelIconWhiteBox}>
          <img className={styles.levelIconWhiteBoxImg} src={iconSrc} alt="" aria-hidden />
        </div>
      ) : (
        <img className={styles.levelIcon} src={iconSrc} alt="" aria-hidden />
      )}
      <div className={styles.levelText}>
        <p className={styles.levelTitle}>{title}</p>
        <p className={styles.levelSubtitle}>{subtitle}</p>
      </div>
    </div>
  );
}
