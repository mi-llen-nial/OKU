import styles from "@/components/SimpleBarChart.module.css";

interface Point {
  label: string;
  value: number;
}

export default function SimpleBarChart({ points }: { points: Point[] }) {
  if (points.length === 0) {
    return <div className={styles.empty}>Недостаточно данных для графика.</div>;
  }

  return (
    <div className={styles.chart}>
      {points.map((point) => (
        <div className={styles.row} key={`${point.label}-${point.value}`}>
          <span className={styles.label}>{point.label}</span>
          <div className={styles.track}>
            <div className={styles.fill} style={{ width: `${Math.min(point.value, 100)}%` }} />
          </div>
          <span className={styles.value}>{point.value.toFixed(1)}%</span>
        </div>
      ))}
    </div>
  );
}
