from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.core.config import settings
from app.models import Question, QuestionType
from app.schemas.tests import QuestionFeedback
from app.services.llm import LLMProviderError, llm_chat

logger = logging.getLogger(__name__)

_GENERIC_KEYWORDS = {
    "пример",
    "мысал",
    "answer",
    "response",
    "жауап",
    "қысқа",
    "кратко",
    "түсіндіріңіз",
    "объясните",
}

_STOPWORDS = {
    # RU
    "и", "в", "на", "по", "с", "со", "к", "ко", "о", "об", "от", "до", "из", "у", "для", "что", "это",
    "как", "или", "ли", "а", "но", "же", "не", "да", "нет", "при", "если", "то", "где", "когда", "бы",
    "чтобы", "который", "которая", "которые", "также", "такой", "такая", "такое", "быть", "есть",
    # KZ
    "және", "мен", "бен", "пен", "үшін", "туралы", "бұл", "сол", "егер", "онда", "сияқты", "емес",
    "бар", "жоқ", "қалай", "қайда", "қашан", "неге", "бірақ", "тағы", "да", "де",
    # EN common
    "the", "and", "or", "if", "is", "are", "to", "of", "for", "with", "in", "on", "at", "by", "as",
}


@dataclass
class EvaluationSummary:
    total_score: float
    max_score: float
    feedback: list[QuestionFeedback]
    weak_topics: list[str]


def evaluate_answers(questions: list[Question], answers_by_question_id: dict[int, dict[str, Any]]) -> EvaluationSummary:
    feedback_items: list[QuestionFeedback] = []
    weak_topic_counter: Counter[str] = Counter()

    total_score = 0.0
    max_score = float(len(questions))

    for question in questions:
        student_answer = answers_by_question_id.get(question.id, {})
        score, is_correct = _evaluate_single_question(question, student_answer)
        total_score += score

        topic = str(question.explanation_json.get("topic", "General"))
        explanation_text = str(question.explanation_json.get("correct_explanation", ""))

        if not is_correct:
            weak_topic_counter[topic] += 1

        feedback_items.append(
            QuestionFeedback(
                question_id=question.id,
                prompt=question.prompt,
                topic=topic,
                student_answer=student_answer,
                expected_hint=_expected_hint(question),
                is_correct=is_correct,
                score=round(score, 2),
                explanation=explanation_text,
            )
        )

    weak_topics = [topic for topic, _ in weak_topic_counter.most_common(3)]
    if weak_topics:
        defaults = ["Повторение теории", "Понимание терминов", "Применение на практике"]
        for default_topic in defaults:
            if len(weak_topics) >= 3:
                break
            if default_topic not in weak_topics:
                weak_topics.append(default_topic)

    return EvaluationSummary(
        total_score=round(total_score, 2),
        max_score=max_score,
        feedback=feedback_items,
        weak_topics=weak_topics,
    )


def _evaluate_single_question(question: Question, student_answer: dict[str, Any]) -> tuple[float, bool]:
    if question.type in {QuestionType.single_choice, QuestionType.multi_choice}:
        return _evaluate_choice(question, student_answer)
    if question.type == QuestionType.matching:
        return _evaluate_matching(question, student_answer)
    if question.type in {QuestionType.short_text, QuestionType.oral_answer}:
        return _evaluate_fuzzy_text(question, student_answer)
    return 0.0, False


def _evaluate_choice(question: Question, student_answer: dict[str, Any]) -> tuple[float, bool]:
    expected = sorted(_to_int_list(question.correct_answer_json.get("correct_option_ids", [])))
    selected = sorted(_to_int_list(student_answer.get("selected_option_ids", [])))
    is_correct = selected == expected
    return (1.0 if is_correct else 0.0), is_correct


def _evaluate_matching(question: Question, student_answer: dict[str, Any]) -> tuple[float, bool]:
    expected = {str(k): str(v) for k, v in question.correct_answer_json.get("matches", {}).items()}
    provided = {str(k): str(v) for k, v in student_answer.get("matches", {}).items()}
    if not expected:
        return 0.0, False

    matches = sum(1 for key, value in expected.items() if provided.get(key) == value)
    score = matches / len(expected)
    return score, score == 1.0


