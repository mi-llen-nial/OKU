import styles from "@/components/ui/ProgressBar.module.css";

interface ProgressBarProps {
  value: number;
}

export default function ProgressBar({ value }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className={styles.track} role="progressbar" aria-valuemax={100} aria-valuemin={0} aria-valuenow={clamped}>
      <div className={styles.fill} style={{ width: `${clamped}%` }} />
    </div>
  );
}
