from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.models import Question, QuestionType
from app.schemas.tests import QuestionFeedback


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

    keywords = [str(item).lower() for item in question.correct_answer_json.get("keywords", [])]
    sample_answer = str(question.correct_answer_json.get("sample_answer", ""))
    normalized_sample = _normalize(sample_answer)

    if not normalized_student:
        return 0.0, False

    keyword_hits = 0
    for keyword in keywords:
        if keyword and keyword in normalized_student:
            keyword_hits += 1

    keyword_score = (keyword_hits / len(keywords)) if keywords else 0.0
    similarity = SequenceMatcher(None, normalized_student, normalized_sample).ratio() if normalized_sample else 0.0

    score = round((keyword_score * 0.7) + (similarity * 0.3), 2)
    is_correct = score >= 0.6
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
