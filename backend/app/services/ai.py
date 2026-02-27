from __future__ import annotations

import json
import logging
import random
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.models import DifficultyLevel, PreferredLanguage, QuestionType, Subject, TestMode
from app.schemas.tests import GeneratedQuestionPayload, GeneratedTestPayload
from app.services.question_bank import _pick, get_distractors, get_text_question_templates

logger = logging.getLogger(__name__)


@dataclass
class RecommendationPayload:
    advice_text: str
    generated_tasks: list[dict]


class AIService:
    OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    LIBRARY_QUESTIONS_PER_COMBINATION = 25

    def generate_test(
        self,
        *,
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        mode: TestMode,
        num_questions: int,
        user_id: int,
        focus_topics: Sequence[str] | None = None,
        used_library_question_ids: set[str] | None = None,
    ) -> GeneratedTestPayload:
        seed = f"{int(time.time() * 1000)}-{user_id}-{subject.id}-{difficulty.value}"
        normalized_focus_topics = [str(topic).strip() for topic in (focus_topics or []) if str(topic).strip()]
        used_library_ids = set(used_library_question_ids or set())

        # First serve questions from local library (no DeepSeek calls).
        library_pool = self._generate_general_library_questions(
            subject=subject,
            difficulty=difficulty,
            language=language,
            mode=mode,
        )
        available_library_questions: list[GeneratedQuestionPayload] = []
        for item in library_pool:
            library_id = str((item.explanation_json or {}).get("library_question_id", "")).strip()
            if library_id and library_id in used_library_ids:
                continue
            available_library_questions.append(item)

        rng = random.Random(f"{seed}-library")
        selected_library = self._sample_library_questions(
            questions=available_library_questions,
            limit=num_questions,
            rng=rng,
        )
        if len(selected_library) >= num_questions:
            return GeneratedTestPayload(seed=seed, questions=selected_library)

        if selected_library:
            remaining = num_questions - len(selected_library)
            fallback_sources: list[list[GeneratedQuestionPayload]] = [list(selected_library)]

            generated = self._generate_non_library_test(
                subject=subject,
                difficulty=difficulty,
                language=language,
                mode=mode,
                num_questions=remaining,
                seed=f"{seed}-after-library",
                focus_topics=normalized_focus_topics,
            )
            fallback_sources.append(list(generated.questions))
            merged = self._merge_unique_questions(
                groups=[selected_library, generated.questions],
                target_count=num_questions,
            )
            if len(merged) < num_questions:
                extra = self._generate_non_library_test(
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    mode=mode,
                    num_questions=max(num_questions, num_questions - len(merged) + 2),
                    seed=f"{seed}-after-library-topup",
                    focus_topics=normalized_focus_topics,
                )
                fallback_sources.append(list(extra.questions))
                merged = self._merge_unique_questions(
                    groups=[merged, extra.questions],
                    target_count=num_questions,
                )
            if len(merged) < num_questions:
                merged = self._fill_questions_to_target(
                    current=merged,
                    fallback_groups=fallback_sources,
                    target_count=num_questions,
                )
            if len(merged) < num_questions:
                merged = self._top_up_unique_questions(
                    current=merged,
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    mode=mode,
                    target_count=num_questions,
                    focus_topics=normalized_focus_topics,
                    seed=f"{seed}-unique-topup",
                )
            return GeneratedTestPayload(seed=seed, questions=merged[:num_questions])

        return self._generate_non_library_test(
            subject=subject,
            difficulty=difficulty,
            language=language,
            mode=mode,
            num_questions=num_questions,
            seed=seed,
            focus_topics=normalized_focus_topics,
        )

    def generate_library_only_questions(
        self,
        *,
        subject: Subject,
        language: PreferredLanguage,
        mode: TestMode,
        num_questions: int,
        seed: str,
        difficulty_order: Sequence[DifficultyLevel] | None = None,
        used_library_question_ids: set[str] | None = None,
        used_library_content_keys: set[str] | None = None,
    ) -> list[GeneratedQuestionPayload]:
        difficulties = list(difficulty_order or [DifficultyLevel.medium, DifficultyLevel.easy, DifficultyLevel.hard])
        normalized_difficulties: list[DifficultyLevel] = []
        seen_difficulty: set[DifficultyLevel] = set()
        for item in difficulties:
            if item in seen_difficulty:
                continue
            seen_difficulty.add(item)
            normalized_difficulties.append(item)

        template_buckets: list[tuple[DifficultyLevel, list[dict[str, Any]]]] = []
        for difficulty in normalized_difficulties:
            templates = get_text_question_templates(
                subject_name_ru=subject.name_ru,
                language=language,
                difficulty=difficulty,
            )
            if templates:
                template_buckets.append((difficulty, templates))

        if not template_buckets:
            return []

        used_ids = set(used_library_question_ids or set())
        track_content_uniqueness = used_library_content_keys is not None
        used_content_keys = {
            str(value).strip().lower()
            for value in (used_library_content_keys or set())
            if str(value).strip()
        }
        rng = random.Random(seed)
        generated_candidates: list[GeneratedQuestionPayload] = []
        library_index = 0
        rounds = max(4, (num_questions // max(1, sum(len(bucket) for _, bucket in template_buckets))) + 8)

        for round_idx in range(rounds):
            round_candidates: list[GeneratedQuestionPayload] = []
            for difficulty, templates in template_buckets:
                rotated = list(templates)
                rng.shuffle(rotated)
                for template in rotated:
                    prepared = dict(template)
                    prepared_prompt = str(prepared.get("prompt", ""))
                    if round_idx > 0:
                        prepared["prompt"] = self._build_library_prompt_variant(
                            prompt=str(template.get("prompt", "")),
                            language=language,
                            variant_index=round_idx,
                            salt=library_index,
                        )
                        prepared_prompt = str(prepared.get("prompt", ""))
                    template_content_key = self._library_content_key(prepared_prompt)
                    if track_content_uniqueness and template_content_key and template_content_key in used_content_keys:
                        continue
                    question = self._build_question_from_bank_template(
                        template=prepared,
                        subject=subject,
                        difficulty=difficulty,
                        language=language,
                        rng=rng,
                    )
                    adapted = self._adapt_library_question_to_mode(
                        question=question,
                        mode=mode,
                        language=language,
                    )
                    attached = self._attach_library_metadata(
                        question=adapted,
                        subject=subject,
                        difficulty=difficulty,
                        language=language,
                        mode=mode,
                        library_index=library_index,
                        template_content_key=template_content_key or None,
                    )
                    library_index += 1
                    library_id = str((attached.explanation_json or {}).get("library_question_id", "")).strip()
                    if library_id and library_id in used_ids:
                        continue
                    content_key = str((attached.explanation_json or {}).get("library_template_key", "")).strip().lower()
                    if track_content_uniqueness and content_key and content_key in used_content_keys:
                        continue
                    if track_content_uniqueness and content_key:
                        used_content_keys.add(content_key)
                    round_candidates.append(attached)
            generated_candidates.extend(round_candidates)
            if len(generated_candidates) >= num_questions * 3:
                break

        sanitized = self._sanitize_questions(
            questions=generated_candidates,
            subject=subject,
            difficulty=normalized_difficulties[0],
            language=language,
            mode=mode,
            target_count=num_questions,
            focus_topics=[],
        )

        if len(sanitized) >= num_questions:
            return sanitized[:num_questions]

        # Final deterministic top-up from template paraphrases only (still library-based).
        fallback: list[GeneratedQuestionPayload] = list(sanitized)
        seen_unique_keys = {self._question_uniqueness_key(item) for item in fallback}
        extra_round = rounds
        while len(fallback) < num_questions and extra_round < rounds + 24:
            extra_round += 1
            for difficulty, templates in template_buckets:
                for template in templates:
                    prepared = dict(template)
                    prepared["prompt"] = self._build_library_prompt_variant(
                        prompt=str(template.get("prompt", "")),
                        language=language,
                        variant_index=extra_round,
                        salt=library_index,
                    )
                    template_content_key = self._library_content_key(str(prepared.get("prompt", "")))
                    if track_content_uniqueness and template_content_key and template_content_key in used_content_keys:
                        continue
                    question = self._build_question_from_bank_template(
                        template=prepared,
                        subject=subject,
                        difficulty=difficulty,
                        language=language,
                        rng=rng,
                    )
                    adapted = self._adapt_library_question_to_mode(
                        question=question,
                        mode=mode,
                        language=language,
                    )
                    attached = self._attach_library_metadata(
                        question=adapted,
                        subject=subject,
                        difficulty=difficulty,
                        language=language,
                        mode=mode,
                        library_index=library_index,
                        template_content_key=template_content_key or None,
                    )
                    library_index += 1
                    key = self._question_uniqueness_key(attached)
                    if key in seen_unique_keys:
                        continue
                    content_key = str((attached.explanation_json or {}).get("library_template_key", "")).strip().lower()
                    if track_content_uniqueness and content_key and content_key in used_content_keys:
                        continue
                    seen_unique_keys.add(key)
                    if track_content_uniqueness and content_key:
                        used_content_keys.add(content_key)
                    fallback.append(attached)
                    if len(fallback) >= num_questions:
                        break
                if len(fallback) >= num_questions:
                    break

        return fallback[:num_questions]

    def _sample_library_questions(
        self,
        *,
        questions: Sequence[GeneratedQuestionPayload],
        limit: int,
        rng: random.Random,
    ) -> list[GeneratedQuestionPayload]:
        if limit <= 0:
            return []

        ranked = sorted(
            questions,
            key=lambda item: (self._is_variant_prompt(item.prompt), rng.random()),
        )
        selected: list[GeneratedQuestionPayload] = []
        seen_unique_keys: set[str] = set()
        seen_base_keys: set[str] = set()
        deferred: list[GeneratedQuestionPayload] = []

        for item in ranked:
            unique_key = self._question_uniqueness_key(item)
            if unique_key in seen_unique_keys:
                continue
            base_key = str((item.explanation_json or {}).get("library_base_key", "")).strip().lower()
            if base_key:
                if base_key in seen_base_keys:
                    deferred.append(item)
                    continue
                seen_base_keys.add(base_key)
            seen_unique_keys.add(unique_key)
            selected.append(item)
            if len(selected) >= limit:
                break

        if len(selected) < limit:
            for item in deferred:
                unique_key = self._question_uniqueness_key(item)
                if unique_key in seen_unique_keys:
                    continue
                seen_unique_keys.add(unique_key)
                selected.append(item)
                if len(selected) >= limit:
                    break

        return selected

    def _merge_unique_questions(
        self,
        *,
        groups: Sequence[Sequence[GeneratedQuestionPayload]],
        target_count: int,
    ) -> list[GeneratedQuestionPayload]:
        merged: list[GeneratedQuestionPayload] = []
        seen_unique_keys: set[str] = set()
        for group in groups:
            for item in group:
                key = self._question_uniqueness_key(item)
                if key in seen_unique_keys:
                    continue
                seen_unique_keys.add(key)
                merged.append(item)
                if len(merged) >= target_count:
                    return merged
        return merged

    def _fill_questions_to_target(
        self,
        *,
        current: Sequence[GeneratedQuestionPayload],
        fallback_groups: Sequence[Sequence[GeneratedQuestionPayload]],
        target_count: int,
    ) -> list[GeneratedQuestionPayload]:
        output = list(current)
        if len(output) >= target_count:
            return output[:target_count]

        seen_unique_keys: set[str] = set()
        for item in output:
            seen_unique_keys.add(self._question_uniqueness_key(item))

        for group in fallback_groups:
            for item in group:
                unique_key = self._question_uniqueness_key(item)
                if unique_key in seen_unique_keys:
                    continue
                seen_unique_keys.add(unique_key)
                output.append(item)
                if len(output) >= target_count:
                    return output[:target_count]

        return output[:target_count]

    def _top_up_unique_questions(
        self,
        *,
        current: Sequence[GeneratedQuestionPayload],
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        mode: TestMode,
        target_count: int,
        focus_topics: Sequence[str],
        seed: str,
    ) -> list[GeneratedQuestionPayload]:
        output = list(current)
        if len(output) >= target_count:
            return output[:target_count]

        for attempt in range(4):
            needed = target_count - len(output)
            if needed <= 0:
                break
            extra = self._generate_non_library_test(
                subject=subject,
                difficulty=difficulty,
                language=language,
                mode=mode,
                num_questions=max(needed * 3, needed + 3),
                seed=f"{seed}-{attempt}",
                focus_topics=focus_topics,
            )
            output = self._merge_unique_questions(
                groups=[output, extra.questions],
                target_count=target_count,
            )

        if len(output) >= target_count:
            return output[:target_count]

        # Final fallback: synthesize unique prompts locally.
        rng = random.Random(f"{seed}-force")
        existing_unique_keys = {self._question_uniqueness_key(item) for item in output}
        forced: list[GeneratedQuestionPayload] = []
        topic_pool = self._topic_pool(subject=subject, language=language, focus_topics=focus_topics)
        max_attempts = max(80, (target_count - len(output)) * 20)

        for idx in range(max_attempts):
            if len(output) + len(forced) >= target_count:
                break
            topic = rng.choice(topic_pool)
            qtype = self._pick_question_type(difficulty=difficulty, mode=mode, rng=rng)
            candidate = self._build_question(
                index=10_000 + idx,
                subject=subject,
                topic=topic,
                qtype=qtype,
                language=language,
                mode=mode,
                difficulty=difficulty,
                rng=rng,
            )
            sanitized = self._sanitize_questions(
                questions=[candidate],
                subject=subject,
                difficulty=difficulty,
                language=language,
                mode=mode,
                target_count=1,
                focus_topics=focus_topics,
                existing_prompt_keys=existing_unique_keys,
            )
            if not sanitized:
                continue
            item = sanitized[0]
            key = self._question_uniqueness_key(item)
            if key in existing_unique_keys:
                continue
            existing_unique_keys.add(key)
            forced.append(item)

        output = self._merge_unique_questions(
            groups=[output, forced],
            target_count=target_count,
        )
        return output[:target_count]

    @staticmethod
    def _library_content_key(prompt: str) -> str:
        normalized = re.sub(r"\s+", " ", prompt.lower()).strip()
        normalized = re.sub(r"\s*\((вариант|нұсқа)\s*\d+\)\s*$", "", normalized).strip()
        return normalized

    @staticmethod
    def _is_variant_prompt(prompt: str) -> bool:
        return bool(re.search(r"\((вариант|нұсқа)\s*\d+\)\s*$", prompt.strip(), flags=re.IGNORECASE))

    def generate_recommendation(
        self,
        *,
        subject: Subject,
        language: PreferredLanguage,
        weak_topics: Sequence[str],
    ) -> RecommendationPayload:
        if settings.ai_provider.lower() == "deepseek" and settings.deepseek_api_key:
            try:
                return self._generate_recommendation_deepseek(
                    subject=subject,
                    language=language,
                    weak_topics=list(weak_topics),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("DeepSeek recommendation failed, fallback to mock: %s", exc)

        return self._generate_recommendation_mock(
            subject=subject,
            language=language,
            weak_topics=list(weak_topics),
        )

    def _generate_non_library_test(
        self,
        *,
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        mode: TestMode,
        num_questions: int,
        seed: str,
        focus_topics: Sequence[str],
    ) -> GeneratedTestPayload:
        if settings.ai_provider.lower() == "deepseek" and settings.deepseek_api_key:
            try:
                return self._generate_test_deepseek(
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    mode=mode,
                    num_questions=num_questions,
                    seed=seed,
                    focus_topics=focus_topics,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("DeepSeek generation failed, fallback to validated library: %s", exc)

        fallback_questions = self.generate_library_only_questions(
            subject=subject,
            language=language,
            mode=mode,
            num_questions=num_questions,
            seed=f"{seed}-library-fallback",
            difficulty_order=[difficulty, DifficultyLevel.medium, DifficultyLevel.easy, DifficultyLevel.hard],
        )
        if len(fallback_questions) >= num_questions:
            return GeneratedTestPayload(seed=seed, questions=fallback_questions[:num_questions])

        # Library-only fallback should still produce a non-empty test when templates exist.
        if fallback_questions:
            return GeneratedTestPayload(seed=seed, questions=fallback_questions)

        # Final safety net for unknown subjects.
        return self._generate_test_mock(
            subject=subject,
            difficulty=difficulty,
            language=language,
            mode=mode,
            num_questions=num_questions,
            seed=seed,
            focus_topics=focus_topics,
        )

    def _generate_test_deepseek(
        self,
        *,
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        mode: TestMode,
        num_questions: int,
        seed: str,
        focus_topics: Sequence[str],
    ) -> GeneratedTestPayload:
        subject_name = subject.name_ru if language == PreferredLanguage.ru else subject.name_kz
        language_label = "русском" if language == PreferredLanguage.ru else "казахском"
        option_count = self._choice_option_count(difficulty)
        allowed_types = self._allowed_question_types(mode)
        allowed_types_text = "|".join(item.value for item in allowed_types)
        required_short_text_count = max(1, num_questions // 4) if mode == TestMode.text and difficulty == DifficultyLevel.hard else 0
        focus_topics_text = ", ".join(focus_topics[:5]) if focus_topics else "нет явного фокуса"

        mode_hint = {
            TestMode.text: "Обычный текстовый тест. Используй только single_choice, multi_choice и short_text.",
            TestMode.audio: "Добавь tts_text для каждого вопроса.",
            TestMode.oral: "Сфокусируйся на oral_answer и short_text, ожидается spoken_answer_text.",
        }[mode]
        difficulty_rules = {
            DifficultyLevel.easy: "Базовые факты и простые определения, без ловушек. Преобладают тестовые вопросы.",
            DifficultyLevel.medium: "Комбинированные задачи, умеренные отвлекающие варианты, часть вопросов с кратким ответом.",
            DifficultyLevel.hard: "Глубокие причинно-следственные вопросы, анализ и интерпретация, заметная доля открытых ответов.",
        }[difficulty]
        hard_free_rule = (
            f"- Для hard/text добавь минимум {required_short_text_count} вопросов типа short_text."
            if required_short_text_count
            else ""
        )

        prompt = f"""
Сгенерируй JSON без markdown для теста.
Предмет: {subject_name}
Язык: {language_label}
Сложность: {difficulty.value}
Правила сложности: {difficulty_rules}
Режим: {mode.value}. {mode_hint}
Количество вопросов: {num_questions}
Seed уникальности: {seed}
Фокус по прошлым ошибкам студента: {focus_topics_text}

Формат JSON:
{{
  "questions": [
    {{
      "type": "{allowed_types_text}",
      "prompt": "...",
      "options_json": {{"options": [{{"id": 0, "text": "A. ..."}}]}} или null,
      "correct_answer_json": {{...}},
      "explanation_json": {{"topic": "...", "correct_explanation": "..."}},
      "tts_text": "... или null"
    }}
  ]
}}

Условия:
- Все тексты только на выбранном языке.
- Для single_choice/multi_choice используй correct_option_ids.
- Для всех single_choice/multi_choice сделай ровно {option_count} вариантов ответа с id от 0 до {option_count - 1}.
- Для вариантов ответа используй формат A., B., C. и т.д. ({option_count} вариантов).
- Для short_text/oral_answer используй keywords и sample_answer.
- Для matching используй matches словарь left->right.
- Для oral_answer в correct_answer_json добавь expected_field="spoken_answer_text".
- Верни ровно {num_questions} вопросов.
{hard_free_rule}
""".strip()

        content = self._call_deepseek(prompt)
        data = self._extract_json(content)
        raw_questions = data.get("questions", [])
        parsed_questions: list[GeneratedQuestionPayload] = []
        for item in raw_questions:
            try:
                parsed_questions.append(GeneratedQuestionPayload.model_validate(item))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping malformed AI question payload: %s", exc)

        sanitized_questions = self._sanitize_questions(
            questions=parsed_questions,
            subject=subject,
            difficulty=difficulty,
            language=language,
            mode=mode,
            target_count=num_questions,
            focus_topics=focus_topics,
        )

        if len(sanitized_questions) < num_questions:
            fallback_needed = num_questions - len(sanitized_questions)
            fallback = self._generate_test_mock(
                subject=subject,
                difficulty=difficulty,
                language=language,
                mode=mode,
                num_questions=fallback_needed + 2,
                seed=f"{seed}-fallback",
                focus_topics=focus_topics,
            )
            prompt_keys = {self._question_uniqueness_key(item) for item in sanitized_questions}
            sanitized_questions.extend(
                self._sanitize_questions(
                    questions=fallback.questions,
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    mode=mode,
                    target_count=fallback_needed,
                    focus_topics=focus_topics,
                    existing_prompt_keys=prompt_keys,
                )
            )

        if len(sanitized_questions) < num_questions:
            raise ValueError("Не удалось подготовить достаточное количество корректных вопросов для теста")

        return GeneratedTestPayload(seed=seed, questions=sanitized_questions[:num_questions])

    def _generate_recommendation_deepseek(
        self,
        *,
        subject: Subject,
        language: PreferredLanguage,
        weak_topics: list[str],
    ) -> RecommendationPayload:
        subject_name = subject.name_ru if language == PreferredLanguage.ru else subject.name_kz
        prompt = f"""
Верни JSON без markdown:
{{
  "advice_text": "...",
  "generated_tasks": [
    {{"topic": "...", "task": "...", "difficulty": "..."}}
  ]
}}

Требования:
- Предмет: {subject_name}
- Слабые темы: {", ".join(weak_topics)}
- Язык: {language.value}
- Дай краткий совет и ровно 5 дополнительных заданий по слабым темам.
""".strip()

        content = self._call_deepseek(prompt)
        data = self._extract_json(content)
        tasks = data.get("generated_tasks", [])[:5]
        if len(tasks) < 5:
            raise ValueError("Недостаточно сгенерированных заданий")
        return RecommendationPayload(advice_text=data.get("advice_text", ""), generated_tasks=tasks)

    def _call_deepseek(self, prompt: str) -> str:
        endpoint = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": "You are a strict JSON generator for exam platforms."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.9,
        }

        with httpx.Client(timeout=30) as client:
            response = client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _extract_json(content: str) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", content)
            if not match:
                raise
            return json.loads(match.group(0))

    def _generate_test_mock(
        self,
        *,
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        mode: TestMode,
        num_questions: int,
        seed: str,
        focus_topics: Sequence[str],
    ) -> GeneratedTestPayload:
        rng = random.Random(seed)
        questions: list[GeneratedQuestionPayload] = []
        base_text_templates: list[dict[str, Any]] = get_text_question_templates(
            subject_name_ru=subject.name_ru,
            language=language,
            difficulty=difficulty,
        )
        if base_text_templates:
            seed_questions = self._generate_text_questions_from_bank(
                subject=subject,
                difficulty=difficulty,
                language=language,
                num_questions=num_questions,
                focus_topics=focus_topics,
                templates=base_text_templates,
                rng=rng,
            )
            if mode == TestMode.text:
                questions.extend(seed_questions)
            else:
                questions.extend(
                    self._adapt_library_question_to_mode(
                        question=item,
                        mode=mode,
                        language=language,
                    )
                    for item in seed_questions
                )

        remaining = max(0, num_questions - len(questions))
        is_math_subject = subject.name_ru.strip().lower() == "математика"

        if mode == TestMode.text and remaining > 0 and is_math_subject:
            questions.extend(
                self._generate_math_text_extra_questions(
                    difficulty=difficulty,
                    language=language,
                    count=remaining,
                    rng=rng,
                )
            )
            remaining = max(0, num_questions - len(questions))

        if remaining > 0 and base_text_templates:
            variant_questions = self._generate_text_template_variants(
                templates=base_text_templates,
                subject=subject,
                difficulty=difficulty,
                language=language,
                count=remaining,
                rng=rng,
                variant_offset=rng.randint(1, 9999),
            )
            if mode == TestMode.text:
                questions.extend(variant_questions)
            else:
                questions.extend(
                    self._adapt_library_question_to_mode(
                        question=item,
                        mode=mode,
                        language=language,
                    )
                    for item in variant_questions
                )
            remaining = max(0, num_questions - len(questions))

        if remaining and mode != TestMode.text:
            topics = self._topic_pool(subject=subject, language=language, focus_topics=focus_topics)
            for offset in range(remaining):
                index = len(questions) + offset
                topic = rng.choice(topics)
                qtype = self._pick_question_type(difficulty=difficulty, mode=mode, rng=rng)
                question = self._build_question(
                    index=index,
                    subject=subject,
                    topic=topic,
                    qtype=qtype,
                    language=language,
                    mode=mode,
                    difficulty=difficulty,
                    rng=rng,
                )
                questions.append(question)
        elif remaining and mode == TestMode.text and not base_text_templates:
            topics = self._topic_pool(subject=subject, language=language, focus_topics=focus_topics)
            for offset in range(remaining):
                index = len(questions) + offset
                topic = rng.choice(topics)
                qtype = self._pick_question_type(difficulty=difficulty, mode=mode, rng=rng)
                questions.append(
                    self._build_question(
                        index=index,
                        subject=subject,
                        topic=topic,
                        qtype=qtype,
                        language=language,
                        mode=mode,
                        difficulty=difficulty,
                        rng=rng,
                    )
                )

        normalized_questions = self._sanitize_questions(
            questions=questions,
            subject=subject,
            difficulty=difficulty,
            language=language,
            mode=mode,
            target_count=num_questions,
            focus_topics=focus_topics,
        )

        if len(normalized_questions) < num_questions:
            normalized_questions = self._top_up_mock_questions(
                existing_questions=normalized_questions,
                subject=subject,
                difficulty=difficulty,
                language=language,
                mode=mode,
                target_count=num_questions,
                focus_topics=focus_topics,
                base_text_templates=base_text_templates,
                is_math_subject=is_math_subject,
                rng=rng,
            )

        return GeneratedTestPayload(seed=seed, questions=normalized_questions[:num_questions])

    def _top_up_mock_questions(
        self,
        *,
        existing_questions: list[GeneratedQuestionPayload],
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        mode: TestMode,
        target_count: int,
        focus_topics: Sequence[str],
        base_text_templates: Sequence[dict[str, Any]],
        is_math_subject: bool,
        rng: random.Random,
    ) -> list[GeneratedQuestionPayload]:
        output = list(existing_questions)
        unique_keys = {self._question_uniqueness_key(item) for item in output}
        variant_offset = 100

        for attempt in range(8):
            if len(output) >= target_count:
                break

            needed = target_count - len(output)
            extra_candidates: list[GeneratedQuestionPayload] = []

            if mode == TestMode.text and is_math_subject:
                extra_candidates.extend(
                    self._generate_math_text_extra_questions(
                        difficulty=difficulty,
                        language=language,
                        count=needed + 3,
                        rng=rng,
                    )
                )

            if base_text_templates:
                extra_variants = self._generate_text_template_variants(
                    templates=base_text_templates,
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    count=needed + 3,
                    rng=rng,
                    variant_offset=variant_offset,
                )
                if mode == TestMode.text:
                    extra_candidates.extend(extra_variants)
                else:
                    extra_candidates.extend(
                        self._adapt_library_question_to_mode(
                            question=item,
                            mode=mode,
                            language=language,
                        )
                        for item in extra_variants
                    )
                variant_offset += needed + 3

            if len(extra_candidates) < needed + 2:
                topics = self._topic_pool(subject=subject, language=language, focus_topics=focus_topics)
                for offset in range(needed + 2):
                    index = len(output) + attempt + offset
                    topic = rng.choice(topics)
                    qtype = self._pick_question_type(difficulty=difficulty, mode=mode, rng=rng)
                    extra_candidates.append(
                        self._build_question(
                            index=index,
                            subject=subject,
                            topic=topic,
                            qtype=qtype,
                            language=language,
                            mode=mode,
                            difficulty=difficulty,
                            rng=rng,
                        )
                    )

            sanitized_extra = self._sanitize_questions(
                questions=extra_candidates,
                subject=subject,
                difficulty=difficulty,
                language=language,
                mode=mode,
                target_count=needed,
                focus_topics=focus_topics,
                existing_prompt_keys=unique_keys,
            )
            if not sanitized_extra:
                continue

            output.extend(sanitized_extra)
            for question in sanitized_extra:
                unique_keys.add(self._question_uniqueness_key(question))

        if len(output) < target_count:
            logger.warning(
                "Mock generation returned %s/%s questions for subject=%s difficulty=%s mode=%s",
                len(output),
                target_count,
                subject.name_ru,
                difficulty.value,
                mode.value,
            )
        return output

    def _generate_text_questions_from_bank(
        self,
        *,
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        num_questions: int,
        focus_topics: Sequence[str],
        templates: list[dict[str, Any]] | None,
        rng: random.Random,
    ) -> list[GeneratedQuestionPayload]:
        templates = templates or get_text_question_templates(
            subject_name_ru=subject.name_ru,
            language=language,
            difficulty=difficulty,
        )
        if not templates:
            return []

        focus_values = [value.lower() for value in focus_topics if value]
        ranked: list[tuple[int, dict[str, Any]]] = []
        for template in templates:
            haystack = f"{template.get('topic', '')} {template.get('prompt', '')}".lower()
            score = 0
            for item in focus_values:
                if item and item in haystack:
                    score += 1
            ranked.append((score, template))

        ranked.sort(key=lambda pair: pair[0], reverse=True)
        grouped = [item for _, item in ranked]
        if len(grouped) > 1:
            top_score = ranked[0][0]
            top_items = [item for score, item in ranked if score == top_score]
            other_items = [item for score, item in ranked if score != top_score]
            rng.shuffle(top_items)
            rng.shuffle(other_items)
            grouped = [*top_items, *other_items]

        selected = grouped[: min(num_questions, len(grouped))]
        return [
            self._build_question_from_bank_template(
                template={
                    **template,
                    "template_content_key": self._library_content_key(str(template.get("prompt", ""))),
                },
                subject=subject,
                difficulty=difficulty,
                language=language,
                rng=rng,
            )
            for template in selected
        ]

    def _generate_text_template_variants(
        self,
        *,
        templates: Sequence[dict[str, Any]],
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        count: int,
        rng: random.Random,
        variant_offset: int = 0,
    ) -> list[GeneratedQuestionPayload]:
        if not templates or count <= 0:
            return []

        variants: list[GeneratedQuestionPayload] = []
        rotation = list(templates)
        rng.shuffle(rotation)

        for index in range(count):
            base = dict(rotation[index % len(rotation)])
            base_prompt = str(base.get("prompt", "")).strip()
            variant_prompt = self._variant_prompt(
                base_prompt,
                language=language,
                variant_index=variant_offset + index + 1,
            )
            base["prompt"] = variant_prompt
            base["template_content_key"] = self._library_content_key(variant_prompt)
            variants.append(
                self._build_question_from_bank_template(
                    template=base,
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    rng=rng,
                )
            )
        return variants

    def _generate_math_text_extra_questions(
        self,
        *,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        count: int,
        rng: random.Random,
    ) -> list[GeneratedQuestionPayload]:
        if count <= 0:
            return []

        subject = Subject(id=0, name_ru="Математика", name_kz="Математика")
        results: list[GeneratedQuestionPayload] = []
        seen_prompts: set[str] = set()
        patterns = [
            self._math_template_discriminant_value,
            self._math_template_roots_count,
            self._math_template_linear_equation,
            self._math_template_percentage_problem,
            self._math_template_short_text_quadratic_roots,
        ]

        if difficulty == DifficultyLevel.easy:
            weighted = [patterns[0], patterns[2], patterns[3]]
        elif difficulty == DifficultyLevel.medium:
            weighted = [patterns[0], patterns[1], patterns[2], patterns[3], patterns[4]]
        else:
            weighted = [patterns[0], patterns[1], patterns[3], patterns[4], patterns[4]]

        attempts = 0
        max_attempts = max(20, count * 10)
        while len(results) < count and attempts < max_attempts:
            attempts += 1
            template = rng.choice(weighted)(language=language, rng=rng)
            question = self._build_question_from_bank_template(
                template=template,
                subject=subject,
                difficulty=difficulty,
                language=language,
                rng=rng,
            )
            prompt_key = self._prompt_key(question.prompt)
            if prompt_key in seen_prompts:
                continue
            seen_prompts.add(prompt_key)
            results.append(question)

        if len(results) < count:
            fallback_count = count - len(results)
            results.extend(
                self._generate_text_template_variants(
                    templates=get_text_question_templates(
                        subject_name_ru="Математика",
                        language=language,
                        difficulty=difficulty,
                    ),
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    count=fallback_count,
                    rng=rng,
                    variant_offset=200,
                )
            )
        return results

    @staticmethod
    def _variant_prompt(prompt: str, *, language: PreferredLanguage, variant_index: int) -> str:
        base = prompt.strip()
        if not base or variant_index <= 0:
            return base

        if language == PreferredLanguage.ru:
            prefixes = [
                "Выберите правильный ответ:",
                "Укажите верный вариант:",
                "Какой ответ правильный?",
                "Определите корректный вариант:",
                "Найдите правильный ответ:",
                "Выберите наиболее точный ответ:",
                "Какой вариант соответствует условию?",
                "Укажите точный ответ:",
            ]
        else:
            prefixes = [
                "Дұрыс жауапты таңдаңыз:",
                "Дұрыс нұсқаны көрсетіңіз:",
                "Қай жауап дұрыс?",
                "Дұрыс нұсқаны анықтаңыз:",
                "Дұрыс жауапты табыңыз:",
                "Ең дәл жауапты таңдаңыз:",
                "Қай нұсқа шартқа сәйкес?",
                "Нақты дұрыс жауапты көрсетіңіз:",
            ]

        prefix = prefixes[variant_index % len(prefixes)]
        if base.lower().startswith(prefix.lower()):
            return base
        return f"{prefix} {base}".strip()

    @staticmethod
    def _build_library_prompt_variant(
        *,
        prompt: str,
        language: PreferredLanguage,
        variant_index: int,
        salt: int = 0,
    ) -> str:
        base = prompt.strip()
        if not base:
            return base
        if variant_index <= 0:
            return base
        return AIService._variant_prompt(
            base,
            language=language,
            variant_index=variant_index + max(0, salt),
        )

    @staticmethod
    def _format_quadratic(a: int, b: int, c: int) -> str:
        b_part = f"+ {abs(b)}x" if b >= 0 else f"- {abs(b)}x"
        c_part = f"+ {abs(c)}" if c >= 0 else f"- {abs(c)}"
        return f"{a}x^2 {b_part} {c_part} = 0"

    @staticmethod
    def _format_linear(a: int, b: int, c: int) -> str:
        b_part = f"+ {abs(b)}" if b >= 0 else f"- {abs(b)}"
        return f"{a}x {b_part} = {c}"

    def _math_template_discriminant_value(self, *, language: PreferredLanguage, rng: random.Random) -> dict[str, Any]:
        a = rng.randint(1, 5)
        b = rng.randint(-10, 10)
        if b == 0:
            b = 6
        c = rng.randint(-12, 12)
        if c == 0:
            c = 3
        d = b * b - 4 * a * c
        prompt_ru = f"Найдите дискриминант уравнения {self._format_quadratic(a, b, c)}."
        prompt_kz = f"{self._format_quadratic(a, b, c)} теңдеуінің дискриминантын табыңыз."
        options = [str(d), str(d + 4), str(d - 4), str(-d if d != 0 else d + 8)]
        return {
            "type": "single_choice",
            "topic": "Квадратные уравнения" if language == PreferredLanguage.ru else "Квадрат теңдеулер",
            "prompt": _pick(language, ru=prompt_ru, kz=prompt_kz),
            "options": options,
            "correct_option_ids": [0],
            "explanation": _pick(
                language,
                ru=f"По формуле D = b^2 - 4ac: D = {b}^2 - 4*{a}*{c} = {d}.",
                kz=f"D = b^2 - 4ac формуласы бойынша: D = {b}^2 - 4*{a}*{c} = {d}.",
            ),
        }

    def _math_template_roots_count(self, *, language: PreferredLanguage, rng: random.Random) -> dict[str, Any]:
        cases = [
            (1, -5, 6),   # D > 0
            (1, -4, 4),   # D = 0
            (1, 2, 5),    # D < 0
        ]
        a, b, c = rng.choice(cases)
        d = b * b - 4 * a * c
        correct = 0 if d > 0 else (1 if d == 0 else 2)
        options_ru = ["Два действительных корня", "Один действительный корень", "Нет действительных корней", "Бесконечно много корней"]
        options_kz = ["Екі нақты түбір", "Бір нақты түбір", "Нақты түбір жоқ", "Шексіз көп түбір"]
        return {
            "type": "single_choice",
            "topic": "Квадратные уравнения" if language == PreferredLanguage.ru else "Квадрат теңдеулер",
            "prompt": _pick(
                language,
                ru=f"Сколько действительных корней имеет уравнение {self._format_quadratic(a, b, c)}?",
                kz=f"{self._format_quadratic(a, b, c)} теңдеуінің неше нақты түбірі бар?",
            ),
            "options": _pick(language, ru=options_ru, kz=options_kz),
            "correct_option_ids": [correct],
            "explanation": _pick(
                language,
                ru=f"D = {d}. При D>0 два корня, при D=0 один, при D<0 действительных корней нет.",
                kz=f"D = {d}. D>0 болса екі түбір, D=0 болса бір түбір, D<0 болса нақты түбір жоқ.",
            ),
        }

    def _math_template_linear_equation(self, *, language: PreferredLanguage, rng: random.Random) -> dict[str, Any]:
        a = rng.randint(2, 9)
        x = rng.randint(-8, 12)
        b = rng.randint(-12, 12)
        c = a * x + b
        prompt_ru = f"Решите уравнение: {self._format_linear(a, b, c)}"
        prompt_kz = f"Теңдеуді шешіңіз: {self._format_linear(a, b, c)}"
        distractors = [x + 1, x - 1, -x if x != 0 else x + 2]
        options = [str(x), *[str(value) for value in distractors]]
        return {
            "type": "single_choice",
            "topic": "Линейные уравнения" if language == PreferredLanguage.ru else "Сызықтық теңдеулер",
            "prompt": _pick(language, ru=prompt_ru, kz=prompt_kz),
            "options": options,
            "correct_option_ids": [0],
            "explanation": _pick(
                language,
                ru=f"Переносим {b} и делим на {a}: x = {x}.",
                kz=f"{b} санын тасымалдап, {a} санына бөлеміз: x = {x}.",
            ),
        }

    def _math_template_percentage_problem(self, *, language: PreferredLanguage, rng: random.Random) -> dict[str, Any]:
        base = rng.choice([120, 150, 200, 240, 300, 360, 450])
        percent = rng.choice([10, 15, 20, 25, 30])
        new_price = int(base * (100 + percent) / 100)
        prompt_ru = f"Товар стоил {base} и подорожал на {percent}%. Какая новая цена?"
        prompt_kz = f"Тауар бағасы {base} болып, {percent}% өсті. Жаңа баға қанша?"
        wrong_candidates = [
            base,
            int(base * (100 + percent // 2) / 100),
            int(base * (100 + percent + 10) / 100),
            int(base * (100 - percent) / 100),
            new_price + max(5, base // 20),
            max(1, new_price - max(5, base // 20)),
        ]
        unique_wrong: list[int] = []
        seen_wrong: set[int] = set()
        for value in wrong_candidates:
            if value == new_price or value in seen_wrong:
                continue
            seen_wrong.add(value)
            unique_wrong.append(value)
            if len(unique_wrong) >= 3:
                break
        while len(unique_wrong) < 3:
            candidate = new_price + (len(unique_wrong) + 1) * 7
            if candidate == new_price or candidate in seen_wrong:
                candidate += 3
            seen_wrong.add(candidate)
            unique_wrong.append(candidate)
        options = [str(new_price), *[str(value) for value in unique_wrong[:3]]]
        return {
            "type": "single_choice",
            "topic": "Проценты" if language == PreferredLanguage.ru else "Пайыз",
            "prompt": _pick(language, ru=prompt_ru, kz=prompt_kz),
            "options": options,
            "correct_option_ids": [0],
            "explanation": _pick(
                language,
                ru=f"{percent}% от {base} = {int(base * percent / 100)}. Итого {new_price}.",
                kz=f"{base} санының {percent}% = {int(base * percent / 100)}. Нәтиже {new_price}.",
            ),
        }

    def _math_template_short_text_quadratic_roots(self, *, language: PreferredLanguage, rng: random.Random) -> dict[str, Any]:
        r1 = rng.choice([1, 2, 3, 4, 5, 6, -1, -2])
        r2 = rng.choice([2, 3, 4, 5, 6, 7, -3, -4])
        while r2 == r1:
            r2 = rng.choice([2, 3, 4, 5, 6, 7, -3, -4])
        b = -(r1 + r2)
        c = r1 * r2
        equation = self._format_quadratic(1, b, c)
        return {
            "type": "short_text",
            "topic": "Квадратные уравнения" if language == PreferredLanguage.ru else "Квадрат теңдеулер",
            "prompt": _pick(
                language,
                ru=f"Решите уравнение {equation} и укажите оба корня.",
                kz=f"{equation} теңдеуін шешіп, екі түбірін жазыңыз.",
            ),
            "keywords": [str(r1), str(r2)],
            "sample_answer": _pick(
                language,
                ru=f"Корни уравнения: x1 = {r1}, x2 = {r2}.",
                kz=f"Түбірлері: x1 = {r1}, x2 = {r2}.",
            ),
            "explanation": _pick(
                language,
                ru="Используйте разложение на множители или формулу дискриминанта.",
                kz="Көбейткіштерге жіктеу немесе дискриминант формуласын қолданыңыз.",
            ),
        }

    def _build_question_from_bank_template(
        self,
        *,
        template: dict[str, Any],
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        rng: random.Random,
    ) -> GeneratedQuestionPayload:
        topic = str(template.get("topic", "")).strip() or (
            "Базовая тема" if language == PreferredLanguage.ru else "Негізгі тақырып"
        )
        prompt = str(template.get("prompt", "")).strip()
        explanation = str(template.get("explanation", "")).strip() or self._build_default_explanation(topic=topic, language=language)
        template_content_key = str(template.get("template_content_key", "")).strip().lower()
        base_prompt_key = str(template.get("base_prompt_key", "")).strip().lower()
        explanation_payload: dict[str, Any] = {"topic": topic, "correct_explanation": explanation}
        if template_content_key:
            explanation_payload["library_template_key"] = template_content_key
        if base_prompt_key:
            explanation_payload["library_base_key"] = base_prompt_key

        template_type = str(template.get("type", "single_choice")).strip()
        if template_type == QuestionType.short_text.value:
            keywords = [str(item).strip().lower() for item in (template.get("keywords") or []) if str(item).strip()]
            if not keywords:
                keywords = self._extract_keywords(topic=topic, language=language, source_keywords=[])
            sample_answer = str(template.get("sample_answer", "")).strip()
            if not sample_answer:
                sample_answer = (
                    f"По теме «{topic}» важно указать определение и практический пример."
                    if language == PreferredLanguage.ru
                    else f"«{topic}» тақырыбы бойынша анықтама мен практикалық мысалды көрсету керек."
                )
            return GeneratedQuestionPayload(
                type=QuestionType.short_text,
                prompt=prompt,
                options_json=None,
                correct_answer_json={"keywords": keywords, "sample_answer": sample_answer},
                explanation_json=explanation_payload,
                tts_text=None,
            )

        option_count = self._choice_option_count(difficulty)
        options = [str(item).strip() for item in (template.get("options") or []) if str(item).strip()]
        correct_option_ids = [int(item) for item in (template.get("correct_option_ids") or [])]
        if not options:
            return self._make_short_text_question(
                prompt=prompt,
                topic=topic,
                explanation_json=explanation_payload,
                language=language,
                source_correct_answer_json={
                    "keywords": [str(item).strip() for item in (template.get("keywords") or []) if str(item).strip()],
                    "sample_answer": str(template.get("sample_answer", "")).strip(),
                },
            )

        options, correct_option_ids = self._expand_and_shuffle_options_from_template(
            subject=subject,
            language=language,
            difficulty=difficulty,
            topic=topic,
            options=options,
            correct_option_ids=correct_option_ids,
            rng=rng,
        )
        if len(options) < 2:
            return self._make_short_text_question(
                prompt=prompt,
                topic=topic,
                explanation_json=explanation_payload,
                language=language,
                source_correct_answer_json={
                    "keywords": [str(item).strip() for item in (template.get("keywords") or []) if str(item).strip()],
                    "sample_answer": str(template.get("sample_answer", "")).strip(),
                },
            )

        correct_option_ids = [
            int(item)
            for item in correct_option_ids
            if isinstance(item, int) and 0 <= int(item) < len(options)
        ]
        if not correct_option_ids:
            correct_option_ids = [0]
        question_type = QuestionType.multi_choice if len(correct_option_ids) > 1 else QuestionType.single_choice
        return GeneratedQuestionPayload(
            type=question_type,
            prompt=prompt,
            options_json={"options": [{"id": idx, "text": text} for idx, text in enumerate(options)]},
            correct_answer_json={"correct_option_ids": correct_option_ids},
            explanation_json=explanation_payload,
            tts_text=None,
        )

    def _expand_and_shuffle_options_from_template(
        self,
        *,
        subject: Subject,
        language: PreferredLanguage,
        difficulty: DifficultyLevel,
        topic: str,
        options: list[str],
        correct_option_ids: list[int],
        rng: random.Random,
    ) -> tuple[list[str], list[int]]:
        option_count = self._choice_option_count(difficulty)
        safe_options = [value for value in options if value]
        if not safe_options:
            return [], []

        safe_correct_ids = [value for value in correct_option_ids if 0 <= value < len(safe_options)]
        if not safe_correct_ids:
            safe_correct_ids = [0]

        subject_distractors = get_distractors(subject_name_ru=subject.name_ru, language=language)
        topic_tokens = {
            token
            for token in re.findall(r"[a-zA-Zа-яА-ЯәіңғүұқөһӘІҢҒҮҰҚӨҺ0-9]+", topic.lower())
            if len(token) >= 4
        }
        topic_matched_distractors = [
            item for item in subject_distractors
            if any(token in item.lower() for token in topic_tokens)
        ]
        distractor_pool = [
            *self._contextual_distractors_from_options(
                options=safe_options,
                language=language,
                needed=option_count * 2,
                rng=rng,
            ),
            *topic_matched_distractors,
        ]
        seen = {item.lower() for item in safe_options}
        for distractor in distractor_pool:
            if len(safe_options) >= option_count:
                break
            key = str(distractor).strip().lower()
            if not key or key in seen:
                continue
            safe_options.append(str(distractor).strip())
            seen.add(key)

        min_required_options = min(4, option_count)
        if len(safe_options) < min_required_options:
            return safe_options, safe_correct_ids

        if len(safe_options) > option_count:
            mandatory_ids = sorted(set(safe_correct_ids))
            other_ids = [idx for idx in range(len(safe_options)) if idx not in mandatory_ids]
            rng.shuffle(other_ids)
            selected_ids = mandatory_ids + other_ids[: max(0, option_count - len(mandatory_ids))]
            selected_ids = sorted(set(selected_ids))[:option_count]
            remap = {old_idx: new_idx for new_idx, old_idx in enumerate(selected_ids)}
            safe_options = [safe_options[idx] for idx in selected_ids]
            safe_correct_ids = [remap[idx] for idx in mandatory_ids if idx in remap]

        option_items = list(enumerate(safe_options))
        rng.shuffle(option_items)
        options_out = []
        id_map: dict[int, int] = {}
        for new_id, (old_id, text) in enumerate(option_items[:option_count]):
            options_out.append(text)
            id_map[old_id] = new_id

        correct_out = [id_map[idx] for idx in safe_correct_ids if idx in id_map]
        if not correct_out:
            correct_out = [0]
        return options_out, sorted(set(correct_out))

    def _contextual_distractors_from_options(
        self,
        *,
        options: Sequence[str],
        language: PreferredLanguage,
        needed: int,
        rng: random.Random,
    ) -> list[str]:
        pool: list[str] = []
        source = [str(item).strip() for item in options if str(item).strip()]
        if not source:
            return pool

        def add(candidate: str) -> None:
            value = candidate.strip()
            if not value:
                return
            key = value.lower()
            if key in {item.lower() for item in source}:
                return
            if key in {item.lower() for item in pool}:
                return
            pool.append(value)

        for item in source:
            if "=" in item:
                left, right = item.split("=", 1)
                left = left.strip()
                right = right.strip()
                if "-" in right:
                    add(f"{left} = {right.replace('-', '+', 1)}")
                if "+" in right:
                    add(f"{left} = {right.replace('+', '-', 1)}")
                if "4ac" in right:
                    add(f"{left} = {right.replace('4ac', '2ac')}")
                    add(f"{left} = {right.replace('4ac', '8ac')}")
                if "^2" in right:
                    add(f"{left} = {right.replace('^2', '')}")
                    add(f"{left} = ({right})^2")

        for item in source:
            sentence = item
            if len(sentence) < 12:
                continue
            if "не имеет" in sentence:
                add(sentence.replace("не имеет", "имеет"))
            if "имеет два различных действительных корня" in sentence:
                add(sentence.replace("имеет два различных действительных корня", "имеет один действительный корень"))
            elif "имеет два различных корня" in sentence:
                add(sentence.replace("имеет два различных корня", "имеет один корень"))
            elif "имеет два" in sentence:
                add(sentence.replace("имеет два", "имеет один"))
            if "имеет один действительный корень" in sentence:
                add(sentence.replace("имеет один действительный корень", "имеет два действительных корня"))
            elif "имеет один корень" in sentence:
                add(sentence.replace("имеет один корень", "имеет два корня"))
            if "D > 0" in sentence:
                add(sentence.replace("D > 0", "D < 0"))
                add(sentence.replace("D > 0", "D = 0"))
            if "D < 0" in sentence:
                add(sentence.replace("D < 0", "D > 0"))
                add(sentence.replace("D < 0", "D = 0"))
            if "D = 0" in sentence:
                add(sentence.replace("D = 0", "D > 0"))
                add(sentence.replace("D = 0", "D < 0"))
            if "действительных корней нет" in sentence:
                add(sentence.replace("действительных корней нет", "есть два действительных корня"))
            if "нақты түбір жоқ" in sentence:
                add(sentence.replace("нақты түбір жоқ", "екі нақты түбір бар"))

        numeric_values: list[tuple[float, str]] = []
        for item in source:
            match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*([%°]?)\s*", item)
            if not match:
                continue
            numeric_values.append((float(match.group(1)), match.group(2)))

        if numeric_values:
            suffix = numeric_values[0][1]
            base_values = [value for value, _ in numeric_values]
            is_integer_series = all(float(value).is_integer() for value in base_values)

            if is_integer_series:
                int_values = [int(value) for value in base_values]
                span = max(int_values) - min(int_values)
                if span <= 20:
                    step = 1
                elif span <= 80:
                    step = 5
                else:
                    step = 10
                deltas = [-4, -3, -2, -1, 1, 2, 3, 4, 5, -5]
                rng.shuffle(deltas)
                anchors = int_values[:]
                rng.shuffle(anchors)
                for anchor in anchors:
                    for delta in deltas:
                        candidate = anchor + delta * step
                        add(f"{candidate}{suffix}")
                        if len(pool) >= needed:
                            break
                    if len(pool) >= needed:
                        break
            else:
                average = sum(base_values) / len(base_values)
                offsets = [-30, -20, -10, -5, 5, 10, 20, 30]
                rng.shuffle(offsets)
                for offset in offsets:
                    candidate = average + offset
                    rendered = f"{int(candidate) if candidate.is_integer() else round(candidate, 2)}{suffix}"
                    add(rendered)
                    if len(pool) >= needed:
                        break

        return pool[:needed]

    def _generate_recommendation_mock(
        self,
        *,
        subject: Subject,
        language: PreferredLanguage,
        weak_topics: list[str],
    ) -> RecommendationPayload:
        if not weak_topics:
            weak_topics = ["Углубление темы"] if language == PreferredLanguage.ru else ["Тақырыпты тереңдету"]

        subject_name = subject.name_ru if language == PreferredLanguage.ru else subject.name_kz
        if language == PreferredLanguage.ru:
            advice = (
                f"Сконцентрируйтесь на темах: {', '.join(weak_topics[:3])}. "
                f"Повторяйте материал по предмету «{subject_name}» короткими сессиями по 25 минут."
            )
        else:
            advice = (
                f"Назарды келесі тақырыптарға аударыңыз: {', '.join(weak_topics[:3])}. "
                f"«{subject_name}» пәні бойынша 25 минуттық қысқа қайталау сессияларын жасаңыз."
            )

        tasks = []
        for idx in range(5):
            topic = weak_topics[idx % len(weak_topics)]
            if language == PreferredLanguage.ru:
                task_text = f"Тема: {topic}. Сформулируйте объяснение и приведите один практический пример."
            else:
                task_text = f"Тақырып: {topic}. Түсіндіріп, бір практикалық мысал келтіріңіз."
            tasks.append({"topic": topic, "task": task_text, "difficulty": "adaptive"})

        return RecommendationPayload(advice_text=advice, generated_tasks=tasks)

    def _generate_general_library_questions(
        self,
        *,
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        mode: TestMode,
    ) -> list[GeneratedQuestionPayload]:
        templates = get_text_question_templates(
            subject_name_ru=subject.name_ru,
            language=language,
            difficulty=difficulty,
        )
        if not templates:
            templates = []

        rng = random.Random(f"library::{subject.name_ru}::{language.value}::{difficulty.value}")
        target_count = self.LIBRARY_QUESTIONS_PER_COMBINATION
        text_questions = self._generate_text_questions_from_bank(
            subject=subject,
            difficulty=difficulty,
            language=language,
            num_questions=min(target_count, len(templates)),
            focus_topics=[],
            templates=list(templates),
            rng=rng,
        )

        if len(text_questions) < target_count:
            text_questions.extend(
                self._generate_text_template_variants(
                    templates=templates,
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    count=target_count - len(text_questions),
                    rng=rng,
                    variant_offset=0,
                )
            )

        candidates: list[GeneratedQuestionPayload] = []
        for index, question in enumerate(text_questions[:target_count]):
            adapted = self._adapt_library_question_to_mode(
                question=question,
                mode=mode,
                language=language,
            )
            candidates.append(
                self._attach_library_metadata(
                    question=adapted,
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    mode=mode,
                    library_index=index,
                )
            )

        candidates = self._sanitize_questions(
            questions=candidates,
            subject=subject,
            difficulty=difficulty,
            language=language,
            mode=mode,
            target_count=target_count,
            focus_topics=[],
        )

        if len(candidates) < target_count:
            needed = target_count - len(candidates)
            extra_seed = f"library-ai::{subject.id}::{language.value}::{difficulty.value}::{mode.value}"
            try:
                if settings.ai_provider.lower() == "deepseek" and settings.deepseek_api_key:
                    extra_payload = self._generate_test_deepseek(
                        subject=subject,
                        difficulty=difficulty,
                        language=language,
                        mode=mode,
                        num_questions=max(needed * 3, needed + 8),
                        seed=extra_seed,
                        focus_topics=[],
                    )
                else:
                    extra_payload = self._generate_test_mock(
                        subject=subject,
                        difficulty=difficulty,
                        language=language,
                        mode=mode,
                        num_questions=max(needed * 3, needed + 8),
                        seed=extra_seed,
                        focus_topics=[],
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to build AI-backed library questions: %s", exc)
                extra_payload = GeneratedTestPayload(seed=extra_seed, questions=[])

            start_index = len(candidates)
            attached_extras: list[GeneratedQuestionPayload] = []
            for idx, question in enumerate(extra_payload.questions):
                attached_extras.append(
                    self._attach_library_metadata(
                        question=question,
                        subject=subject,
                        difficulty=difficulty,
                        language=language,
                        mode=mode,
                        library_index=start_index + idx,
                        template_content_key=self._library_content_key(question.prompt),
                    )
                )

            candidates = self._merge_unique_questions(
                groups=[candidates, attached_extras],
                target_count=target_count,
            )

        return candidates[:target_count]

    def _adapt_library_question_to_mode(
        self,
        *,
        question: GeneratedQuestionPayload,
        mode: TestMode,
        language: PreferredLanguage,
    ) -> GeneratedQuestionPayload:
        if mode == TestMode.text:
            return question

        if mode == TestMode.audio:
            return GeneratedQuestionPayload(
                type=question.type,
                prompt=question.prompt,
                options_json=question.options_json,
                correct_answer_json=question.correct_answer_json,
                explanation_json=question.explanation_json,
                tts_text=question.prompt,
            )

        topic = str(question.explanation_json.get("topic", "")).strip() or (
            "Базовая тема" if language == PreferredLanguage.ru else "Негізгі тақырып"
        )
        source_answer_json: dict[str, Any] = dict(question.correct_answer_json or {})
        if question.type in {QuestionType.single_choice, QuestionType.multi_choice}:
            source_answer_json = self._build_oral_source_answer_from_choice(
                question=question,
                topic=topic,
                language=language,
            )

        return self._make_short_text_question(
            prompt=question.prompt,
            topic=topic,
            explanation_json=question.explanation_json,
            language=language,
            source_correct_answer_json=source_answer_json,
            oral=True,
        )

    def _build_short_text_source_answer(
        self,
        *,
        question: GeneratedQuestionPayload,
        topic: str,
        language: PreferredLanguage,
    ) -> dict[str, Any]:
        if question.type in {QuestionType.single_choice, QuestionType.multi_choice}:
            return self._build_oral_source_answer_from_choice(
                question=question,
                topic=topic,
                language=language,
            )
        return dict(question.correct_answer_json or {})

    def _build_oral_source_answer_from_choice(
        self,
        *,
        question: GeneratedQuestionPayload,
        topic: str,
        language: PreferredLanguage,
    ) -> dict[str, Any]:
        options = list((question.options_json or {}).get("options", []) or [])
        correct_ids = {
            int(item)
            for item in (question.correct_answer_json.get("correct_option_ids", []) or [])
            if isinstance(item, int)
        }
        correct_texts: list[str] = []
        for item in options:
            if not isinstance(item, dict):
                continue
            option_id = item.get("id")
            if not isinstance(option_id, int) or option_id not in correct_ids:
                continue
            text = self._strip_option_label(str(item.get("text", "")).strip())
            if text:
                correct_texts.append(text)

        if not correct_texts:
            fallback = _pick(
                language,
                ru=f"Ключевой ответ по теме «{topic}».",
                kz=f"«{topic}» тақырыбы бойынша негізгі жауап.",
            )
            correct_texts = [fallback]

        sample_answer = "; ".join(correct_texts)
        keywords = self._extract_keywords(topic=topic, language=language, source_keywords=correct_texts)
        return {"keywords": keywords, "sample_answer": sample_answer}

    def _attach_library_metadata(
        self,
        *,
        question: GeneratedQuestionPayload,
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        mode: TestMode,
        library_index: int,
        template_content_key: str | None = None,
    ) -> GeneratedQuestionPayload:
        explanation_json = dict(question.explanation_json or {})
        topic = str(explanation_json.get("topic", "")).strip() or (
            "Базовая тема" if language == PreferredLanguage.ru else "Негізгі тақырып"
        )
        explanation_json["topic"] = topic
        explanation_json["correct_explanation"] = str(
            explanation_json.get("correct_explanation", self._build_default_explanation(topic=topic, language=language))
        ).strip()
        explanation_json["library_question_id"] = (
            f"lib-bank::{self._slug(subject.name_ru)}::{language.value}::{difficulty.value}::{mode.value}::{library_index + 1:03d}"
        )
        explanation_json["library_topic"] = topic
        explanation_json["library_difficulty"] = difficulty.value
        explanation_json["library_content_key"] = self._library_content_key(question.prompt)
        inherited_template_key = str(explanation_json.get("library_template_key", "")).strip().lower()
        explanation_json["library_template_key"] = (
            str(template_content_key).strip().lower()
            if template_content_key and str(template_content_key).strip()
            else (inherited_template_key or explanation_json["library_content_key"])
        )
        return GeneratedQuestionPayload(
            type=question.type,
            prompt=question.prompt,
            options_json=question.options_json,
            correct_answer_json=question.correct_answer_json,
            explanation_json=explanation_json,
            tts_text=question.tts_text,
        )

    @staticmethod
    def _slug(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Zа-яА-ЯәіңғүұқөһӘІҢҒҮҰҚӨҺ0-9]+", "-", value.lower())
        return normalized.strip("-") or "topic"

    def _topics_for_subject(self, subject: Subject, language: PreferredLanguage) -> list[str]:
        subject_key = subject.name_ru.lower()
        topic_map_ru = {
            "математика": ["Линейные уравнения", "Функции", "Проценты", "Текстовые задачи", "Логика"],
            "алгебра": ["Квадратные уравнения", "Прогрессии", "Неравенства", "Графики функций", "Степени и корни"],
            "геометрия": ["Треугольники", "Окружность", "Площади фигур", "Подобие", "Теорема Пифагора"],
            "физика": ["Кинематика", "Динамика", "Энергия", "Электричество", "Оптика"],
            "русский язык": ["Орфография", "Пунктуация", "Синтаксис", "Лексика", "Стили речи"],
            "английский язык": ["Grammar", "Vocabulary", "Reading", "Tenses", "Sentence structure"],
            "биология": ["Клетка", "Генетика", "Экология", "Анатомия человека", "Эволюция"],
            "информатика": ["Алгоритмы", "Структуры данных", "Логические операции", "Базы данных", "Сети"],
            "химия": ["Периодическая система", "Химические реакции", "Строение вещества", "Растворы", "Окисление и восстановление"],
            "история": ["Хронология", "Причины и последствия", "Исторические личности", "Реформы", "Источники"],
            "всемирная история": ["Хронология", "Причины и последствия", "Исторические личности", "Реформы", "Источники"],
        }
        topic_map_kz = {
            "математика": ["Сызықтық теңдеулер", "Функциялар", "Пайыз", "Мәтіндік есептер", "Логика"],
            "алгебра": ["Квадрат теңдеулер", "Прогрессиялар", "Теңсіздіктер", "Функция графиктері", "Дәреже және түбір"],
            "геометрия": ["Үшбұрыштар", "Шеңбер", "Фигура аудандары", "Ұқсастық", "Пифагор теоремасы"],
            "физика": ["Кинематика", "Динамика", "Энергия", "Электр", "Оптика"],
            "орыс тілі": ["Орфография", "Пунктуация", "Синтаксис", "Лексика", "Сөйлеу стильдері"],
            "ағылшын тілі": ["Грамматика", "Сөздік қор", "Оқу", "Шақтар", "Сөйлем құрылымы"],
            "биология": ["Жасуша", "Генетика", "Экология", "Адам анатомиясы", "Эволюция"],
            "информатика": ["Алгоритмдер", "Деректер құрылымы", "Логикалық амалдар", "Дерекқор", "Желілер"],
            "химия": ["Периодтық кесте", "Химиялық реакциялар", "Зат құрылысы", "Ерітінділер", "Тотығу-тотықсыздану"],
            "история": ["Хронология", "Себеп пен салдар", "Тарихи тұлғалар", "Реформалар", "Дереккөздер"],
            "тарих": ["Хронология", "Себеп пен салдар", "Тарихи тұлғалар", "Реформалар", "Дереккөздер"],
            "дүниежүзі тарихы": ["Хронология", "Себеп пен салдар", "Тарихи тұлғалар", "Реформалар", "Дереккөздер"],
        }

        if language == PreferredLanguage.ru:
            return topic_map_ru.get(subject_key, ["Базовая теория", "Практика", "Анализ"])
        return topic_map_kz.get(subject_key, ["Негізгі теория", "Практика", "Талдау"])

    def _topic_pool(self, *, subject: Subject, language: PreferredLanguage, focus_topics: Sequence[str]) -> list[str]:
        seen: set[str] = set()
        combined: list[str] = []
        for item in [*focus_topics, *self._topics_for_subject(subject, language)]:
            value = str(item).strip()
            key = value.lower()
            if not value or key in seen:
                continue
            seen.add(key)
            combined.append(value)
        return combined or self._topics_for_subject(subject, language)

    @staticmethod
    def _choice_option_count(difficulty: DifficultyLevel) -> int:
        return 6 if difficulty == DifficultyLevel.hard else 4

    @staticmethod
    def _allowed_question_types(mode: TestMode) -> tuple[QuestionType, ...]:
        if mode == TestMode.text:
            return (QuestionType.single_choice, QuestionType.multi_choice, QuestionType.short_text)
        if mode == TestMode.audio:
            return (QuestionType.single_choice, QuestionType.multi_choice, QuestionType.short_text, QuestionType.matching)
        return (QuestionType.oral_answer, QuestionType.short_text, QuestionType.single_choice)

    @staticmethod
    def _pick_question_type(
        *,
        difficulty: DifficultyLevel,
        mode: TestMode,
        rng: random.Random,
    ) -> QuestionType:
        if mode == TestMode.text:
            if difficulty == DifficultyLevel.easy:
                pool = [QuestionType.single_choice, QuestionType.multi_choice, QuestionType.short_text]
                weights = [0.75, 0.2, 0.05]
            elif difficulty == DifficultyLevel.medium:
                pool = [QuestionType.single_choice, QuestionType.multi_choice, QuestionType.short_text]
                weights = [0.55, 0.25, 0.2]
            else:
                pool = [QuestionType.single_choice, QuestionType.multi_choice, QuestionType.short_text]
                weights = [0.35, 0.25, 0.4]
            return rng.choices(pool, weights=weights, k=1)[0]

        if mode == TestMode.audio:
            if difficulty == DifficultyLevel.easy:
                pool = [QuestionType.single_choice, QuestionType.multi_choice, QuestionType.short_text, QuestionType.matching]
                weights = [0.5, 0.2, 0.2, 0.1]
            elif difficulty == DifficultyLevel.medium:
                pool = [QuestionType.single_choice, QuestionType.multi_choice, QuestionType.short_text, QuestionType.matching]
                weights = [0.3, 0.25, 0.25, 0.2]
            else:
                pool = [QuestionType.single_choice, QuestionType.multi_choice, QuestionType.short_text, QuestionType.matching]
                weights = [0.25, 0.2, 0.35, 0.2]
            return rng.choices(pool, weights=weights, k=1)[0]

        if difficulty == DifficultyLevel.easy:
            pool = [QuestionType.single_choice, QuestionType.short_text, QuestionType.oral_answer]
            weights = [0.45, 0.35, 0.2]
        elif difficulty == DifficultyLevel.medium:
            pool = [QuestionType.single_choice, QuestionType.short_text, QuestionType.oral_answer]
            weights = [0.3, 0.4, 0.3]
        else:
            pool = [QuestionType.single_choice, QuestionType.short_text, QuestionType.oral_answer]
            weights = [0.2, 0.4, 0.4]
        return rng.choices(pool, weights=weights, k=1)[0]

    def _build_question(
        self,
        *,
        index: int,
        subject: Subject,
        topic: str,
        qtype: QuestionType,
        language: PreferredLanguage,
        mode: TestMode,
        difficulty: DifficultyLevel,
        rng: random.Random,
    ) -> GeneratedQuestionPayload:
        template_candidates = get_text_question_templates(
            subject_name_ru=subject.name_ru,
            language=language,
            difficulty=difficulty,
        )
        if template_candidates:
            topic_key = topic.lower()
            filtered = [
                item
                for item in template_candidates
                if topic_key in str(item.get("topic", "")).lower() or topic_key in str(item.get("prompt", "")).lower()
            ]
            template = dict(rng.choice(filtered or template_candidates))
            template["template_content_key"] = self._library_content_key(str(template.get("prompt", "")))
            base_question = self._build_question_from_bank_template(
                template=template,
                subject=subject,
                difficulty=difficulty,
                language=language,
                rng=rng,
            )

            if qtype == QuestionType.short_text and base_question.type != QuestionType.short_text:
                topic_value = str((base_question.explanation_json or {}).get("topic", "")).strip() or topic
                source_answer_json = self._build_short_text_source_answer(
                    question=base_question,
                    topic=topic_value,
                    language=language,
                )
                return self._make_short_text_question(
                    prompt=base_question.prompt,
                    topic=topic_value,
                    explanation_json=base_question.explanation_json,
                    language=language,
                    source_correct_answer_json=source_answer_json,
                    oral=False,
                )
            if qtype == QuestionType.oral_answer:
                return self._adapt_library_question_to_mode(
                    question=base_question,
                    mode=TestMode.oral,
                    language=language,
                )
            if mode != TestMode.text:
                return self._adapt_library_question_to_mode(
                    question=base_question,
                    mode=mode,
                    language=language,
                )
            return base_question

        subject_name = subject.name_ru if language == PreferredLanguage.ru else subject.name_kz

        if language == PreferredLanguage.ru:
            prompt = f"По предмету «{subject_name}» выполните задание по теме «{topic}»."
            explanation = {
                "topic": topic,
                "correct_explanation": f"Проверьте базовые определения и примените правило по теме «{topic}».",
            }
        else:
            prompt = f"«{subject_name}» пәні бойынша «{topic}» тақырыбына тапсырманы орындаңыз."
            explanation = {
                "topic": topic,
                "correct_explanation": f"«{topic}» тақырыбы бойынша негізгі ережені қолданыңыз.",
            }

        tts_text = prompt if mode == TestMode.audio else None

        if qtype == QuestionType.single_choice:
            options = self._build_options(topic=topic, language=language, count=self._choice_option_count(difficulty))
            correct = rng.randrange(0, len(options))
            if language == PreferredLanguage.ru:
                prompt += " Выберите один правильный ответ."
            else:
                prompt += " Бір дұрыс жауапты таңдаңыз."
            return GeneratedQuestionPayload(
                type=qtype,
                prompt=prompt,
                options_json={"options": options},
                correct_answer_json={"correct_option_ids": [correct]},
                explanation_json=explanation,
                tts_text=tts_text,
            )

        if qtype == QuestionType.multi_choice:
            options = self._build_options(topic=topic, language=language, count=self._choice_option_count(difficulty))
            correct_amount = 2 if len(options) >= 4 else 1
            correct_ids = sorted(rng.sample(range(len(options)), correct_amount))
            if language == PreferredLanguage.ru:
                prompt += " Выберите все верные варианты."
            else:
                prompt += " Барлық дұрыс нұсқаларды таңдаңыз."
            return GeneratedQuestionPayload(
                type=qtype,
                prompt=prompt,
                options_json={"options": options},
                correct_answer_json={"correct_option_ids": correct_ids},
                explanation_json=explanation,
                tts_text=tts_text,
            )

        if qtype == QuestionType.matching:
            left_items = [
                f"{topic} A",
                f"{topic} B",
                f"{topic} C",
            ]
            right_items = [
                "1",
                "2",
                "3",
            ]
            shuffled = right_items[:]
            rng.shuffle(shuffled)
            matches = {left_items[i]: right_items[i] for i in range(len(left_items))}
            if language == PreferredLanguage.ru:
                prompt += " Сопоставьте элементы слева и справа."
            else:
                prompt += " Сол жақ пен оң жақ элементтерін сәйкестендіріңіз."
            return GeneratedQuestionPayload(
                type=qtype,
                prompt=prompt,
                options_json={"left": left_items, "right": shuffled},
                correct_answer_json={"matches": matches},
                explanation_json=explanation,
                tts_text=tts_text,
            )

        if qtype == QuestionType.oral_answer:
            if language == PreferredLanguage.ru:
                prompt += " Ответьте устно: объясните идею и приведите пример."
                sample_answer = f"Тема {topic} объясняется через правило и практический пример."
            else:
                prompt += " Ауызша жауап беріңіз: идеяны түсіндіріп, мысал келтіріңіз."
                sample_answer = f"{topic} тақырыбы ереже мен практикалық мысал арқылы түсіндіріледі."
            return GeneratedQuestionPayload(
                type=qtype,
                prompt=prompt,
                options_json=None,
                correct_answer_json={
                    "keywords": [topic.split()[0].lower(), "мысал" if language == PreferredLanguage.kz else "пример"],
                    "sample_answer": sample_answer,
                    "expected_field": "spoken_answer_text",
                },
                explanation_json=explanation,
                tts_text=tts_text,
            )

        return self._make_short_text_question(
            prompt=prompt,
            topic=topic,
            explanation_json=explanation,
            language=language,
            tts_text=tts_text,
        )

    def _sanitize_questions(
        self,
        *,
        questions: Sequence[GeneratedQuestionPayload],
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        mode: TestMode,
        target_count: int,
        focus_topics: Sequence[str],
        existing_prompt_keys: set[str] | None = None,
    ) -> list[GeneratedQuestionPayload]:
        output: list[GeneratedQuestionPayload] = []
        seen_prompt_keys = set(existing_prompt_keys or set())
        topic_pool = self._topic_pool(subject=subject, language=language, focus_topics=focus_topics)
        allowed_types = set(self._allowed_question_types(mode))

        for index, question in enumerate(questions):
            if len(output) >= target_count:
                break

            default_topic = topic_pool[index % len(topic_pool)]
            topic = str(question.explanation_json.get("topic", "")).strip() or default_topic
            explanation_text = str(question.explanation_json.get("correct_explanation", "")).strip()
            if not explanation_text:
                explanation_text = self._build_default_explanation(topic=topic, language=language)
            extra_explanation = {
                str(key): value
                for key, value in (question.explanation_json or {}).items()
                if str(key) not in {"topic", "correct_explanation"}
            }

            prompt = str(question.prompt).strip()
            if not prompt:
                continue
            if self._is_low_quality_prompt(prompt):
                continue
            qtype = question.type
            if qtype not in allowed_types:
                qtype = QuestionType.short_text if QuestionType.short_text in allowed_types else QuestionType.single_choice
            if mode == TestMode.text and qtype in {QuestionType.matching, QuestionType.oral_answer}:
                qtype = QuestionType.short_text if qtype == QuestionType.oral_answer else QuestionType.single_choice

            tts_text = question.tts_text if mode == TestMode.audio else None
            if mode == TestMode.audio and not tts_text:
                tts_text = prompt

            normalized: GeneratedQuestionPayload
            if qtype in {QuestionType.single_choice, QuestionType.multi_choice}:
                sanitized_choice_payload = self._sanitize_choice_payload(
                    subject=subject,
                    topic=topic,
                    language=language,
                    option_count=self._choice_option_count(difficulty),
                    source_options=question.options_json,
                    source_correct_answer=question.correct_answer_json,
                    question_type=qtype,
                )
                if sanitized_choice_payload is None:
                    continue
                options, correct_option_ids = sanitized_choice_payload
                normalized = GeneratedQuestionPayload(
                    type=qtype,
                    prompt=prompt,
                    options_json={"options": options},
                    correct_answer_json={"correct_option_ids": correct_option_ids},
                    explanation_json={"topic": topic, "correct_explanation": explanation_text, **extra_explanation},
                    tts_text=tts_text,
                )
            elif qtype == QuestionType.matching:
                left = [str(item).strip() for item in (question.options_json or {}).get("left", []) if str(item).strip()]
                right = [str(item).strip() for item in (question.options_json or {}).get("right", []) if str(item).strip()]
                matches = {
                    str(key).strip(): str(value).strip()
                    for key, value in (question.correct_answer_json.get("matches", {}) or {}).items()
                    if str(key).strip() and str(value).strip()
                }
                if not left or not right or not matches:
                    normalized = self._make_short_text_question(
                        prompt=prompt,
                        topic=topic,
                        explanation_json={"topic": topic, "correct_explanation": explanation_text},
                        language=language,
                        tts_text=tts_text,
                    )
                else:
                    normalized = GeneratedQuestionPayload(
                        type=QuestionType.matching,
                        prompt=prompt,
                        options_json={"left": left, "right": right},
                        correct_answer_json={"matches": matches},
                        explanation_json={"topic": topic, "correct_explanation": explanation_text, **extra_explanation},
                        tts_text=tts_text,
                    )
            else:
                source_answer_json = self._build_short_text_source_answer(
                    question=question,
                    topic=topic,
                    language=language,
                )
                normalized = self._make_short_text_question(
                    prompt=prompt,
                    topic=topic,
                    explanation_json={"topic": topic, "correct_explanation": explanation_text, **extra_explanation},
                    language=language,
                    tts_text=tts_text,
                    source_correct_answer_json=source_answer_json,
                    oral=(qtype == QuestionType.oral_answer),
                )

            key = self._question_uniqueness_key(normalized)
            if key in seen_prompt_keys:
                continue
            seen_prompt_keys.add(key)
            output.append(normalized)

        self._enforce_text_difficulty_mix(questions=output, language=language, mode=mode, difficulty=difficulty)
        return output[:target_count]

    def _sanitize_choice_payload(
        self,
        *,
        subject: Subject,
        topic: str,
        language: PreferredLanguage,
        option_count: int,
        source_options: dict[str, Any] | None,
        source_correct_answer: dict[str, Any] | None,
        question_type: QuestionType,
    ) -> tuple[list[dict[str, Any]], list[int]] | None:
        raw_items = []
        if source_options and isinstance(source_options, dict):
            raw_items = source_options.get("options", []) or []

        normalized_texts: list[str] = []
        text_to_index: dict[str, int] = {}
        raw_to_normalized: dict[int, int] = {}
        for raw_idx, item in enumerate(raw_items):
            text = ""
            if isinstance(item, dict):
                text = str(item.get("text", "")).strip()
            elif isinstance(item, str):
                text = item.strip()
            if not text:
                continue
            cleaned = self._strip_option_label(text)
            key = cleaned.lower()
            if key not in text_to_index:
                text_to_index[key] = len(normalized_texts)
                normalized_texts.append(cleaned)
            raw_to_normalized[raw_idx] = text_to_index[key]

        raw_correct_ids = []
        values = (source_correct_answer or {}).get("correct_option_ids", [])
        if isinstance(values, list):
            for value in values:
                try:
                    raw_id = int(value)
                except (TypeError, ValueError):
                    continue
                raw_correct_ids.append(raw_id)

        remapped_correct_ids: list[int] = []
        for raw_id in raw_correct_ids:
            mapped = raw_to_normalized.get(raw_id)
            if mapped is None:
                continue
            if mapped not in remapped_correct_ids:
                remapped_correct_ids.append(mapped)

        rng = random.Random(f"sanitize::{subject.name_ru}::{language.value}::{topic}::{option_count}")
        subject_distractors = get_distractors(subject_name_ru=subject.name_ru, language=language)
        contextual_distractors = self._contextual_distractors_from_options(
            options=normalized_texts,
            language=language,
            needed=option_count * 3,
            rng=rng,
        )
        topic_tokens = {
            token
            for token in re.findall(r"[a-zA-Zа-яА-ЯәіңғүұқөһӘІҢҒҮҰҚӨҺ0-9]+", topic.lower())
            if len(token) >= 4
        }
        topic_matched_distractors = [
            item
            for item in subject_distractors
            if any(token in item.lower() for token in topic_tokens)
        ]

        for fallback in [*contextual_distractors, *topic_matched_distractors]:
            if len(normalized_texts) >= option_count:
                break
            key = str(fallback).strip().lower()
            if key in text_to_index:
                continue
            text_to_index[key] = len(normalized_texts)
            normalized_texts.append(str(fallback).strip())

        min_required_options = min(4, option_count)
        if len(normalized_texts) < min_required_options:
            return None

        if len(normalized_texts) > option_count:
            mandatory = sorted({idx for idx in remapped_correct_ids if 0 <= idx < len(normalized_texts)})
            others = [idx for idx in range(len(normalized_texts)) if idx not in mandatory]
            selected = mandatory + others[: max(0, option_count - len(mandatory))]
            selected = sorted(set(selected))[:option_count]
            remap = {old: new for new, old in enumerate(selected)}
            normalized_texts = [normalized_texts[idx] for idx in selected]
            remapped_correct_ids = [remap[idx] for idx in mandatory if idx in remap]

        if question_type == QuestionType.single_choice:
            if not remapped_correct_ids:
                remapped_correct_ids = [0]
            else:
                remapped_correct_ids = [remapped_correct_ids[0]]
        else:
            if not remapped_correct_ids:
                remapped_correct_ids = [0, 1] if len(normalized_texts) > 1 else [0]
            if len(remapped_correct_ids) == 1 and len(normalized_texts) > 1:
                remapped_correct_ids.append(1 if remapped_correct_ids[0] != 1 else 0)
            remapped_correct_ids = sorted(set(remapped_correct_ids[:3]))

        options: list[dict[str, Any]] = []
        for index, text in enumerate(normalized_texts[:option_count]):
            label = self.OPTION_LABELS[index]
            options.append({"id": index, "text": f"{label}. {text}"})

        return options, remapped_correct_ids

    def _enforce_text_difficulty_mix(
        self,
        *,
        questions: list[GeneratedQuestionPayload],
        language: PreferredLanguage,
        mode: TestMode,
        difficulty: DifficultyLevel,
    ) -> None:
        if mode != TestMode.text or not questions:
            return

        if difficulty == DifficultyLevel.easy:
            return

        required_short_questions = max(1, len(questions) // 5) if difficulty == DifficultyLevel.medium else max(2, len(questions) // 3)
        current_short_questions = sum(1 for item in questions if item.type == QuestionType.short_text)
        for index in range(len(questions) - 1, -1, -1):
            if current_short_questions >= required_short_questions:
                break
            question = questions[index]
            if question.type not in {QuestionType.single_choice, QuestionType.multi_choice}:
                continue
            topic = str(question.explanation_json.get("topic", "")).strip() or (
                "Причинно-следственный анализ" if language == PreferredLanguage.ru else "Себеп-салдар талдауы"
            )
            source_answer_json = self._build_short_text_source_answer(
                question=question,
                topic=topic,
                language=language,
            )
            questions[index] = self._make_short_text_question(
                prompt=question.prompt,
                topic=topic,
                explanation_json=question.explanation_json,
                language=language,
                source_correct_answer_json=source_answer_json,
            )
            current_short_questions += 1

        if difficulty != DifficultyLevel.hard:
            return

        required_multi_questions = max(1, len(questions) // 4)
        current_multi_questions = sum(1 for item in questions if item.type == QuestionType.multi_choice)
        for index in range(len(questions) - 1, -1, -1):
            if current_multi_questions >= required_multi_questions:
                break
            question = questions[index]
            if question.type != QuestionType.single_choice:
                continue
            questions[index] = self._convert_single_to_multi(question=question, language=language)
            current_multi_questions += 1

    def _make_short_text_question(
        self,
        *,
        prompt: str,
        topic: str,
        explanation_json: dict[str, Any],
        language: PreferredLanguage,
        tts_text: str | None = None,
        source_correct_answer_json: dict[str, Any] | None = None,
        oral: bool = False,
    ) -> GeneratedQuestionPayload:
        normalized_prompt = prompt.strip()
        normalized_prompt = re.sub(r"\s*Выберите один правильный ответ\.?\s*$", "", normalized_prompt, flags=re.IGNORECASE)
        normalized_prompt = re.sub(r"\s*Выберите все верные варианты\.?\s*$", "", normalized_prompt, flags=re.IGNORECASE)
        normalized_prompt = re.sub(r"\s*Бір дұрыс жауапты таңдаңыз\.?\s*$", "", normalized_prompt, flags=re.IGNORECASE)
        normalized_prompt = re.sub(r"\s*Барлық дұрыс нұсқаларды таңдаңыз\.?\s*$", "", normalized_prompt, flags=re.IGNORECASE)
        normalized_prompt = normalized_prompt.strip()
        if oral:
            if language == PreferredLanguage.ru and "Ответьте устно" not in normalized_prompt:
                normalized_prompt = f"{normalized_prompt} Ответьте устно и кратко аргументируйте ответ."
            if language == PreferredLanguage.kz and "Ауызша жауап" not in normalized_prompt:
                normalized_prompt = f"{normalized_prompt} Ауызша жауап беріп, қысқаша дәлелдеңіз."
        else:
            normalized_prompt_lower = normalized_prompt.lower()
            if language == PreferredLanguage.ru and "кратк" not in normalized_prompt_lower and "коротк" not in normalized_prompt_lower:
                normalized_prompt = f"{normalized_prompt} Дайте краткий текстовый ответ."
            if language == PreferredLanguage.kz and "қысқа" not in normalized_prompt.lower():
                normalized_prompt = f"{normalized_prompt} Қысқа мәтіндік жауап беріңіз."

        source_keywords = []
        if source_correct_answer_json:
            source_keywords = source_correct_answer_json.get("keywords", []) or []
        keywords = self._extract_keywords(topic=topic, language=language, source_keywords=source_keywords)
        sample_answer = str((source_correct_answer_json or {}).get("sample_answer", "")).strip()
        if not sample_answer:
            sample_answer = (
                f"По теме «{topic}» важно объяснить определение, причину и практический пример."
                if language == PreferredLanguage.ru
                else f"«{topic}» тақырыбы бойынша анықтама, себеп және практикалық мысалды түсіндіру маңызды."
            )

        correct_answer_json: dict[str, Any] = {"keywords": keywords, "sample_answer": sample_answer}
        if oral:
            correct_answer_json["expected_field"] = "spoken_answer_text"

        explanation_extras = {
            str(key): value
            for key, value in (explanation_json or {}).items()
            if str(key) not in {"topic", "correct_explanation"}
        }

        return GeneratedQuestionPayload(
            type=QuestionType.oral_answer if oral else QuestionType.short_text,
            prompt=normalized_prompt,
            options_json=None,
            correct_answer_json=correct_answer_json,
            explanation_json={
                "topic": str(explanation_json.get("topic", topic)).strip() or topic,
                "correct_explanation": str(
                    explanation_json.get("correct_explanation", self._build_default_explanation(topic=topic, language=language))
                ).strip(),
                **explanation_extras,
            },
            tts_text=tts_text,
        )

    @staticmethod
    def _is_low_quality_prompt(prompt: str) -> bool:
        normalized = re.sub(r"\s+", " ", prompt.strip().lower())
        if len(normalized) < 12:
            return True
        low_quality_patterns = [
            r"^вопрос\s*\d+",
            r"^\[[^\]]+\]\s*вопрос\s*\d+",
            r"^\d+\s*[-–]?\s*сұрақ",
            r"^\[[^\]]+\]\s*\d+\s*[-–]?\s*сұрақ",
        ]
        return any(re.search(pattern, normalized) for pattern in low_quality_patterns)

    def _convert_short_to_choice(
        self,
        *,
        question: GeneratedQuestionPayload,
        language: PreferredLanguage,
        difficulty: DifficultyLevel,
    ) -> GeneratedQuestionPayload:
        topic = str(question.explanation_json.get("topic", "")).strip() or (
            "Базовая теория" if language == PreferredLanguage.ru else "Негізгі теория"
        )
        prompt = str(question.prompt).strip()
        prompt = re.sub(r"\s*Дайте краткий текстовый ответ\.?\s*$", "", prompt, flags=re.IGNORECASE).strip()
        prompt = re.sub(r"\s*Қысқа мәтіндік жауап беріңіз\.?\s*$", "", prompt, flags=re.IGNORECASE).strip()
        if language == PreferredLanguage.ru and "Выберите один правильный ответ" not in prompt:
            prompt = f"{prompt} Выберите один правильный ответ."
        if language == PreferredLanguage.kz and "Бір дұрыс жауапты таңдаңыз" not in prompt:
            prompt = f"{prompt} Бір дұрыс жауапты таңдаңыз."

        options = self._build_options(topic=topic, language=language, count=self._choice_option_count(difficulty))
        explanation_extras = {
            str(key): value
            for key, value in (question.explanation_json or {}).items()
            if str(key) not in {"topic", "correct_explanation"}
        }
        return GeneratedQuestionPayload(
            type=QuestionType.single_choice,
            prompt=prompt,
            options_json={"options": options},
            correct_answer_json={"correct_option_ids": [0]},
            explanation_json={
                "topic": topic,
                "correct_explanation": str(question.explanation_json.get("correct_explanation", "")).strip()
                or self._build_default_explanation(topic=topic, language=language),
                **explanation_extras,
            },
            tts_text=question.tts_text,
        )

    @staticmethod
    def _convert_single_to_multi(*, question: GeneratedQuestionPayload, language: PreferredLanguage) -> GeneratedQuestionPayload:
        options = list((question.options_json or {}).get("options", []) or [])
        if len(options) < 2:
            return question

        current_ids = [int(item) for item in (question.correct_answer_json.get("correct_option_ids", []) or []) if isinstance(item, int)]
        first_correct = current_ids[0] if current_ids else 0
        second_correct = 1 if first_correct != 1 and len(options) > 1 else 0
        correct_ids = sorted({first_correct, second_correct})

        prompt = str(question.prompt).strip()
        prompt = re.sub(r"\s*Выберите один правильный ответ\.?\s*$", "", prompt, flags=re.IGNORECASE).strip()
        prompt = re.sub(r"\s*Бір дұрыс жауапты таңдаңыз\.?\s*$", "", prompt, flags=re.IGNORECASE).strip()
        if "Выберите все верные варианты" not in prompt and "Барлық дұрыс нұсқаларды таңдаңыз" not in prompt:
            prompt = (
                f"{prompt} Выберите все верные варианты."
                if language == PreferredLanguage.ru
                else f"{prompt} Барлық дұрыс нұсқаларды таңдаңыз."
            )

        return GeneratedQuestionPayload(
            type=QuestionType.multi_choice,
            prompt=prompt,
            options_json={"options": options},
            correct_answer_json={"correct_option_ids": correct_ids},
            explanation_json=question.explanation_json,
            tts_text=question.tts_text,
        )

    def _sanitize_choice_options(
        self,
        *,
        topic: str,
        language: PreferredLanguage,
        option_count: int,
        source_options: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        raw_items = []
        if source_options and isinstance(source_options, dict):
            raw_items = source_options.get("options", []) or []

        normalized_texts: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            text: str = ""
            if isinstance(item, dict):
                text = str(item.get("text", "")).strip()
            elif isinstance(item, str):
                text = item.strip()
            if not text:
                continue
            cleaned = self._strip_option_label(text)
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized_texts.append(cleaned)

        fallback_texts = self._fallback_option_texts(topic=topic, language=language, count=option_count * 2)
        for fallback in fallback_texts:
            if len(normalized_texts) >= option_count:
                break
            key = fallback.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized_texts.append(fallback)

        normalized_texts = normalized_texts[:option_count]
        options: list[dict[str, Any]] = []
        for index, text in enumerate(normalized_texts):
            label = self.OPTION_LABELS[index]
            options.append({"id": index, "text": f"{label}. {text}"})
        return options

    @staticmethod
    def _sanitize_correct_option_ids(
        *,
        source: dict[str, Any],
        question_type: QuestionType,
        option_count: int,
    ) -> list[int]:
        values = source.get("correct_option_ids", []) if isinstance(source, dict) else []
        normalized = []
        if isinstance(values, list):
            for value in values:
                try:
                    option_id = int(value)
                except (TypeError, ValueError):
                    continue
                if 0 <= option_id < option_count and option_id not in normalized:
                    normalized.append(option_id)

        if question_type == QuestionType.single_choice:
            if not normalized:
                normalized = [0]
            return [normalized[0]]

        if not normalized:
            normalized = [0, 1] if option_count > 1 else [0]
        if len(normalized) == 1 and option_count > 1:
            normalized.append(1 if normalized[0] != 1 else 0)
        return sorted(normalized[:3])

    def _extract_keywords(
        self,
        *,
        topic: str,
        language: PreferredLanguage,
        source_keywords: Sequence[Any],
    ) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for keyword in source_keywords:
            value = str(keyword).strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            cleaned.append(value)

        for token in re.findall(r"[a-zA-Zа-яА-ЯәіңғүұқөһӘІҢҒҮҰҚӨҺ0-9]+", topic.lower()):
            if len(token) < 4 or token in seen:
                continue
            seen.add(token)
            cleaned.append(token)
            if len(cleaned) >= 3:
                break

        fallback_keyword = "пример" if language == PreferredLanguage.ru else "мысал"
        if fallback_keyword not in seen:
            cleaned.append(fallback_keyword)

        return cleaned[:4]

    @staticmethod
    def _build_default_prompt(*, topic: str, language: PreferredLanguage, index: int) -> str:
        if language == PreferredLanguage.ru:
            return f"Вопрос {index + 1} по теме «{topic}»."
        return f"{index + 1}-сұрақ «{topic}» тақырыбы бойынша."

    @staticmethod
    def _build_default_explanation(*, topic: str, language: PreferredLanguage) -> str:
        if language == PreferredLanguage.ru:
            return f"Проверьте определение, ключевые признаки и пример по теме «{topic}»."
        return f"«{topic}» тақырыбы бойынша анықтама, негізгі белгілер және мысалды қайталаңыз."

    @staticmethod
    def _strip_option_label(text: str) -> str:
        return re.sub(r"^\s*[A-ZА-Я]\s*[\).\:\-]\s*", "", text).strip()

    @staticmethod
    def _prompt_key(prompt: str) -> str:
        normalized = re.sub(r"\s+", " ", prompt.lower()).strip()
        normalized = re.sub(r"^\s*\[[^\]]+\]\s*", "", normalized).strip()
        normalized = re.sub(r"^\s*вопрос\s*\d+\s*[:.\-]\s*", "", normalized).strip()
        normalized = re.sub(r"^\s*\d+\s*[-.)]\s*", "", normalized).strip()
        normalized = re.sub(r"\s*\((вариант|нұсқа)\s*\d+\)\s*$", "", normalized, flags=re.IGNORECASE).strip()
        normalized = re.sub(r"[.!?…]+$", "", normalized).strip()
        return normalized

    def _question_uniqueness_key(self, question: GeneratedQuestionPayload) -> str:
        explanation = dict(question.explanation_json or {})
        template_key = str(explanation.get("library_template_key", "")).strip().lower()
        if template_key:
            return f"tpl::{template_key}"

        content_key = str(explanation.get("library_content_key", "")).strip().lower()
        if content_key:
            return f"cnt::{content_key}"

        return f"pr::{self._prompt_key(question.prompt)}"

    def _fallback_option_texts(self, *, topic: str, language: PreferredLanguage, count: int) -> list[str]:
        if language == PreferredLanguage.ru:
            base = [
                f"Верное определение по теме «{topic}»",
                f"Причина, связанная с темой «{topic}»",
                f"Пример практического применения темы «{topic}»",
                f"Типичная ошибка в теме «{topic}»",
                f"Ключевой факт по теме «{topic}»",
                f"Утверждение о последствиях по теме «{topic}»",
                f"Сравнение подходов в теме «{topic}»",
                f"Обобщающий вывод по теме «{topic}»",
            ]
        else:
            base = [
                f"«{topic}» тақырыбы бойынша дұрыс анықтама",
                f"«{topic}» тақырыбына қатысты себеп",
                f"«{topic}» тақырыбының практикалық мысалы",
                f"«{topic}» тақырыбындағы жиі қате",
                f"«{topic}» тақырыбы бойынша негізгі факт",
                f"«{topic}» тақырыбының салдары туралы тұжырым",
                f"«{topic}» тақырыбындағы тәсілдерді салыстыру",
                f"«{topic}» тақырыбы бойынша қорытынды",
            ]

        output: list[str] = []
        while len(output) < count:
            output.extend(base)
        return output[:count]

    def _build_options(self, topic: str, language: PreferredLanguage, count: int) -> list[dict]:
        texts = self._fallback_option_texts(topic=topic, language=language, count=count)
        options = []
        for idx in range(count):
            label = self.OPTION_LABELS[idx]
            options.append({"id": idx, "text": f"{label}. {texts[idx]}"})
        return options


ai_service = AIService()
