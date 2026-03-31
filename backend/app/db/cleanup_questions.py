#!/usr/bin/env python3
"""
Глубокая очистка базы тестовых вопросов:
- удаление смысловых дублей и псевдо-разнообразия
- удаление машинной штамповки и слабых формулировок
- валидация типов single/multi/short_text
- ограничение однотипных шаблонов
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict

INPUT_CSV = OUTPUT_CSV = "database_question.csv"

VARIANT_PATTERN = re.compile(r"\s*\(вариант\s+\d+\)\s*$", re.I)
SERIES_PATTERN = re.compile(r"\bсерия\s*\d+\b", re.I)
YEAR_QUESTION_PATTERN = re.compile(r"(в\s+каком\s+году|қай\s+жылы)", re.I)
ONLY_DIGITS_PATTERN = re.compile(r"^\d{1,4}$")

# Шаблонные/искусственные фразы, удаляем из prompt
NOISE_PHRASES_RU = [
    r"Почему правильный ответ именно такой\.?",
    r"Кратко объясните почему этот ответ верный\.?",
    r"Кратко объясните логику выбора ответа\.?",
    r"Выберите правильный ответ по теме:\s*",
    r"Проверьте знание темы и ответьте:\s*",
    r"Учебный вопрос:\s*",
    r"Тематический вопрос:\s*",
    r"Контрольное задание:\s*",
    r"Ответьте на вопрос по предмету:\s*",
    r"Проверьте понимание и ответьте:\s*",
    r"Вопрос для повторения:\s*",
    r"Уточняющий вопрос:\s*",
    r"Практический вопрос:\s*",
    r"Фокус:\s*[^.]+\.",
]

NOISE_PHRASES_KZ = [
    r"Неге дұрыс жауап дәл осындай\.?",
    r"Неліктен бұл жауап дұрыс екенін қысқаша түсіндіріңіз\.?",
    r"Жауапты таңдаудың логикасын қысқаша түсіндіріңіз\.?",
    r"Тақырып бойынша дұрыс жауапты таңдаңыз:\s*",
    r"Тақырып білімін тексеріңіз:\s*",
    r"Оқу сұрағы:\s*",
    r"Тақырыптық сұрақ:\s*",
    r"Бақылау тапсырмасы:\s*",
    r"Пән бойынша сұраққа жауап беріңіз:\s*",
    r"Түсінуді тексеріп, жауап беріңіз:\s*",
    r"Қайталауға арналған сұрақ:\s*",
    r"Нақтылаушы сұрақ:\s*",
    r"Практикалық сұрақ:\s*",
    r"Назар:\s*[^.]+\.",
]

LEADING_PREFIXES = (
    "укажите верный ответ: ",
    "найдите правильный ответ: ",
    "выберите верный ответ: ",
    "выберите правильный ответ: ",
    "дұрыс жауапты таңдаңыз: ",
    "дұрыс жауапты табыңыз: ",
)


def clean_text(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "").strip())


def clean_prompt_pair(prompt_ru: str, prompt_kz: str) -> tuple[str, str]:
    pr = clean_text(prompt_ru)
    pk = clean_text(prompt_kz)

    for p in NOISE_PHRASES_RU:
        pr = re.sub(p, " ", pr, flags=re.I)
    for p in NOISE_PHRASES_KZ:
        pk = re.sub(p, " ", pk, flags=re.I)

    pr = SERIES_PATTERN.sub(" ", pr)
    pk = SERIES_PATTERN.sub(" ", pk)

    for pref in LEADING_PREFIXES:
        if pr.lower().startswith(pref):
            pr = pr[len(pref):]
        if pk.lower().startswith(pref):
            pk = pk[len(pref):]

    pr = VARIANT_PATTERN.sub("", pr).strip()
    pk = VARIANT_PATTERN.sub("", pk).strip()
    pr = clean_text(pr).strip(" .")
    pk = clean_text(pk).strip(" .")
    return pr, pk


def prompt_skeleton(prompt: str) -> str:
    """Нормализация для смысловой дедупликации."""
    s = clean_text(prompt).lower()
    for pref in LEADING_PREFIXES:
        if s.startswith(pref):
            s = s[len(pref):]
    s = re.sub(r"[\"'«»]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .?!")
    return s


def clean_keywords(kw: str, *, kz: bool) -> str:
    bad = {"пример", "мысал"} if kz else {"пример", "мысал"}
    out: list[str] = []
    for token in (kw or "").split("|"):
        t = clean_text(token).lower()
        if not t or t in bad:
            continue
        out.append(token.strip())
    return "|".join(out)


def parse_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for x in re.split(r"[|,\s]+", (raw or "").strip()):
        if not x:
            continue
        try:
            ids.append(int(x))
        except ValueError:
            return []
    return ids


def validate_and_repair_row(row: dict[str, str]) -> dict[str, str] | None:
    row = dict(row)

    row["prompt_ru"], row["prompt_kz"] = clean_prompt_pair(row.get("prompt_ru", ""), row.get("prompt_kz", ""))
    row["topic_ru"] = clean_text(VARIANT_PATTERN.sub("", row.get("topic_ru", "")))
    row["topic_kz"] = clean_text(VARIANT_PATTERN.sub("", row.get("topic_kz", "")))
    row["explanation_ru"] = clean_text(re.sub(r"\s*Вариант\s+\d+\.?\s*$", "", row.get("explanation_ru", ""), flags=re.I))
    row["explanation_kz"] = clean_text(re.sub(r"\s*Вариант\s+\d+\.?\s*$", "", row.get("explanation_kz", ""), flags=re.I))
    row["keywords_ru"] = clean_keywords(row.get("keywords_ru", ""), kz=False)
    row["keywords_kz"] = clean_keywords(row.get("keywords_kz", ""), kz=True)

    if not row["prompt_ru"] or not row["prompt_kz"]:
        return None
    if len(row["prompt_ru"].split()) < 3:
        return None
    if SERIES_PATTERN.search(row["prompt_ru"]) or SERIES_PATTERN.search(row["prompt_kz"]):
        return None

    qtype = clean_text(row.get("type", "")).lower()

    if qtype == "single_choice":
        opts_ru = [x.strip() for x in (row.get("options_ru") or "").split("|") if x.strip()]
        opts_kz = [x.strip() for x in (row.get("options_kz") or "").split("|") if x.strip()]
        ids = parse_ids(row.get("correct_option_ids", ""))

        if len(opts_ru) != 4:
            return None
        if not opts_kz:
            opts_kz = list(opts_ru)
        if len(opts_kz) != 4:
            opts_kz = list(opts_ru)
        if len(set(x.lower() for x in opts_ru)) < 4:
            return None
        if len(ids) != 1 or not (1 <= ids[0] <= 4):
            return None

        row["options_ru"] = "|".join(opts_ru)
        row["options_kz"] = "|".join(opts_kz)
        row["correct_option_ids"] = str(ids[0])
        if not row["explanation_ru"]:
            row["explanation_ru"] = "Выбор основан на корректном предметном факте из вопроса."
        if not row["explanation_kz"]:
            row["explanation_kz"] = "Таңдау сұрақтағы дұрыс пәндік фактіге негізделген."
        return row

    if qtype == "multi_choice":
        opts_ru = [x.strip() for x in (row.get("options_ru") or "").split("|") if x.strip()]
        opts_kz = [x.strip() for x in (row.get("options_kz") or "").split("|") if x.strip()]
        ids = parse_ids(row.get("correct_option_ids", ""))

        if len(opts_ru) < 4:
            return None
        if not opts_kz:
            opts_kz = list(opts_ru)
        if len(opts_kz) != len(opts_ru):
            opts_kz = list(opts_ru)
        valid_ids = [i for i in sorted(set(ids)) if 1 <= i <= len(opts_ru)]
        if len(valid_ids) < 2:
            # Если фактически single_choice — сохраняем как single_choice.
            if len(valid_ids) == 1 and len(opts_ru) >= 4:
                row["type"] = "single_choice"
                row["options_ru"] = "|".join(opts_ru[:4])
                row["options_kz"] = "|".join(opts_kz[:4])
                row["correct_option_ids"] = str(valid_ids[0] if valid_ids[0] <= 4 else 1)
                if not row["explanation_ru"]:
                    row["explanation_ru"] = "Выбор основан на корректном предметном факте из вопроса."
                if not row["explanation_kz"]:
                    row["explanation_kz"] = "Таңдау сұрақтағы дұрыс пәндік фактіге негізделген."
                return row
            return None

        row["options_ru"] = "|".join(opts_ru)
        row["options_kz"] = "|".join(opts_kz)
        row["correct_option_ids"] = "|".join(str(i) for i in valid_ids)
        return row

    if qtype == "short_text":
        sa = clean_text(row.get("sample_answer_ru", ""))
        if not sa or len(sa) < 2:
            return None
        # Удаляем примитивные short_text "в каком году -> 1945".
        if YEAR_QUESTION_PATTERN.search(row["prompt_ru"]) and ONLY_DIGITS_PATTERN.match(sa):
            return None
        # Минимальные осмысленные keywords.
        if not row["keywords_ru"]:
            words = [w.lower() for w in re.findall(r"[а-яa-z0-9]+", sa) if len(w) > 2]
            row["keywords_ru"] = "|".join(words[:3])
        if not row["keywords_kz"]:
            row["keywords_kz"] = row["keywords_ru"]
        if not row["explanation_ru"]:
            row["explanation_ru"] = "Ожидается ответ с ключевыми фактами по теме вопроса."
        if not row["explanation_kz"]:
            row["explanation_kz"] = "Сұрақ тақырыбы бойынша негізгі фактілері бар жауап күтіледі."
        return row

    return None


def semantic_key(row: dict[str, str]) -> tuple:
    subject = clean_text(row.get("subject_ru", ""))
    topic = clean_text(row.get("topic_ru", ""))
    qtype = clean_text(row.get("type", ""))
    core = prompt_skeleton(row.get("prompt_ru", ""))

    if qtype in {"single_choice", "multi_choice"}:
        opts = [x.strip() for x in (row.get("options_ru") or "").split("|") if x.strip()]
        ids = parse_ids(row.get("correct_option_ids", ""))
        vals = []
        for i in ids:
            if 1 <= i <= len(opts):
                vals.append(prompt_skeleton(opts[i - 1]))
        return (subject, topic, qtype, core, tuple(sorted(vals)))

    ans = prompt_skeleton(row.get("sample_answer_ru", ""))
    return (subject, topic, qtype, core, ans)


def template_signature(row: dict[str, str]) -> str:
    """Грубая сигнатура формы вопроса для ограничения клонов."""
    subj = clean_text(row.get("subject_ru", ""))
    topic = clean_text(row.get("topic_ru", ""))
    q = prompt_skeleton(row.get("prompt_ru", ""))

    if re.search(r"чему равно # [+\-×÷] #", q):
        kind = "arith_binary"
    elif "решите" in q and "x" in q:
        kind = "solve_x"
    elif YEAR_QUESTION_PATTERN.search(q):
        kind = "year_fact"
    elif "какая формула" in q or "формула" in q:
        kind = "formula"
    elif "как называется" in q:
        kind = "term_name"
    else:
        kind = q[:90]
    return f"{subj}|{topic}|{kind}"


def main() -> None:
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    print(f"Загружено строк: {len(rows)}")

    # 1) Валидация/ремонт строк.
    validated: list[dict[str, str]] = []
    dropped_invalid = 0
    for row in rows:
        fixed = validate_and_repair_row(row)
        if fixed is None:
            dropped_invalid += 1
            continue
        validated.append(fixed)
    print(f"Удалено невалидных/слабых: {dropped_invalid}")

    # 2) Смысловая дедупликация.
    seen: set[tuple] = set()
    deduped: list[dict[str, str]] = []
    for row in validated:
        key = semantic_key(row)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    print(f"Удалено смысловых дублей: {len(validated) - len(deduped)}")

    # 3) Ограничение однотипных шаблонов.
    template_cap = 1000
    by_sig_count: Counter[str] = Counter()
    limited: list[dict[str, str]] = []
    dropped_templates = 0
    for row in deduped:
        sig = template_signature(row)
        if by_sig_count[sig] >= template_cap:
            dropped_templates += 1
            continue
        by_sig_count[sig] += 1
        limited.append(row)
    print(f"Удалено лишних шаблонных: {dropped_templates}")

    # 4) Снижение перенасыщения датами в истории.
    history_subjects = {"всемирная история", "история казахстана"}
    year_cap_per_topic = 8
    year_count: Counter[tuple[str, str]] = Counter()
    final: list[dict[str, str]] = []
    dropped_year = 0
    for row in limited:
        subj = clean_text(row.get("subject_ru", "")).lower()
        topic = clean_text(row.get("topic_ru", "")).lower()
        if subj in history_subjects and YEAR_QUESTION_PATTERN.search(row.get("prompt_ru", "")):
            k = (subj, topic)
            if year_count[k] >= year_cap_per_topic:
                dropped_year += 1
                continue
            year_count[k] += 1
        final.append(row)
    print(f"Удалено избыточных датных вопросов: {dropped_year}")

    # 5) Финальная запись.
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final)

    print(f"Итого строк: {len(final)} (было {len(rows)})")
    print(f"Сохранено в {INPUT_CSV}")


if __name__ == "__main__":
    main()
