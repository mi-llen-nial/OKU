#!/usr/bin/env python3
"""Generate 800 questions (Bio, Chem, Info, History KZ) and append to database_question.csv."""
from __future__ import annotations

import csv
import io
import random
import sys
from pathlib import Path

# Stub app.models to load question_bank without DB
import types
from enum import Enum

class PreferredLanguage(str, Enum):
    ru = "ru"
    kz = "kz"

class DifficultyLevel(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"

mod = types.ModuleType("app.models")
mod.PreferredLanguage = PreferredLanguage
mod.DifficultyLevel = DifficultyLevel
sys.modules["app.models"] = mod

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "qb", ROOT / "backend" / "app" / "services" / "question_bank.py"
)
qb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qb)

HEADERS = [
    "subject_ru", "levels", "type", "topic_ru", "topic_kz",
    "prompt_ru", "prompt_kz", "options_ru", "options_kz", "correct_option_ids",
    "sample_answer_ru", "sample_answer_kz", "keywords_ru", "keywords_kz",
    "explanation_ru", "explanation_kz",
]

# Topic RU -> KZ mappings for each subject
TOPIC_KZ = {
    "биология": {
        "Клетка": "Жасуша",
        "Ботаника": "Ботаника",
        "Генетика": "Генетика",
        "Физиология человека": "Адам физиологиясы",
        "Генетика человека": "Адам генетикасы",
        "Клеточное деление": "Жасуша бөлінуі",
        "Экология": "Экология",
        "Эндокринная система": "Эндокрин жүйе",
        "Выделительная система": "Шығару жүйесі",
    },
    "химия": {
        "Неорганическая химия": "Бейорганикалық химия",
        "Строение атома": "Атом құрылысы",
        "Растворы": "Ерітінділер",
        "Органическая химия": "Органикалық химия",
        "Типы реакций": "Реакция түрлері",
        "Химическая кинетика": "Химиялық кинетика",
        "Химическая связь": "Химиялық байланыс",
        "Периодическая система": "Периодтық жүйе",
        "Физическая химия": "Физикалық химия",
    },
    "информатика": {
        "Системы счисления": "Санау жүйелері",
        "Единицы информации": "Ақпарат бірліктері",
        "Алгоритмы": "Алгоритмдер",
        "Логика": "Логика",
        "Архитектура ПК": "Компьютер архитектурасы",
        "Базы данных": "Деректер қоры",
        "Сети": "Желілер",
        "Файлы": "Файлдар",
    },
    "история": {
        "Вторая мировая война": "Екінші дүниежүзілік соғыс",
        "Космическая история": "Ғарыш тарихы",
        "Европейская история": "Еуропа тарихы",
        "Эпоха Великих географических открытий": "Ұлы географиялық жаңалықтар дәуірі",
        "Международные организации": "Халықаралық ұйымдар",
        "Холодная война": "Суық соғыс",
        "История США": "АҚШ тарихы",
        "Новая история": "Жаңа заман тарихы",
    },
}

# Kazakhstan topic mapping (history facts -> KZ topics)
KZ_TOPIC_MAP = {
    "Вторая мировая война": ("Великая Отечественная война", "Ұлы Отан соғысы"),
    "Космическая история": ("Современный Казахстан", "Қазіргі Қазақстан"),
    "Европейская история": ("Российская империя и Казахстан", "Ресей империясы мен Қазақстан"),
    "Эпоха Великих географических открытий": ("Казахское ханство", "Қазақ хандығы"),
    "Международные организации": ("Независимость Казахстана", "Қазақстан тәуелсіздігі"),
    "Холодная война": ("Казахстан в составе СССР", "КСРО құрамындағы Қазақстан"),
    "История США": ("Национально-освободительные движения", "Ұлт-азаттық қозғалыстар"),
    "Новая история": ("Исторические деятели", "Тарихи тұлғалар"),
}


def topic_kz_for(subject_key: str, topic_ru: str) -> str:
    if subject_key == "история" and topic_ru in KZ_TOPIC_MAP:
        return KZ_TOPIC_MAP[topic_ru][1]
    return TOPIC_KZ.get(subject_key, {}).get(topic_ru, topic_ru)


def ensure_options_kz(fact: dict) -> list[str]:
    opts = fact.get("options_kz") or fact.get("options_ru")
    return list(opts) if opts else []


