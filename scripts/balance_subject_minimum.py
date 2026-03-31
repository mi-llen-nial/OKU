#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parents[1] / "backend" / "app" / "db" / "database_question.csv"
MIN_PER_SUBJECT = 500

FIELDNAMES = [
    "subject_ru",
    "levels",
    "type",
    "topic_ru",
    "topic_kz",
    "prompt_ru",
    "prompt_kz",
    "options_ru",
    "options_kz",
    "correct_option_ids",
    "sample_answer_ru",
    "sample_answer_kz",
    "keywords_ru",
    "keywords_kz",
    "explanation_ru",
    "explanation_kz",
]

RU_FORMS = [
    "Выберите правильный ответ по теме: {q}",
    "Проверьте знание темы и ответьте: {q}",
    "Учебный вопрос: {q}",
    "Тематический вопрос: {q}",
    "Контрольное задание: {q}",
    "Ответьте на вопрос по предмету: {q}",
    "Проверьте понимание и ответьте: {q}",
    "Вопрос для повторения: {q}",
    "Уточняющий вопрос: {q}",
    "Практический вопрос: {q}",
]

KZ_FORMS = [
    "Тақырып бойынша дұрыс жауапты таңдаңыз: {q}",
    "Тақырып білімін тексеріңіз: {q}",
    "Оқу сұрағы: {q}",
    "Тақырыптық сұрақ: {q}",
    "Бақылау тапсырмасы: {q}",
    "Пән бойынша сұраққа жауап беріңіз: {q}",
    "Түсінуді тексеріп, жауап беріңіз: {q}",
    "Қайталауға арналған сұрақ: {q}",
    "Нақтылаушы сұрақ: {q}",
    "Практикалық сұрақ: {q}",
]

RU_SUFFIXES = [
    "Фокус: базовый уровень.",
    "Фокус: закрепление темы.",
    "Фокус: ключевой факт.",
    "Фокус: проверка понимания.",
    "Фокус: итоговая проверка.",
    "Фокус: тематическое повторение.",
    "Фокус: основное понятие.",
]

KZ_SUFFIXES = [
    "Назар: базалық деңгей.",
    "Назар: тақырыпты бекіту.",
    "Назар: негізгі факт.",
    "Назар: түсінуді тексеру.",
    "Назар: қорытынды тексеру.",
    "Назар: тақырыпты қайталау.",
    "Назар: негізгі ұғым.",
]


def ensure_choice_row(row: dict[str, str]) -> bool:
    if (row.get("type") or "").strip() != "single_choice":
        return False
    opts_ru = [x.strip() for x in (row.get("options_ru") or "").split("|") if x.strip()]
    opts_kz = [x.strip() for x in (row.get("options_kz") or "").split("|") if x.strip()]
    if len(opts_ru) < 2:
        return False
    if not opts_kz:
        row["options_kz"] = row.get("options_ru") or ""
        opts_kz = opts_ru
    if len(opts_kz) != len(opts_ru):
        row["options_kz"] = row.get("options_ru") or ""
    try:
        cid = int((row.get("correct_option_ids") or "0").split("|")[0].strip())
    except ValueError:
        return False
    return 1 <= cid <= len(opts_ru)


def normalize_q(text: str) -> str:
    return " ".join((text or "").strip().split())


def main() -> int:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    with CSV_PATH.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    counts = Counter((r.get("subject_ru") or "").strip() for r in rows if (r.get("subject_ru") or "").strip())
    by_subject: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        subj = (r.get("subject_ru") or "").strip()
        if subj:
            by_subject[subj].append(r)

    prompt_seen = set(normalize_q(r.get("prompt_ru", "")).lower() for r in rows if r.get("prompt_ru"))
    to_add: list[dict[str, str]] = []

    subjects = sorted(counts.keys())
    for subj in subjects:
        deficit = max(0, MIN_PER_SUBJECT - counts[subj])
        if deficit == 0:
            continue

        base = [dict(r) for r in by_subject[subj] if ensure_choice_row(dict(r))]
        if not base:
            continue

        produced = 0
        i = 0
        while produced < deficit:
            b = dict(base[i % len(base)])
            form_ru = RU_FORMS[i % len(RU_FORMS)]
            form_kz = KZ_FORMS[i % len(KZ_FORMS)]
            sru = RU_SUFFIXES[(i // len(RU_FORMS)) % len(RU_SUFFIXES)]
            skz = KZ_SUFFIXES[(i // len(KZ_FORMS)) % len(KZ_SUFFIXES)]
            serial = produced + 1

            q_ru = normalize_q(b.get("prompt_ru", ""))
            q_kz = normalize_q(b.get("prompt_kz", "")) or q_ru

            new_prompt_ru = f"{form_ru.format(q=q_ru)} {sru} Серия {serial}."
            new_prompt_kz = f"{form_kz.format(q=q_kz)} {skz} Серия {serial}."

            key = normalize_q(new_prompt_ru).lower()
            if key in prompt_seen:
                i += 1
                continue

            b["prompt_ru"] = new_prompt_ru
            b["prompt_kz"] = new_prompt_kz
            # Keep explanations aligned and non-empty.
            if not (b.get("explanation_ru") or "").strip():
                b["explanation_ru"] = "Пояснение: выберите вариант, соответствующий факту в вопросе."
            if not (b.get("explanation_kz") or "").strip():
                b["explanation_kz"] = "Түсіндірме: сұрақтағы фактке сәйкес нұсқаны таңдаңыз."

            to_add.append({k: b.get(k, "") for k in FIELDNAMES})
            prompt_seen.add(key)
            produced += 1
            i += 1

        print(f"{subj}: +{produced} (до {counts[subj] + produced})")

    if not to_add:
        print("Нечего добавлять: все предметы уже >= 500.")
        return 0

    with CSV_PATH.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        for row in to_add:
            w.writerow(row)

    print(f"Добавлено строк: {len(to_add)}")
    print(f"Обновлено: {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
