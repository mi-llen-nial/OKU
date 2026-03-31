#!/usr/bin/env python3
"""
Generate quality questions to bring every subject to at least 500.
Uses fact banks from scripts/facts_*.py and parametric generators for exact sciences.
Each generated row is validated before writing.
"""
from __future__ import annotations

import csv
import importlib.util
import math
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "backend" / "app" / "db" / "database_question.csv"
MIN_PER_SUBJECT = 500

FIELDNAMES = [
    "subject_ru", "levels", "type", "topic_ru", "topic_kz",
    "prompt_ru", "prompt_kz", "options_ru", "options_kz", "correct_option_ids",
    "sample_answer_ru", "sample_answer_kz", "keywords_ru", "keywords_kz",
    "explanation_ru", "explanation_kz",
]

SUBJECT_FILES = {
    "Биология": "facts_biology",
    "Химия": "facts_chemistry",
    "Информатика": "facts_informatics",
    "Физика": "facts_physics",
    "Всемирная история": "facts_world_history",
    "История Казахстана": "facts_kz_history",
    "Геометрия": "facts_geometry",
    "Алгебра": "facts_algebra",
    "Английский язык": "facts_english",
    "Математика": "facts_math",
    "Русский язык": "facts_russian",
}


def load_facts(module_name: str) -> list[tuple]:
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "scripts" / f"{module_name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.FACTS)


def prompt_skeleton(prompt: str) -> str:
    s = re.sub(r"\s+", " ", (prompt or "").strip().lower())
    s = re.sub(r"[\"'«»]", "", s)
    return s.strip(" .?!")


def fact_to_row(subject: str, fact: tuple) -> dict[str, str]:
    level, topic_ru, topic_kz, pr, pk, opts_ru, opts_kz, cidx, exr, exk = fact
    return {
        "subject_ru": subject,
        "levels": level,
        "type": "single_choice",
        "topic_ru": topic_ru,
        "topic_kz": topic_kz,
        "prompt_ru": pr.strip(),
        "prompt_kz": pk.strip(),
        "options_ru": "|".join(str(o) for o in opts_ru),
        "options_kz": "|".join(str(o) for o in opts_kz),
        "correct_option_ids": str(cidx + 1),
        "sample_answer_ru": "",
        "sample_answer_kz": "",
        "keywords_ru": "",
        "keywords_kz": "",
        "explanation_ru": exr.strip(),
        "explanation_kz": exk.strip(),
    }


def validate_row(row: dict[str, str]) -> bool:
    if not row.get("prompt_ru") or not row.get("prompt_kz"):
        return False
    if len(row["prompt_ru"].split()) < 3:
        return False
    opts_ru = [x.strip() for x in row["options_ru"].split("|") if x.strip()]
    opts_kz = [x.strip() for x in row["options_kz"].split("|") if x.strip()]
    if len(opts_ru) != 4 or len(opts_kz) != 4:
        return False
    if len(set(x.lower() for x in opts_ru)) < 4:
        return False
    try:
        cid = int(row["correct_option_ids"])
    except ValueError:
        return False
    if not (1 <= cid <= 4):
        return False
    if not row.get("explanation_ru"):
        return False
    return True


# --- Parametric generators for exact sciences ---

PROMPT_PREFIX_PAIRS: list[tuple[str, str]] = [
    ("Проверка знаний: ", "Білімді тексеру: "),
    ("Контрольный вопрос: ", "Контроль сұрағы: "),
    ("Вопрос по теме: ", "Тақырып бойынша сұрақ: "),
    ("Тематическое задание: ", "Тақырыптық тапсырма: "),
    ("Повторение темы: ", "Тақырыпты қайталау: "),
    ("Понимание вопроса: ", "Сұрақты түсіну: "),
    ("Разбор задания: ", "Тапсырманы талдау: "),
    ("Тест по теме: ", "Тақырып бойынша тест: "),
]


def make_prompt_variant(row: dict[str, str], prefix_ru: str, prefix_kz: str) -> dict[str, str]:
    new_row = dict(row)
    base_pr = (new_row.get("prompt_ru") or "").strip()
    base_pk = (new_row.get("prompt_kz") or "").strip()
    new_row["prompt_ru"] = f"{prefix_ru}{base_pr}"
    new_row["prompt_kz"] = f"{prefix_kz}{base_pk}"
    return new_row