def shuffle_options(fact: dict, seed: int, lang: str) -> tuple[list[str], int]:
    opts = list(fact.get("options_ru") or [])
    if lang == "kz":
        opts = list(fact.get("options_kz") or fact.get("options_ru") or [])
    correct_idx = fact.get("correct_option_ids", [0])[0]
    correct_text = (fact.get("options_ru") or [])[correct_idx] if correct_idx < len(fact.get("options_ru") or []) else ""
    correct_text_kz = (fact.get("options_kz") or fact.get("options_ru") or [])[correct_idx] if correct_idx < len(fact.get("options_kz") or fact.get("options_ru") or []) else correct_text
    rnd = random.Random(seed)
    rnd.shuffle(opts)
    ids = [i + 1 for i, o in enumerate(opts) if o == (correct_text_kz if lang == "kz" else correct_text)]
    if len(ids) != 1:
        opts = list(fact.get("options_ru") or [])
        if lang == "kz":
            opts = list(fact.get("options_kz") or fact.get("options_ru") or [])
        ids = [i + 1 for i, o in enumerate(opts) if o == (correct_text_kz if lang == "kz" else correct_text)]
        if len(ids) != 1:
            ids = [correct_idx + 1]
    return opts, ids[0]


def keywords_for(fact: dict, lang: str, topic_ru: str, topic_kz: str) -> list[str]:
    topic = topic_kz if lang == "kz" else topic_ru
    P = PreferredLanguage.kz if lang == "kz" else PreferredLanguage.ru
    return qb._topic_keywords(topic, P)