def _evaluate_fuzzy_text(question: Question, student_answer: dict[str, Any]) -> tuple[float, bool]:
    student_text = str(
        student_answer.get("text")
        or student_answer.get("spoken_answer_text")
        or student_answer.get("transcript")
        or ""
    )
    normalized_student = _normalize(student_text)

    keywords = _clean_keywords(question.correct_answer_json.get("keywords", []))
    sample_answer = str(question.correct_answer_json.get("sample_answer", ""))
    explanation_text = str(question.explanation_json.get("correct_explanation", ""))
    reference_text = _build_reference_text(
        sample_answer=sample_answer,
        explanation_text=explanation_text,
        keywords=keywords,
    )
    normalized_sample = _normalize(sample_answer)

    if not normalized_student:
        return 0.0, False

    keyword_hits = sum(1 for keyword in keywords if keyword and keyword in normalized_student)
    keyword_score = (keyword_hits / len(keywords)) if keywords else 0.0
    exact_keyword_match = any(normalized_student == keyword for keyword in keywords)
    all_keywords_present = bool(keywords) and all(keyword in normalized_student for keyword in keywords)
    similarity = SequenceMatcher(None, normalized_student, normalized_sample).ratio() if normalized_sample else 0.0
    token_similarity = _jaccard_similarity(normalized_student, normalized_sample)
    formula_similarity = _formula_similarity(student_text, sample_answer)
    concept_sample = _concept_coverage(student_text=student_text, reference_text=sample_answer)
    concept_explanation = _concept_coverage(student_text=student_text, reference_text=explanation_text)
    concept_score = max(concept_sample, (concept_sample * 0.7) + (concept_explanation * 0.3))
    exact_text_match = bool(normalized_sample) and normalized_student == normalized_sample
    formula_targets = _infer_formula_targets_from_prompt(question.prompt)
    discriminant_score = _discriminant_rule_score(prompt=question.prompt, student_text=student_text)
    inferred_numeric = _infer_expected_numeric_from_prompt(question.prompt)

    if exact_text_match:
        return 1.0, True
    if inferred_numeric is not None and _answer_matches_number(student_text, inferred_numeric):
        return 1.0, True
    if _numeric_equivalent(student_text, sample_answer):
        return 0.95, True
    if discriminant_score >= 0.99:
        return 1.0, True
    if discriminant_score >= 0.66:
        return round(discriminant_score, 2), False
    if formula_targets and _is_formula_answer_match(student_text, formula_targets):
        return 0.98, True
    if formula_similarity >= 0.98:
        return 0.95, True

    if keywords:
        heuristic_score = (
            (keyword_score * 0.20)
            + (max(similarity, token_similarity) * 0.25)
            + (concept_score * 0.40)
            + (formula_similarity * 0.15)
        )
        threshold = 0.65
    else:
        # If keywords are missing/low quality, rely on semantic and structural similarity.
        heuristic_score = (max(similarity, token_similarity) * 0.25) + (concept_score * 0.65) + (formula_similarity * 0.10)
        threshold = 0.70

    if exact_keyword_match or all_keywords_present:
        heuristic_score = max(heuristic_score, 0.82)
    if concept_sample >= 0.92:
        heuristic_score = max(heuristic_score, 1.0)
    elif concept_sample >= 0.80:
        heuristic_score = max(heuristic_score, 0.95)
    elif concept_score >= 0.75 and token_similarity >= 0.40:
        heuristic_score = max(heuristic_score, 0.90)
    elif concept_score >= 0.92:
        heuristic_score = max(heuristic_score, 0.95)

    heuristic_score = _clamp(heuristic_score)
    semantic_verdict = None
    if _should_use_semantic_ai(
        question=question,
        student_text=student_text,
        sample_answer=sample_answer,
        heuristic_score=heuristic_score,
    ):
        semantic_verdict = _evaluate_with_semantic_ai(
            question=question,
            student_text=student_text,
            sample_answer=sample_answer,
            reference_text=reference_text,
            keywords=keywords,
        )

    if semantic_verdict is not None:
        ai_score = _clamp(semantic_verdict.score)
        score = round(max(ai_score, heuristic_score if heuristic_score >= 0.9 else 0.0), 2)
        is_correct = semantic_verdict.is_correct or score >= 0.9
        if is_correct and score < threshold:
            score = round(threshold, 2)
    else:
        score = round(heuristic_score, 2)
        is_correct = score >= threshold

    return score, is_correct