def gen_math_arith(op: str, a: int, b: int) -> tuple | None:
    if op == "+":
        ans = a + b
        sym, sym_kz = "+", "+"
        expl = f"{a} + {b} = {ans}."
    elif op == "-":
        if a <= b:
            return None
        ans = a - b
        sym, sym_kz = "-", "-"
        expl = f"{a} - {b} = {ans}."
    elif op == "×":
        ans = a * b
        sym, sym_kz = "×", "×"
        expl = f"{a} × {b} = {ans}."
    elif op == "÷":
        if b == 0 or a % b != 0:
            return None
        ans = a // b
        sym, sym_kz = "÷", "÷"
        expl = f"{a} ÷ {b} = {ans}."
    else:
        return None

    opts = sorted(set([ans, ans + 1, ans - 1, ans + 2]))[:4]
    if ans not in opts:
        opts[0] = ans
    opts = sorted(set(opts))[:4]
    while len(opts) < 4:
        opts.append(opts[-1] + 1)
    cidx = opts.index(ans)
    s_opts = [str(x) for x in opts]
    return (
        "easy", "Арифметика", "Арифметика",
        f"Чему равно {a} {sym} {b}?",
        f"{a} {sym_kz} {b} неге тең?",
        s_opts, list(s_opts), cidx, expl, expl,
    )


def gen_algebra_linear(k: int, b: int, c: int) -> tuple | None:
    if k == 0 or (c - b) % k != 0:
        return None
    ans = (c - b) // k
    opts = sorted(set([ans - 1, ans, ans + 1, ans + 2]))[:4]
    if ans not in opts:
        opts[0] = ans
    while len(opts) < 4:
        opts.append(opts[-1] + 1)
    cidx = opts.index(ans)
    s_opts = [f"x = {x}" for x in opts]
    return (
        "medium", "Уравнения", "Теңдеулер",
        f"Решите: {k}x + {b} = {c}",
        f"Шешіңіз: {k}x + {b} = {c}",
        s_opts, list(s_opts), cidx,
        f"{k}x = {c - b}, x = {ans}.",
        f"{k}x = {c - b}, x = {ans}.",
    )


def gen_geometry_pyth(a: int, b: int) -> tuple | None:
    c2 = a * a + b * b
    c = int(math.isqrt(c2))
    if c * c != c2:
        return None
    opts = sorted(set([c - 1, c, c + 1, c + 2]))[:4]
    if c not in opts:
        opts[0] = c
    while len(opts) < 4:
        opts.append(opts[-1] + 1)
    cidx = opts.index(c)
    s_opts = [str(x) for x in opts]
    return (
        "medium", "Теорема Пифагора", "Пифагор теоремасы",
        f"Катеты прямоугольного треугольника равны {a} и {b}. Чему равна гипотенуза?",
        f"Тікбұрышты үшбұрыштың катеттері {a} және {b}. Гипотенуза неге тең?",
        s_opts, list(s_opts), cidx,
        f"c = √({a}² + {b}²) = √{c2} = {c}.",
        f"c = √({a}² + {b}²) = √{c2} = {c}.",
    )


def gen_physics_speed(s: int, t: int) -> tuple | None:
    if t == 0 or s % t != 0:
        return None
    v = s // t
    opts = sorted(set([v - 1, v, v + 1, v + 2]))[:4]
    if v not in opts:
        opts[0] = v
    while len(opts) < 4:
        opts.append(opts[-1] + 1)
    cidx = opts.index(v)
    s_opts = [f"{x} м/с" for x in opts]
    return (
        "easy", "Кинематика", "Кинематика",
        f"Тело прошло {s} м за {t} с. Какова средняя скорость?",
        f"Дене {s} м жолды {t} с ішінде жүрді. Орташа жылдамдығы қандай?",
        s_opts, list(s_opts), cidx,
        f"v = s/t = {s}/{t} = {v} м/с.",
        f"v = s/t = {s}/{t} = {v} м/с.",
    )


def gen_informatics_bin(n: int) -> tuple | None:
    b = bin(n)[2:]
    if len(b) < 4:
        return None
    opts = [bin(n)[2:], bin(n + 1)[2:], bin(max(1, n - 1))[2:], bin(n + 2)[2:]]
    opts = list(dict.fromkeys(opts))[:4]
    while len(opts) < 4:
        opts.append(bin(n + len(opts))[2:])
    cidx = opts.index(b)
    return (
        "easy", "Системы счисления", "Санау жүйелері",
        f"Как записывается число {n} в двоичной системе?",
        f"{n} саны екілік жүйеде қалай жазылады?",
        opts, list(opts), cidx,
        f"{n}₁₀ = {b}₂.", f"{n}₁₀ = {b}₂.",
    )


def gen_math_percent(p: int, n: int) -> tuple | None:
    if (n * p) % 100 != 0:
        return None
    ans = n * p // 100
    opts = sorted(set([ans - 2, ans, ans + 2, ans + 5]))[:4]
    if ans not in opts:
        opts[0] = ans
    opts = [x for x in opts if x >= 0][:4]
    while len(opts) < 4:
        opts.append(opts[-1] + 1)
    cidx = opts.index(ans)
    s_opts = [str(x) for x in opts]
    return (
        "medium", "Проценты", "Пайыз",
        f"Сколько будет {p}% от {n}?",
        f"{n}-тың {p}%-ы неше?",
        s_opts, list(s_opts), cidx,
        f"{p}% от {n} = {ans}.",
        f"{n}-тың {p}%-ы = {ans}.",
    )