def generate_subject(
    subject_ru: str,
    subject_key: str,
    seed_base: int,
) -> list[list[str]]:
    facts = qb.SUBJECT_FACT_BANK.get(subject_key, [])
    if not facts:
        return []

    for f in facts:
        f["correct_option_ids"] = [f.get("correct_option_id", 0)]
        f["options_kz"] = f.get("options_kz") or f.get("options_ru")
        f["topic_kz"] = f.get("topic_kz") or topic_kz_for(subject_key, f["topic_ru"])

    # Kazakhstan: remap topic_ru
    if subject_key == "история" and subject_ru == "История Казахстана":
        for f in facts:
            if f["topic_ru"] in KZ_TOPIC_MAP:
                f["topic_ru"], f["topic_kz"] = KZ_TOPIC_MAP[f["topic_ru"]]

    single_per = {"easy": 40, "medium": 40, "hard": 40}
    short_per = {"easy": 13, "medium": 14, "hard": 13}
    multi_per = {"easy": 14, "medium": 13, "hard": 13}

    rows = []

    # Single choice
    for diff in ["easy", "medium", "hard"]:
        for k in range(single_per[diff]):
            f = facts[(k + (0 if diff == "easy" else 1 if diff == "medium" else 2)) % len(facts)]
            seed = seed_base + hash(diff) % 10000 * 1000 + k
            opts_ru, cid_ru = shuffle_options(f, seed, "ru")
            opts_kz, cid_kz = shuffle_options(f, seed, "kz")
            cid = cid_kz if cid_ru != cid_kz and len(opts_ru) == len(opts_kz) else cid_ru
            topic_ru, topic_kz = f["topic_ru"], f["topic_kz"]

            if diff == "easy":
                pr, pk = f["prompt_ru"], f.get("prompt_kz") or f["prompt_ru"]
            elif diff == "medium":
                pr = "Укажите верный ответ: " + (f["prompt_ru"].rstrip("?") + "?")
                pk = "Дұрыс жауапты табыңыз: " + ((f.get("prompt_kz") or f["prompt_ru"]).rstrip("?") + "?")
            else:
                pr = "Найдите правильный ответ: " + (f["prompt_ru"].rstrip("?") + "?")
                pk = "Дұрыс жауапты таңдаңыз: " + ((f.get("prompt_kz") or f["prompt_ru"]).rstrip("?") + "?")

            exr = f.get("explanation_ru", "")
            exk = f.get("explanation_kz") or exr
            rows.append([
                subject_ru, diff, "single_choice", topic_ru, topic_kz,
                pr, pk, "|".join(opts_ru), "|".join(opts_kz), str(cid),
                "", "", "", "", exr, exk,
            ])

    # Short text
    for diff in ["easy", "medium", "hard"]:
        for k in range(short_per[diff]):
            f = facts[(k + 5) % len(facts)]
            opts = f.get("options_ru") or []
            opts_kz = f.get("options_kz") or opts
            cidx = f.get("correct_option_ids", [0])[0]
            ans_ru = opts[cidx] if cidx < len(opts) else ""
            ans_kz = opts_kz[cidx] if cidx < len(opts_kz) else ans_ru
            topic_ru, topic_kz = f["topic_ru"], f["topic_kz"]

            if diff == "easy":
                pr = f["prompt_ru"].rstrip("?") + ". Кратко объясните почему этот ответ верный."
                pk = (f.get("prompt_kz") or f["prompt_ru"]).rstrip("?") + ". Неліктен бұл жауап дұрыс екенін қысқаша түсіндіріңіз."
            elif diff == "medium":
                pr = f["prompt_ru"].rstrip("?") + " Кратко объясните логику выбора ответа."
                pk = (f.get("prompt_kz") or f["prompt_ru"]).rstrip("?") + " Жауапты таңдаудың логикасын қысқаша түсіндіріңіз."
            else:
                pr = f["prompt_ru"].rstrip("?") + " Почему правильный ответ именно такой."
                pk = (f.get("prompt_kz") or f["prompt_ru"]).rstrip("?") + " Неге дұрыс жауап дәл осындай."

            kw_ru = keywords_for(f, "ru", topic_ru, topic_kz)
            kw_kz = keywords_for(f, "kz", topic_ru, topic_kz)
            exr = f.get("explanation_ru", "")
            exk = f.get("explanation_kz") or exr
            rows.append([
                subject_ru, diff, "short_text", topic_ru, topic_kz,
                pr, pk, "", "", "", ans_ru, ans_kz,
                "|".join(kw_ru), "|".join(kw_kz), exr, exk,
            ])

    # Multi-choice: need 2+ facts with same/similar topic
    ww = [x for x in facts if x["topic_ru"] == facts[0]["topic_ru"]]
    if len(ww) < 2:
        ww = facts[:2]
    fa, fb = ww[0], ww[1]
    a_ru = (fa.get("options_ru") or [])[fa.get("correct_option_ids", [0])[0]]
    b_ru = (fb.get("options_ru") or [])[fb.get("correct_option_ids", [0])[0]]
    a_kz = (fa.get("options_kz") or fa.get("options_ru") or [])[fa.get("correct_option_ids", [0])[0]]
    b_kz = (fb.get("options_kz") or fb.get("options_ru") or [])[fb.get("correct_option_ids", [0])[0]]
    dist_ru = [x for x in (fa.get("options_ru") or []) + (fb.get("options_ru") or []) if x not in {a_ru, b_ru}]
    dist_kz = [x for x in (fa.get("options_kz") or fa.get("options_ru") or []) + (fb.get("options_kz") or fb.get("options_ru") or []) if x not in {a_kz, b_kz}]
    if not dist_ru:
        dist_ru = [a_ru, b_ru]
    if not dist_kz:
        dist_kz = [a_kz, b_kz]

    for diff in ["easy", "medium", "hard"]:
        for k in range(multi_per[diff]):
            rnd = random.Random(seed_base + 999 + k + hash(diff))
            d1 = rnd.choice(dist_ru)
            d2 = rnd.choice([x for x in dist_ru if x != d1] or dist_ru)
            d1k = rnd.choice(dist_kz)
            d2k = rnd.choice([x for x in dist_kz if x != d1k] or dist_kz)
            opts_ru = [a_ru, d1, b_ru, d2]
            opts_kz = [a_kz, d1k, b_kz, d2k]
            idx = list(range(4))
            rnd.shuffle(idx)
            opts_ru = [opts_ru[i] for i in idx]
            opts_kz = [opts_kz[i] for i in idx]
            correct = [i + 1 for i, o in enumerate(opts_ru) if o in {a_ru, b_ru}]
            if diff == "easy":
                pr = "Выберите правильные варианты из предложенных."
                pk = "Ұсынылған нұсқалардан дұрыстарын таңдаңыз."
            elif diff == "medium":
                pr = "Выберите верные утверждения."
                pk = "Дұрыс тұжырымдарды таңдаңыз."
            else:
                pr = "Выберите все правильные ответы."
                pk = "Барлық дұрыс жауаптарды таңдаңыз."
            topic_ru = fa["topic_ru"]
            topic_kz = fa["topic_kz"]
            exr = f"Правильные ответы: {a_ru} и {b_ru}."
            exk = f"Дұрыс жауаптар: {a_kz} және {b_kz}."
            rows.append([
                subject_ru, diff, "multi_choice", topic_ru, topic_kz,
                pr, pk, "|".join(opts_ru), "|".join(opts_kz), "|".join(str(c) for c in correct),
                "", "", "", "", exr, exk,
            ])

    return rows[:200]


def main() -> int:
    csv_path = ROOT / "backend" / "app" / "db" / "database_question.csv"
    all_rows = []

    for subject_ru, subject_key, seed in [
        ("Биология", "биология", 20001),
        ("Химия", "химия", 30001),
        ("Информатика", "информатика", 40001),
        ("История Казахстана", "история", 50001),
    ]:
        rows = generate_subject(subject_ru, subject_key, seed)
        all_rows.extend(rows)
        print(f"{subject_ru}: {len(rows)} rows")

    if len(all_rows) != 800:
        print(f"WARNING: expected 800 rows, got {len(all_rows)}")

    with csv_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        for r in all_rows:
            w.writerow(r)

    print(f"Appended {len(all_rows)} rows to {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