def _expected_hint(question: Question) -> dict[str, Any]:
    if question.type in {QuestionType.single_choice, QuestionType.multi_choice}:
        return {"correct_option_ids": question.correct_answer_json.get("correct_option_ids", [])}
    if question.type == QuestionType.matching:
        return {"matches": question.correct_answer_json.get("matches", {})}
    return {
        "keywords": question.correct_answer_json.get("keywords", []),
        "sample_answer": question.correct_answer_json.get("sample_answer", ""),
    }


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _build_reference_text(*, sample_answer: str, explanation_text: str, keywords: list[str]) -> str:
    parts = [sample_answer.strip(), explanation_text.strip(), " ".join(keywords).strip()]
    return " ".join(part for part in parts if part)


def _clean_keywords(raw_keywords: Any) -> list[str]:
    if not isinstance(raw_keywords, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_keywords:
        normalized = _normalize(str(item))
        if not normalized or normalized in _GENERIC_KEYWORDS or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Zа-яА-ЯәіңғүұқөһӘІҢҒҮҰҚӨҺ0-9]+", text.lower())


def _normalize_concept_token(token: str) -> str:
    value = token.lower().strip()
    value = value.replace("ё", "е")
    value = re.sub(r"[^a-zа-яәіңғүұқөһ0-9]", "", value)
    if len(value) <= 4:
        return value
    # Light stemming for RU/KZ/EN to reduce false negatives by inflections.
    for suffix in (
        "лары", "лері", "дар", "дер", "тар", "тер", "дың", "дің", "тың", "тің", "лар", "лер", "менен",
        "иями", "ями", "ами", "ого", "ему", "ому", "ыми", "ими", "ать", "ять", "ить", "ость", "ение",
        "ения", "ция", "ции", "ться", "ется", "ются", "ешь", "ет", "ут", "ют", "ий", "ый", "ой", "ая",
        "ое", "ые", "ого", "ему", "ами", "ах", "ях", "ом", "ем", "ам", "ям", "ов", "ев", "ие", "ия",
        "ing", "ed", "es", "s",
    ):
        if value.endswith(suffix) and len(value) - len(suffix) >= 4:
            return value[: -len(suffix)]
    return value


def _concept_tokens(text: str) -> set[str]:
    output: set[str] = set()
    for token in _tokenize(text):
        normalized = _normalize_concept_token(token)
        if len(normalized) < 3:
            continue
        if normalized in _STOPWORDS or normalized in _GENERIC_KEYWORDS:
            continue
        output.add(normalized)
    return output


def _concept_coverage(*, student_text: str, reference_text: str) -> float:
    reference = _concept_tokens(reference_text)
    student = _concept_tokens(student_text)
    if not reference or not student:
        return 0.0

    hits = 0
    for ref in reference:
        matched = any(
            stud == ref
            or (len(stud) >= 4 and len(ref) >= 4 and (stud.startswith(ref) or ref.startswith(stud)))
            for stud in student
        )
        if matched:
            hits += 1
    return hits / len(reference)


def _jaccard_similarity(student_text: str, sample_text: str) -> float:
    student_tokens = set(_tokenize(student_text))
    sample_tokens = set(_tokenize(sample_text))
    if not student_tokens or not sample_tokens:
        return 0.0
    intersection = len(student_tokens & sample_tokens)
    union = len(student_tokens | sample_tokens)
    if union == 0:
        return 0.0
    return intersection / union


def _normalize_formula(value: str) -> str:
    expression = value.lower().strip()
    expression = expression.replace("**", "^").replace("−", "-").replace("×", "*")
    expression = re.sub(r"^(ответ|жауап|answer)\s*[:=]\s*", "", expression)
    expression = expression.replace("{", "(").replace("}", ")")
    expression = re.sub(r"\s+", "", expression)
    expression = re.sub(r"\^\(([^()]+)\)", r"^\1", expression)
    expression = re.sub(r"\^\{([^{}]+)\}", r"^\1", expression)
    return expression