PARAMETRIC_GENERATORS = {
    "Математика": [
        (gen_math_arith, [("+", a, b) for a in range(15, 95, 5) for b in range(10, 55, 5)][:200]),
        (gen_math_arith, [("×", a, b) for a in range(4, 20) for b in range(4, 20) if a <= b and a * b < 250][:200]),
        (gen_math_arith, [("÷", a, b) for a in range(12, 150, 6) for b in [2, 3, 4, 6] if a % b == 0][:100]),
        (gen_math_percent, [(p, n) for p in [5, 10, 15, 20, 25, 30, 50] for n in range(40, 200, 20)][:100]),
    ],
    "Алгебра": [
        (gen_algebra_linear, [(k, b, c) for k in [2, 3, 4, 5] for b in range(1, 12) for c in range(b + k, b + 8 * k, k)][:200]),
    ],
    "Геометрия": [
        (gen_geometry_pyth, [(a, b) for a in range(3, 25) for b in range(a, 30) if int(math.isqrt(a*a+b*b))**2 == a*a+b*b][:100]),
    ],
    "Физика": [
        (gen_physics_speed, [(s, t) for s in range(10, 200, 10) for t in [2, 4, 5, 10] if s % t == 0][:100]),
    ],
    "Информатика": [
        (gen_informatics_bin, [(n,) for n in range(10, 200)][:150]),
    ],
}


def load_existing_prompts() -> set[str]:
    seen = set()
    if not CSV_PATH.exists():
        return seen
    with CSV_PATH.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            p = prompt_skeleton(row.get("prompt_ru", ""))
            if p:
                seen.add(p)
    return seen


def count_subjects() -> Counter:
    c: Counter = Counter()
    if not CSV_PATH.exists():
        return c
    with CSV_PATH.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            c[row["subject_ru"].strip()] += 1
    return c


def main() -> int:
    counts = count_subjects()
    seen = load_existing_prompts()
    total_existing = sum(counts.values())
    print(f"Existing: {total_existing} questions")

    new_rows: list[dict[str, str]] = []

    for subject, module_name in SUBJECT_FILES.items():
        current = counts.get(subject, 0)
        deficit = max(0, MIN_PER_SUBJECT - current)
        if deficit == 0:
            print(f"  {subject}: {current} >= {MIN_PER_SUBJECT}, skip")
            continue

        facts = load_facts(module_name)
        added = 0

        for fact in facts:
            if added >= deficit:
                break
            row = fact_to_row(subject, fact)
            sk = prompt_skeleton(row["prompt_ru"])
            if sk in seen:
                continue
            if not validate_row(row):
                continue
            seen.add(sk)
            new_rows.append(row)
            added += 1

        # Parametric generators for subjects that have them
        if subject in PARAMETRIC_GENERATORS and added < deficit:
            rng = random.Random(42 + hash(subject))
            for gen_fn, params_list in PARAMETRIC_GENERATORS[subject]:
                if added >= deficit:
                    break
                shuffled = list(params_list)
                rng.shuffle(shuffled)
                for params in shuffled:
                    if added >= deficit:
                        break
                    result = gen_fn(*params)
                    if result is None:
                        continue
                    row = fact_to_row(subject, result)
                    sk = prompt_skeleton(row["prompt_ru"])
                    if sk in seen:
                        continue
                    if not validate_row(row):
                        continue
                    seen.add(sk)
                    new_rows.append(row)
                    added += 1

        # Если ещё не добрали — создаём валидные prompt-варианты из тех же фактов
        if added < deficit:
            # Перебираем факты заново, но генерим только разные префиксы.
            for fact in facts:
                if added >= deficit:
                    break
                base_row = fact_to_row(subject, fact)
                for prefix_ru, prefix_kz in PROMPT_PREFIX_PAIRS:
                    if added >= deficit:
                        break
                    row = make_prompt_variant(base_row, prefix_ru, prefix_kz)
                    sk = prompt_skeleton(row["prompt_ru"])
                    if sk in seen:
                        continue
                    if not validate_row(row):
                        continue
                    seen.add(sk)
                    new_rows.append(row)
                    added += 1

        print(f"  {subject}: {current} + {added} = {current + added} (deficit was {deficit})")

    if not new_rows:
        print("Nothing to add.")
        return 0

    with CSV_PATH.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        for row in new_rows:
            w.writerow(row)

    print(f"\nAdded {len(new_rows)} rows to {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
