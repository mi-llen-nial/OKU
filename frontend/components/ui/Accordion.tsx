import styles from "@/components/ui/Accordion.module.css";

export interface AccordionItem {
  id: string;
  title: string;
  subtitle?: string;
  content: React.ReactNode;
}

interface AccordionProps {
  items: AccordionItem[];
}

export default function Accordion({ items }: AccordionProps) {
  return (
    <div className={styles.root}>
      {items.map((item) => (
        <details className={styles.item} key={item.id}>
          <summary className={styles.summary}>
            <span>{item.title}</span>
            {item.subtitle && <span>{item.subtitle}</span>}
          </summary>
          <div className={styles.body}>{item.content}</div>
        </details>
      ))}
    </div>
  );
}