def _looks_like_formula(value: str) -> bool:
    return bool(re.search(r"[\^\=\+\-\*/]", value))


def _formula_similarity(student_text: str, sample_text: str) -> float:
    normalized_student = _normalize_formula(student_text)
    normalized_sample = _normalize_formula(sample_text)
    if not normalized_student or not normalized_sample:
        return 0.0
    if not (_looks_like_formula(normalized_student) or _looks_like_formula(normalized_sample)):
        return 0.0
    if normalized_student == normalized_sample:
        return 1.0
    return SequenceMatcher(None, normalized_student, normalized_sample).ratio()


def _extract_numbers(text: str) -> list[float]:
    values: list[float] = []

    for left, right in re.findall(r"(-?\d+(?:[.,]\d+)?)\s*/\s*(-?\d+(?:[.,]\d+)?)", text):
        try:
            denominator = float(right.replace(",", "."))
            if abs(denominator) < 1e-12:
                continue
            numerator = float(left.replace(",", "."))
            values.append(numerator / denominator)
        except ValueError:
            continue

    for match in re.findall(r"-?\d+(?:[.,]\d+)?", text):
        normalized = match.replace(",", ".")
        try:
            values.append(float(normalized))
        except ValueError:
            continue
    return values


def _numeric_equivalent(student_text: str, sample_text: str) -> bool:
    student_numbers = _extract_numbers(student_text)
    sample_numbers = _extract_numbers(sample_text)
    if not student_numbers or not sample_numbers:
        return False
    if len(student_numbers) == 1 and len(sample_numbers) == 1:
        return _numbers_close(student_numbers[0], sample_numbers[0])
    if len(student_numbers) == 1 and len(sample_numbers) > 1:
        return any(_numbers_close(student_numbers[0], value) for value in sample_numbers)
    if len(sample_numbers) == 1 and len(student_numbers) > 1:
        return any(_numbers_close(value, sample_numbers[0]) for value in student_numbers)
    if len(student_numbers) == len(sample_numbers):
        return all(_numbers_close(a, b) for a, b in zip(student_numbers, sample_numbers))
    return False


def _numbers_close(left: float, right: float) -> bool:
    abs_tol = 0.02
    rel_tol = max(abs(left), abs(right)) * 0.003
    return abs(left - right) <= max(abs_tol, rel_tol)


def _answer_matches_number(student_text: str, expected: float) -> bool:
    candidates = _extract_numbers(student_text)
    return any(_numbers_close(value, expected) for value in candidates)


def _infer_expected_numeric_from_prompt(prompt: str) -> float | None:
    normalized = prompt.lower()
    if "среднее арифметическ" in normalized:
        values = _extract_numbers_after_marker(
            text=prompt,
            markers=["среднее арифметическое чисел", "среднее арифметическое", "орташа арифметикалық"],
        )
        if len(values) < 2:
            values = _extract_numbers(prompt)
        if len(values) >= 2:
            return sum(values) / len(values)
    if "периметр квадрата" in normalized and ("сторон" in normalized or "қабыр" in normalized):
        side_match = re.search(r"сторон[а-я]*\s*(-?\d+(?:[.,]\d+)?)", normalized)
        if not side_match:
            side_match = re.search(r"қабырғ[а-я]*\s*(-?\d+(?:[.,]\d+)?)", normalized)
        if side_match:
            try:
                return float(side_match.group(1).replace(",", ".")) * 4
            except ValueError:
                return None
        values = _extract_numbers(prompt)
        if values:
            return values[-1] * 4
    return None


def _extract_numbers_after_marker(*, text: str, markers: list[str]) -> list[float]:
    lowered = text.lower()
    for marker in markers:
        idx = lowered.find(marker)
        if idx < 0:
            continue
        fragment = text[idx + len(marker):]
        fragment = re.split(r"[.?!\n]", fragment, maxsplit=1)[0]
        values = _extract_numbers(fragment)
        if values:
            return values
    return []


def _discriminant_rule_score(*, prompt: str, student_text: str) -> float:
    if "дискриминант" not in prompt.lower():
        return 0.0
    text = student_text.lower().replace(" ", "")
    if not text:
        return 0.0

    neg_ok = _match_discriminant_case(text=text, case_pattern=r"d<0", root_patterns=[r"неткор", r"0кор"])
    zero_ok = _match_discriminant_case(text=text, case_pattern=r"d=0", root_patterns=[r"1кор", r"одинкор", r"біртүбір", r"біркор"])
    pos_ok = _match_discriminant_case(text=text, case_pattern=r"d>0", root_patterns=[r"2кор", r"двакор", r"екітүбір", r"екікор"])
    hits = int(neg_ok) + int(zero_ok) + int(pos_ok)
    if hits == 3:
        return 1.0
    if hits == 2:
        return 0.72
    return 0.0


def _match_discriminant_case(*, text: str, case_pattern: str, root_patterns: list[str]) -> bool:
    case_match = re.search(case_pattern, text)
    if not case_match:
        return False
    window_start = max(case_match.start() - 20, 0)
    window_end = min(case_match.end() + 45, len(text))
    window = text[window_start:window_end]
    return any(re.search(pattern, window) for pattern in root_patterns)


def _infer_formula_targets_from_prompt(prompt: str) -> list[str]:
    normalized = prompt.lower().replace(" ", "")
    targets: list[str] = []

    if re.search(r"\(?a\^m\)?\^n", normalized):
        targets.extend(["a^(mn)", "a^mn", "a^(m*n)", "a^m*n"])
    if re.search(r"a\^m[\*x×]a\^n", normalized):
        targets.extend(["a^(m+n)", "a^m+n"])
    if re.search(r"a\^m[/:]a\^n", normalized):
        targets.extend(["a^(m-n)", "a^m-n"])
    return targets


def _is_formula_answer_match(student_text: str, targets: list[str]) -> bool:
    student = _normalize_formula(student_text)
    if not student:
        return False
    normalized_targets = {_normalize_formula(item) for item in targets if item}
    return student in normalized_targets


@dataclass
class SemanticVerdict:
    score: float
    is_correct: bool


def _should_use_semantic_ai(
    *,
    question: Question,
    student_text: str,
    sample_answer: str,
    heuristic_score: float,
) -> bool:
    if not settings.deepseek_api_key:
        return False
    if not student_text.strip():
        return False
    # For free-text answers, always prefer semantic grading by AI when available.
    return True


def _evaluate_with_semantic_ai(
    *,
    question: Question,
    student_text: str,
    sample_answer: str,
    reference_text: str,
    keywords: list[str],
) -> SemanticVerdict | None:
    prompt = f"""
Оцени ответ студента в формате строгого JSON без markdown:
{{
  "score": 0.0,
  "is_correct": false,
  "reason": "краткое пояснение"
}}

Критерии:
- Оцени смысловую правильность, а не только буквальное совпадение.
- Игнорируй мелкие орфографические/пунктуационные ошибки, если смысл верный.
- Для математики считай эквивалентными записи вида a^(m+n), a^m+n, a{{m+n}}, если смысл один.
- Если эталонный ответ выглядит общим/шаблонным, опирайся на формулировку вопроса и предметные правила.
- Если ответ частично верный, ставь score между 0.3 и 0.79.
- Если ответ в целом верный по сути, is_correct=true и score >= 0.8.

Вопрос: {question.prompt}
Эталонный ответ: {sample_answer}
Контекст правильного ответа: {reference_text}
Ключевые слова: {", ".join(keywords) if keywords else "нет"}
Ответ студента: {student_text}
""".strip()

    try:
        content = llm_chat(
            system_prompt="You are an accurate educational evaluator. Return strict JSON only.",
            user_prompt=prompt,
            temperature=0.0,
            timeout_seconds=12,
        )
        parsed = _extract_json_object(content)
        score = _clamp(float(parsed.get("score", 0.0)))
        is_correct = bool(parsed.get("is_correct", False))
        return SemanticVerdict(score=score, is_correct=is_correct)
    except (LLMProviderError, Exception) as exc:  # noqa: BLE001
        logger.warning("Semantic AI grading failed, fallback to heuristic: %s", exc)
        return None


def _extract_json_object(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            raise
        return json.loads(match.group(0))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _to_int_list(values: Any) -> list[int]:
    if isinstance(values, list):
        output = []
        for value in values:
            try:
                output.append(int(value))
            except (TypeError, ValueError):
                continue
        return output
    return []
