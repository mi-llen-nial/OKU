from __future__ import annotations

import json
import logging
import random
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.models import DifficultyLevel, PreferredLanguage, QuestionType, Subject, TestMode
from app.schemas.tests import GeneratedQuestionPayload, GeneratedTestPayload
from app.services.llm import LLMProviderError, is_llm_provider_configured, llm_chat
from app.services.question_bank import SUBJECT_FACT_BANK, _pick, get_distractors, get_text_question_templates

logger = logging.getLogger(__name__)


@dataclass
class RecommendationPayload:
    advice_text: str
    generated_tasks: list[dict]


class AIService:
    OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    LIBRARY_QUESTIONS_PER_COMBINATION = 25

    @staticmethod
    def _student_provider_name() -> str:
        return (settings.student_ai_provider or settings.ai_provider or "openai").strip().lower() or "openai"

    @staticmethod
    def _teacher_provider_name() -> str:
        return (settings.teacher_ai_provider or settings.ai_provider or "openai").strip().lower() or "openai"

    def _llm_is_configured(self, *, audience: str) -> bool:
        provider_name = self._teacher_provider_name() if audience == "teacher" else self._student_provider_name()
        return is_llm_provider_configured(provider_name, audience=audience)

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
        used_library_content_keys: set[str] | None = None,
    ) -> GeneratedTestPayload:
        seed = f"{int(time.time() * 1000)}-{user_id}-{subject.id}-{difficulty.value}"
        normalized_focus_topics = [str(topic).strip() for topic in (focus_topics or []) if str(topic).strip()]
        used_library_ids = set(used_library_question_ids or set())
        used_library_keys = {str(value).strip().lower() for value in (used_library_content_keys or set()) if str(value).strip()}

        difficulty_order: list[DifficultyLevel] = []
        for item in (difficulty, DifficultyLevel.medium, DifficultyLevel.easy, DifficultyLevel.hard):
            if item not in difficulty_order:
                difficulty_order.append(item)

        # Fast path: generate only from local library first (no external LLM calls).
        library_pool = self.generate_library_only_questions(
            subject=subject,
            language=language,
            mode=mode,
            num_questions=min(260, max(num_questions * 5, num_questions + 12, self.LIBRARY_QUESTIONS_PER_COMBINATION * 2)),
            seed=f"{seed}-library-fast",
            difficulty_order=difficulty_order,
            used_library_question_ids=used_library_ids,
            used_library_content_keys=used_library_keys,
        )

        rng = random.Random(f"{seed}-library")
        selected_library = self._sample_library_questions(
            questions=library_pool,
            limit=num_questions,
            rng=rng,
            focus_topics=normalized_focus_topics,
        )
        if len(selected_library) >= num_questions:
            return GeneratedTestPayload(seed=seed, questions=selected_library)

        fallback_sources: list[list[GeneratedQuestionPayload]] = [list(selected_library)] if selected_library else []
        remaining = max(0, num_questions - len(selected_library))
        merged = list(selected_library)

        if remaining > 0:
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
                groups=[merged, generated.questions],
                target_count=num_questions,
            )

        if len(merged) < num_questions:
            deterministic_topup = self._generate_test_mock(
                subject=subject,
                difficulty=difficulty,
                language=language,
                mode=mode,
                num_questions=max(num_questions - len(merged) + 2, 4),
                seed=f"{seed}-deterministic-topup",
                focus_topics=normalized_focus_topics,
            )
            fallback_sources.append(list(deterministic_topup.questions))
            merged = self._merge_unique_questions(
                groups=[merged, deterministic_topup.questions],
                target_count=num_questions,
            )

        if len(merged) < num_questions:
            merged = self._fill_questions_to_target(
                current=merged,
                fallback_groups=fallback_sources,
                target_count=num_questions,
            )

        if len(merged) >= num_questions:
            return GeneratedTestPayload(seed=seed, questions=merged[:num_questions])

        topped_up = self._top_up_unique_questions(
            current=merged,
            subject=subject,
            difficulty=difficulty,
            language=language,
            mode=mode,
            target_count=num_questions,
            focus_topics=normalized_focus_topics,
            seed=f"{seed}-unique-topup",
        )
        return GeneratedTestPayload(seed=seed, questions=topped_up[:num_questions])

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
        focus_topics: Sequence[str] | None = None,
    ) -> list[GeneratedQuestionPayload]:
        if limit <= 0:
            return []

        normalized_focus = [item.lower() for item in (focus_topics or []) if item]
        ranked = sorted(
            questions,
            key=lambda item: (
                0 if self._question_matches_focus(item, normalized_focus) else 1,
                self._is_variant_prompt(item.prompt),
                rng.random(),
            ),
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

    @staticmethod
    def _question_matches_focus(question: GeneratedQuestionPayload, focus_topics: Sequence[str]) -> bool:
        if not focus_topics:
            return False
        explanation = dict(question.explanation_json or {})
        topic = str(explanation.get("topic", "")).strip().lower()
        prompt = str(question.prompt or "").strip().lower()
        return any(item and (item in topic or item in prompt) for item in focus_topics)

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
        if self._llm_is_configured(audience="student"):
            try:
                return self._generate_recommendation_llm(
                    subject=subject,
                    language=language,
                    weak_topics=list(weak_topics),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM recommendation failed, fallback to mock: %s", exc)

        return self._generate_recommendation_mock(
            subject=subject,
            language=language,
            weak_topics=list(weak_topics),
        )

    def generate_teacher_custom_material(
        self,
        *,
        topic: str,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        questions_count: int,
        user_id: int,
    ) -> list[dict[str, Any]]:
        normalized_topic = topic.strip()
        if not normalized_topic:
            raise ValueError("Тема не может быть пустой")

        seed = f"teacher-custom-{int(time.time() * 1000)}-{user_id}-{difficulty.value}"
        try:
            if self._llm_is_configured(audience="teacher"):
                aggregated: list[dict[str, Any]] = []
                seen_prompt_keys: set[str] = set()
                last_exc: Exception | None = None
                generated_batches: list[dict[str, Any]] = []
                try:
                    generated_batches.extend(
                        self._generate_teacher_custom_material_llm(
                            topic=normalized_topic,
                            difficulty=difficulty,
                            language=language,
                            questions_count=questions_count,
                            seed=f"{seed}-batch-1",
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    logger.warning("LLM teacher material generation batch failed: %s", exc)

                for item in generated_batches:
                    prompt_key = self._semantic_prompt_key(str(item.get("prompt", "")))
                    if not prompt_key or prompt_key in seen_prompt_keys:
                        continue
                    seen_prompt_keys.add(prompt_key)
                    aggregated.append(item)
                    if len(aggregated) >= questions_count:
                        break

                if len(aggregated) >= questions_count:
                    return aggregated[:questions_count]

                if aggregated and len(aggregated) < questions_count:
                    # One additional LLM top-up attempt before deterministic fallback.
                    fallback_needed = questions_count - len(aggregated)
                    try:
                        topup_questions = self._generate_teacher_custom_material_llm(
                            topic=normalized_topic,
                            difficulty=difficulty,
                            language=language,
                            questions_count=min(questions_count, fallback_needed + 2),
                            seed=f"{seed}-topup",
                        )
                        for item in topup_questions:
                            prompt_key = self._semantic_prompt_key(str(item.get("prompt", "")))
                            if not prompt_key or prompt_key in seen_prompt_keys:
                                continue
                            seen_prompt_keys.add(prompt_key)
                            aggregated.append(item)
                            if len(aggregated) >= questions_count:
                                break
                    except Exception as exc:  # noqa: BLE001
                        last_exc = exc
                        logger.warning("LLM teacher material generation top-up failed: %s", exc)

                    if len(aggregated) >= questions_count:
                        return aggregated[:questions_count]

                    fallback_questions = self._generate_teacher_custom_material_fallback(
                        topic=normalized_topic,
                        difficulty=difficulty,
                        language=language,
                        questions_count=fallback_needed + 4,
                        seed=f"{seed}-fallback",
                    )
                    for item in fallback_questions:
                        prompt_key = self._semantic_prompt_key(str(item.get("prompt", "")))
                        if not prompt_key or prompt_key in seen_prompt_keys:
                            continue
                        seen_prompt_keys.add(prompt_key)
                        aggregated.append(item)
                        if len(aggregated) >= questions_count:
                            break
                    if len(aggregated) >= questions_count:
                        return aggregated[:questions_count]

                if last_exc is not None:
                    raise ValueError(
                        f"LLM не смог сгенерировать релевантный материал по теме «{normalized_topic}»: "
                        f"{self._format_teacher_llm_error(last_exc)}"
                    ) from last_exc
                raise ValueError(
                    f"LLM вернул недостаточно релевантных вопросов по теме «{normalized_topic}». "
                    "Попробуйте уточнить тему."
                )
            else:
                logger.info("LLM provider is not configured; teacher material falls back to deterministic builder.")

            return self._generate_teacher_custom_material_fallback(
                topic=normalized_topic,
                difficulty=difficulty,
                language=language,
                questions_count=questions_count,
                seed=seed,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Teacher material generation failed: %s", exc)
            raise

    def _generate_teacher_custom_material_llm(
        self,
        *,
        topic: str,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        questions_count: int,
        seed: str,
    ) -> list[dict[str, Any]]:
        language_label = "русском" if language == PreferredLanguage.ru else "қазақ"
        difficulty_hint = {
            DifficultyLevel.easy: "Базовый уровень: определения, простые примеры, базовые факты.",
            DifficultyLevel.medium: "Средний уровень: применение правил, сравнение и классификация.",
            DifficultyLevel.hard: "Сложный уровень: анализ, причинно-следственные связи, интерпретация.",
        }[difficulty]
        free_text_target = {
            DifficultyLevel.easy: 0,
            DifficultyLevel.medium: max(1, questions_count // 5),
            DifficultyLevel.hard: max(2, questions_count // 3),
        }[difficulty]
        input_payload = {
            "topic": topic,
            "difficulty": difficulty.value,
            "language": language.value.upper(),
            "questions_count": questions_count,
            "free_text_target_min": free_text_target,
            "seed": seed,
        }
        output_schema = {
            "questions": [
                {
                    "answer_type": "choice|free_text",
                    "prompt": "string",
                    "options": ["string", "string", "string", "string"],
                    "correct_option_index": 0,
                    "sample_answer": "string|null",
                }
            ]
        }
        prompt = (
            "Сгенерируй материал для конструктора теста преподавателя строго в JSON формате.\n"
            "Верни ТОЛЬКО JSON-объект, без markdown, пояснений и префиксов.\n\n"
            f"INPUT_JSON:\n{json.dumps(input_payload, ensure_ascii=False)}\n\n"
            f"OUTPUT_SCHEMA_JSON:\n{json.dumps(output_schema, ensure_ascii=False)}\n\n"
            "Требования:\n"
            f"- {difficulty_hint}\n"
            "- Все вопросы строго по теме INPUT_JSON.topic.\n"
            "- Каждый prompt должен явно ссылаться на тему из INPUT_JSON.topic (прямое упоминание темы/имени).\n"
            "- Вопросы не повторяются и не перефразируют один и тот же факт.\n"
            "- answer_type=choice: ровно 4 опции, одна корректная, correct_option_index в диапазоне 0..3.\n"
            "- answer_type=free_text: options=[], correct_option_index=null, sample_answer обязателен.\n"
            "- answer_type=choice: sample_answer=null.\n"
            "- Не использовать шаблонные/мета формулировки, например 'по теме выберите базовое утверждение'.\n"
            f"- Язык вопросов строго: {language_label}.\n"
            f"- Количество вопросов строго: {questions_count}.\n"
            f"- Минимум вопросов free_text: {free_text_target}.\n"
            "- Не используй markdown-блоки вида ```json.\n"
            "- Формулируй тексты максимально лаконично, без длинных объяснений.\n"
            "- Каждый вариант ответа: не длиннее 8 слов.\n"
        )

        teacher_generation_max_tokens = min(4000, max(1200, questions_count * 220))
        content = self._call_llm(
            prompt,
            audience="teacher",
            max_tokens=teacher_generation_max_tokens,
            timeout_seconds=45,
            temperature=0.2,
        )
        try:
            data = self._extract_json(content)
        except Exception:  # noqa: BLE001
            retry_prompt = (
                f"{prompt}\n\n"
                "Повтори генерацию в более компактном виде.\n"
                "Верни ТОЛЬКО JSON-объект без markdown и без текста до/после JSON.\n"
                "Сократи формулировки вариантов ответа до 3-6 слов."
            )
            retried = self._call_llm(
                retry_prompt,
                audience="teacher",
                max_tokens=teacher_generation_max_tokens,
                timeout_seconds=45,
                temperature=0.1,
            )
            data = self._extract_json(retried)
        raw_questions = data.get("questions", [])
        if not isinstance(raw_questions, list):
            raw_questions = []

        return self._sanitize_teacher_custom_material_questions(
            raw_questions=raw_questions,
            topic=topic,
            difficulty=difficulty,
            language=language,
            questions_count=questions_count,
            seed=seed,
            allow_fallback=False,
            require_topic_relevance=True,
        )

    def _generate_teacher_custom_material_fallback(
        self,
        *,
        topic: str,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        questions_count: int,
        seed: str,
    ) -> list[dict[str, Any]]:
        return self._sanitize_teacher_custom_material_questions(
            raw_questions=[],
            topic=topic,
            difficulty=difficulty,
            language=language,
            questions_count=questions_count,
            seed=seed,
            allow_fallback=True,
            require_topic_relevance=False,
        )

    def _sanitize_teacher_custom_material_questions(
        self,
        *,
        raw_questions: Sequence[dict[str, Any] | Any],
        topic: str,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        questions_count: int,
        seed: str,
        allow_fallback: bool = True,
        require_topic_relevance: bool = False,
    ) -> list[dict[str, Any]]:
        rng = random.Random(seed)
        normalized: list[dict[str, Any]] = []
        seen_prompt_keys: set[str] = set()
        free_text_target = {
            DifficultyLevel.easy: 0,
            DifficultyLevel.medium: max(1, questions_count // 5),
            DifficultyLevel.hard: max(2, questions_count // 3),
        }[difficulty]

        for raw in raw_questions:
            if not isinstance(raw, dict):
                continue

            prompt = re.sub(r"\s+", " ", str(raw.get("prompt", "")).strip())
            if len(prompt) < 8:
                continue
            prompt_key = self._semantic_prompt_key(prompt)
            if prompt_key in seen_prompt_keys:
                continue

            answer_type = "free_text" if str(raw.get("answer_type", "")).strip().lower() == "free_text" else "choice"
            if answer_type == "choice":
                raw_options = raw.get("options", [])
                options = [re.sub(r"^[A-H]\.\s*", "", str(item).strip()) for item in (raw_options if isinstance(raw_options, list) else [])]
                options = [item for item in options if item]
                dedup_options: list[str] = []
                seen_options: set[str] = set()
                for item in options:
                    key = item.lower()
                    if key in seen_options:
                        continue
                    seen_options.add(key)
                    dedup_options.append(item)
                options = dedup_options[:4]

                # Drop low-quality AI items and let deterministic topic-aware fallback build a better question.
                if len(options) < 4 or self._is_placeholder_teacher_options(options=options, topic=topic):
                    continue
                if require_topic_relevance and not self._is_teacher_material_related_to_topic(
                    topic=topic,
                    prompt=prompt,
                    options=options,
                    sample_answer=None,
                ):
                    continue

                try:
                    correct_option_index = int(raw.get("correct_option_index", 0))
                except Exception:  # noqa: BLE001
                    correct_option_index = 0
                if correct_option_index < 0 or correct_option_index > 3:
                    correct_option_index = 0

                normalized.append(
                    {
                        "prompt": prompt,
                        "answer_type": "choice",
                        "options": options,
                        "correct_option_index": correct_option_index,
                        "sample_answer": None,
                    }
                )
            else:
                sample_answer = re.sub(r"\s+", " ", str(raw.get("sample_answer", "")).strip())
                if len(sample_answer) < 3:
                    continue
                if require_topic_relevance and not self._is_teacher_material_related_to_topic(
                    topic=topic,
                    prompt=prompt,
                    options=[],
                    sample_answer=sample_answer,
                ):
                    continue
                normalized.append(
                    {
                        "prompt": prompt,
                        "answer_type": "free_text",
                        "options": [],
                        "correct_option_index": None,
                        "sample_answer": sample_answer,
                    }
                )

            seen_prompt_keys.add(prompt_key)
            if len(normalized) >= questions_count:
                break

        if not allow_fallback:
            return normalized[:questions_count]

        current_free_text_count = sum(1 for item in normalized if item["answer_type"] == "free_text")
        fallback_pool = self._build_teacher_custom_fallback_pool(
            topic=topic,
            difficulty=difficulty,
            language=language,
            questions_count=max(questions_count * 2, 24),
            seed=seed,
        )
        for payload in fallback_pool:
            if len(normalized) >= questions_count:
                break
            prompt_key = self._semantic_prompt_key(str(payload.get("prompt", "")))
            if not prompt_key or prompt_key in seen_prompt_keys:
                continue
            if payload.get("answer_type") == "free_text":
                if current_free_text_count >= free_text_target and len(normalized) + 1 <= questions_count:
                    # Prefer choice after free-text quota is reached.
                    continue
                current_free_text_count += 1
            seen_prompt_keys.add(prompt_key)
            normalized.append(payload)

        # Final tiny safety net without placeholder phrasing.
        idx = 0
        while len(normalized) < questions_count:
            idx += 1
            payload = self._build_teacher_custom_generic_question(
                topic=topic,
                language=language,
                index=idx,
                free_text=(
                    current_free_text_count < free_text_target
                    and (len(normalized) - current_free_text_count) >= 1
                ),
            )
            if payload["answer_type"] == "free_text":
                current_free_text_count += 1
            prompt_key = self._semantic_prompt_key(payload["prompt"])
            if prompt_key in seen_prompt_keys:
                continue
            seen_prompt_keys.add(prompt_key)
            normalized.append(payload)

        return normalized[:questions_count]

    def _is_teacher_material_related_to_topic(
        self,
        *,
        topic: str,
        prompt: str,
        options: Sequence[str],
        sample_answer: str | None,
    ) -> bool:
        topic_lower = topic.strip().lower()
        if not topic_lower:
            return True

        text = " ".join(
            [
                prompt or "",
                " ".join(options or []),
                sample_answer or "",
            ]
        ).lower()

        if topic_lower in text:
            return True

        aliases: list[str] = []
        if any(key in topic_lower for key in ("ооп", "oop")):
            aliases.extend(
                [
                    "объектно-ориент",
                    "object-oriented",
                    "object oriented",
                    "класс",
                    "инкапсуляц",
                    "наследован",
                    "полиморф",
                ]
            )
        for token in self._topic_tokens(topic):
            aliases.append(token)

        normalized_aliases: list[str] = []
        for alias in aliases:
            item = alias.strip().lower()
            if len(item) < 2 or item in normalized_aliases:
                continue
            normalized_aliases.append(item)

        if not normalized_aliases:
            return True

        return any(alias in text for alias in normalized_aliases)

    @staticmethod
    def _topic_tokens(topic: str) -> list[str]:
        tokens = re.findall(r"[a-zа-яәіңғүұқөһ0-9]+", topic.lower())
        output: list[str] = []
        for token in tokens:
            if len(token) < 2:
                continue
            if token in output:
                continue
            output.append(token)
        return output

    def _is_placeholder_teacher_options(self, *, options: Sequence[str], topic: str) -> bool:
        if not options:
            return True
        topic_lower = topic.strip().lower()
        generic_patterns = (
            "верное определение по теме",
            "причина, связанная с темой",
            "пример практического применения темы",
            "типичная ошибка в теме",
            "ключевой факт по теме",
            "утверждение о последствиях",
            "сравнение подходов в теме",
            "обобщающий вывод по теме",
            "тақырыбы бойынша дұрыс анықтама",
            "тақырыбына қатысты себеп",
            "практикалық мысалы",
        )
        hit_count = 0
        for option in options:
            value = str(option).strip().lower()
            if not value:
                continue
            if any(pattern in value for pattern in generic_patterns):
                hit_count += 1
            if topic_lower and topic_lower in value and len(value) < max(40, len(topic_lower) + 24):
                hit_count += 1
        return hit_count >= max(2, len(options) // 2)

    def _build_teacher_custom_fallback_pool(
        self,
        *,
        topic: str,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        questions_count: int,
        seed: str,
    ) -> list[dict[str, Any]]:
        rng = random.Random(f"{seed}-teacher-fallback")
        topic_tokens = self._topic_tokens(topic)
        lang_key = "ru" if language == PreferredLanguage.ru else "kz"
        matched: list[tuple[float, str, dict[str, Any]]] = []
        subject_scores: dict[str, float] = {}

        # Curated topic packs for high-value custom themes (e.g., ООП).
        curated = self._teacher_topic_curated_facts(topic=topic, language=language)
        for item in curated:
            matched.append((1000.0, "информатика", item))
            subject_scores["информатика"] = subject_scores.get("информатика", 0.0) + 1000.0

        for subject_key, facts in SUBJECT_FACT_BANK.items():
            for fact in facts:
                prompt = str(fact.get(f"prompt_{lang_key}", "")).strip()
                fact_topic = str(fact.get(f"topic_{lang_key}", "")).strip()
                if not prompt:
                    continue
                haystack = f"{fact_topic} {prompt}".lower()
                score = 0.0
                topic_lower = topic.lower().strip()
                if topic_lower and (topic_lower in haystack or haystack in topic_lower):
                    score += 8.0
                for token in topic_tokens:
                    if token in haystack:
                        score += 1.8
                if score <= 0:
                    continue
                matched.append((score, subject_key, fact))
                subject_scores[subject_key] = subject_scores.get(subject_key, 0.0) + score

        matched.sort(key=lambda pair: pair[0], reverse=True)
        if matched:
            top: list[tuple[float, str, dict[str, Any]]] = matched[: max(questions_count * 3, 32)]
            # If exact topic matches are sparse, continue from the best matched subject.
            best_subject = max(subject_scores.items(), key=lambda item: item[1])[0] if subject_scores else None
            if best_subject and len(top) < max(questions_count * 2, 12):
                for fact in SUBJECT_FACT_BANK.get(best_subject, []):
                    if any(existing_fact is fact for _, _, existing_fact in top):
                        continue
                    top.append((0.2, best_subject, fact))
                    if len(top) >= max(questions_count * 4, 24):
                        break
        else:
            # No direct matches: take broad school facts from multiple subjects to avoid empty placeholders.
            top: list[tuple[float, str, dict[str, Any]]] = []
            for subject_key, facts in SUBJECT_FACT_BANK.items():
                for fact in facts[:3]:
                    top.append((0.1, subject_key, fact))
            rng.shuffle(top)

        pool: list[dict[str, Any]] = []
        seen_prompts: set[str] = set()
        for _, _, fact in top:
            prompt = str(fact.get(f"prompt_{lang_key}", "")).strip()
            options = [str(item).strip() for item in (fact.get(f"options_{lang_key}", []) or []) if str(item).strip()]
            correct_ids = [int(item) for item in (fact.get("correct_option_ids", []) or []) if isinstance(item, int)]
            correct_option_index = correct_ids[0] if correct_ids else 0
            if not prompt or len(options) < 4 or correct_option_index < 0 or correct_option_index >= len(options):
                continue
            prompt_key = self._semantic_prompt_key(prompt)
            if prompt_key in seen_prompts:
                continue
            seen_prompts.add(prompt_key)
            pool.append(
                {
                    "prompt": prompt,
                    "answer_type": "choice",
                    "options": options[:4],
                    "correct_option_index": int(correct_option_index),
                    "sample_answer": None,
                }
            )

            # Add free-text companions for medium/hard difficulties.
            if difficulty != DifficultyLevel.easy:
                fact_topic = str(fact.get(f"topic_{lang_key}", "")).strip() or topic
                explanation = str(fact.get(f"explanation_{lang_key}", "")).strip()
                free_prompt = (
                    f"Кратко объясните ключевое правило темы «{fact_topic}» и приведите 1 пример."
                    if language == PreferredLanguage.ru
                    else f"«{fact_topic}» тақырыбының негізгі ережесін қысқаша түсіндіріп, 1 мысал келтіріңіз."
                )
                free_key = self._semantic_prompt_key(free_prompt)
                if free_key not in seen_prompts:
                    seen_prompts.add(free_key)
                    pool.append(
                        {
                            "prompt": free_prompt,
                            "answer_type": "free_text",
                            "options": [],
                            "correct_option_index": None,
                            "sample_answer": explanation or (
                                f"Ключевое правило темы «{fact_topic}» объяснено корректно."
                                if language == PreferredLanguage.ru
                                else f"«{fact_topic}» тақырыбының негізгі ережесі дұрыс түсіндірілген."
                            ),
                        }
                    )

            if len(pool) >= questions_count:
                break

        rng.shuffle(pool)
        return pool

    def _teacher_topic_curated_facts(self, *, topic: str, language: PreferredLanguage) -> list[dict[str, Any]]:
        topic_lower = topic.lower()
        oop_keywords = ("ооп", "oop", "object oriented", "объектно-ориент", "класс", "инкапсуляц", "полиморф")
        if not any(key in topic_lower for key in oop_keywords):
            return []

        if language == PreferredLanguage.ru:
            return [
                {
                    "topic_ru": "ООП",
                    "prompt_ru": "Что означает аббревиатура ООП?",
                    "options_ru": [
                        "Объектно-ориентированное программирование",
                        "Объединённая обработка процессов",
                        "Основной операционный протокол",
                        "Общая оптимизация памяти",
                    ],
                    "correct_option_ids": [0],
                    "explanation_ru": "ООП — это объектно-ориентированная парадигма программирования.",
                },
                {
                    "topic_ru": "ООП",
                    "prompt_ru": "Какой принцип ООП скрывает внутреннюю реализацию объекта?",
                    "options_ru": ["Инкапсуляция", "Наследование", "Полиморфизм", "Рекурсия"],
                    "correct_option_ids": [0],
                    "explanation_ru": "Инкапсуляция ограничивает прямой доступ к внутреннему состоянию.",
                },
                {
                    "topic_ru": "ООП",
                    "prompt_ru": "Что в ООП обычно описывает структура класса?",
                    "options_ru": ["Поля и методы", "IP-адрес и маску подсети", "Только комментарии", "Список библиотек ОС"],
                    "correct_option_ids": [0],
                    "explanation_ru": "Класс обычно содержит данные (поля) и поведение (методы).",
                },
                {
                    "topic_ru": "ООП",
                    "prompt_ru": "Что демонстрирует полиморфизм в ООП?",
                    "options_ru": [
                        "Один интерфейс — разные реализации",
                        "Обязательное использование глобальных переменных",
                        "Запрет переопределения методов",
                        "Только работу с файлами",
                    ],
                    "correct_option_ids": [0],
                    "explanation_ru": "Полиморфизм позволяет вызывать разные реализации через общий интерфейс.",
                },
                {
                    "topic_ru": "ООП",
                    "prompt_ru": "Что такое наследование в ООП?",
                    "options_ru": [
                        "Создание нового класса на основе существующего",
                        "Преобразование типов без правил",
                        "Удаление всех методов из класса",
                        "Шифрование исходного кода",
                    ],
                    "correct_option_ids": [0],
                    "explanation_ru": "Наследование позволяет переиспользовать и расширять поведение базового класса.",
                },
            ]

        return [
            {
                "topic_kz": "ООП",
                "prompt_kz": "ООП қысқартуы нені білдіреді?",
                "options_kz": [
                    "Объектіге бағытталған бағдарламалау",
                    "Орталық операциялық процесс",
                    "Ортақ оңтайландыру пакеті",
                    "Объектіні өңдеу протоколы",
                ],
                "correct_option_ids": [0],
                "explanation_kz": "ООП — объектіге бағытталған бағдарламалау парадигмасы.",
            },
            {
                "topic_kz": "ООП",
                "prompt_kz": "ООП-та объектінің ішкі жүзеге асуын қай қағида жасырады?",
                "options_kz": ["Инкапсуляция", "Мұрагерлік", "Полиморфизм", "Итерация"],
                "correct_option_ids": [0],
                "explanation_kz": "Инкапсуляция объектінің ішкі күйін тікелей өзгертуді шектейді.",
            },
            {
                "topic_kz": "ООП",
                "prompt_kz": "Сынып (class) әдетте нені сипаттайды?",
                "options_kz": ["Өрістер мен әдістерді", "Тек IP адресті", "Тек түсіндірме мәтінді", "Тек файл пішімін"],
                "correct_option_ids": [0],
                "explanation_kz": "Сынып деректерді (өрістер) және әрекеттерді (әдістер) біріктіреді.",
            },
        ]

    def _build_teacher_custom_generic_question(
        self,
        *,
        topic: str,
        language: PreferredLanguage,
        index: int,
        free_text: bool,
    ) -> dict[str, Any]:
        if free_text:
            prompt = (
                f"Объясните ключевую идею темы «{topic}» и приведите один практический пример."
                if language == PreferredLanguage.ru
                else f"«{topic}» тақырыбының негізгі идеясын түсіндіріп, бір практикалық мысал келтіріңіз."
            )
            answer = (
                f"Корректно объяснена суть темы «{topic}» и приведён релевантный пример."
                if language == PreferredLanguage.ru
                else f"«{topic}» тақырыбының мәні дұрыс түсіндіріліп, орынды мысал келтірілген."
            )
            return {
                "prompt": prompt,
                "answer_type": "free_text",
                "options": [],
                "correct_option_index": None,
                "sample_answer": answer,
            }

        if language == PreferredLanguage.ru:
            prompt = f"Какое утверждение о теме «{topic}» является наиболее корректным?"
            options = [
                f"Утверждение {index}: отражает ключевое правило темы «{topic}».",
                f"Утверждение {index}: содержит подмену понятий и неточный термин.",
                f"Утверждение {index}: игнорирует основное условие применения.",
                f"Утверждение {index}: противоречит базовому определению темы.",
            ]
        else:
            prompt = f"«{topic}» тақырыбы туралы ең дұрыс тұжырым қайсы?"
            options = [
                f"{index}-тұжырым: «{topic}» тақырыбының негізгі ережесін дұрыс береді.",
                f"{index}-тұжырым: ұғымдарды шатастырып, терминді қате қолданады.",
                f"{index}-тұжырым: қолдану шартын ескермейді.",
                f"{index}-тұжырым: негізгі анықтамаға қайшы келеді.",
            ]
        return {
            "prompt": prompt,
            "answer_type": "choice",
            "options": options,
            "correct_option_index": 0,
            "sample_answer": None,
        }

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
        def ensure_exact_count(candidate_questions: Sequence[GeneratedQuestionPayload]) -> GeneratedTestPayload:
            merged = self._merge_unique_questions(
                groups=[list(candidate_questions)],
                target_count=num_questions,
            )
            if len(merged) >= num_questions:
                return GeneratedTestPayload(seed=seed, questions=merged[:num_questions])

            missing = num_questions - len(merged)
            topup = self._generate_test_mock(
                subject=subject,
                difficulty=difficulty,
                language=language,
                mode=mode,
                num_questions=max(missing + 2, missing * 2),
                seed=f"{seed}-deterministic-topup",
                focus_topics=focus_topics,
            )
            merged = self._merge_unique_questions(
                groups=[merged, topup.questions],
                target_count=num_questions,
            )
            return GeneratedTestPayload(seed=seed, questions=merged[:num_questions])

        if self._llm_is_configured(audience="student"):
            try:
                return self._generate_test_llm(
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    mode=mode,
                    num_questions=num_questions,
                    seed=seed,
                    focus_topics=focus_topics,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM generation failed, fallback to validated library: %s", exc)

        fallback_questions = self.generate_library_only_questions(
            subject=subject,
            language=language,
            mode=mode,
            num_questions=num_questions,
            seed=f"{seed}-library-fallback",
            difficulty_order=[difficulty, DifficultyLevel.medium, DifficultyLevel.easy, DifficultyLevel.hard],
        )
        if fallback_questions:
            return ensure_exact_count(fallback_questions)

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

    def _generate_test_llm(
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
- Не используй мета-формулировки: "по теме ... выберите базовое утверждение", "найдите корректный факт", "опирайтесь на школьный курс".
- Каждый вопрос должен быть конкретным и предметным (термин, правило, вычисление, причинно-следственная связь, факт).
- Не превращай явно тестовые формулировки ("в каком слове", "выберите синоним/антоним", "правильная форма слова") в short_text/oral_answer.
- Верни ровно {num_questions} вопросов.
{hard_free_rule}
""".strip()

        content = self._call_llm(prompt, audience="student")
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

    def _generate_recommendation_llm(
        self,
        *,
        subject: Subject,
        language: PreferredLanguage,
        weak_topics: list[str],
    ) -> RecommendationPayload:
        subject_name = subject.name_ru if language == PreferredLanguage.ru else subject.name_kz
        language_name = "русский" if language == PreferredLanguage.ru else "казахский"
        language_hard_rule = (
            "Весь текст должен быть строго на русском языке."
            if language == PreferredLanguage.ru
            else "Весь текст должен быть строго на казахском языке. Не используй русский язык."
        )
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
- Язык: {language_name}
- {language_hard_rule}
- Дай краткий совет и ровно 5 дополнительных заданий по слабым темам.
""".strip()

        content = self._call_llm(prompt, audience="student")
        data = self._extract_json(content)
        tasks = data.get("generated_tasks", [])[:5]
        if len(tasks) < 5:
            raise ValueError("Недостаточно сгенерированных заданий")
        advice = str(data.get("advice_text", "")).strip()
        if not advice:
            raise ValueError("Пустой совет в рекомендациях")
        if not self._looks_like_target_language(text=advice, language=language):
            raise ValueError(f"Модель вернула рекомендации не на целевом языке: {language.value}")

        validated_tasks: list[dict[str, str]] = []
        for raw_task in tasks:
            if not isinstance(raw_task, dict):
                continue
            topic = str(raw_task.get("topic", "")).strip()
            task_text = str(raw_task.get("task", "")).strip()
            difficulty = str(raw_task.get("difficulty", "adaptive")).strip() or "adaptive"
            if not topic or not task_text:
                continue
            if not self._looks_like_target_language(text=f"{topic}. {task_text}", language=language):
                raise ValueError(f"Модель вернула задания не на целевом языке: {language.value}")
            validated_tasks.append({"topic": topic, "task": task_text, "difficulty": difficulty})

        if len(validated_tasks) < 5:
            raise ValueError("Недостаточно валидных заданий после проверки языка")

        return RecommendationPayload(advice_text=advice, generated_tasks=validated_tasks[:5])

    @staticmethod
    def _looks_like_target_language(*, text: str, language: PreferredLanguage) -> bool:
        normalized = f" {str(text or '').lower()} "
        if not normalized.strip():
            return False

        # Kazakh has distinctive letters and common markers. If none are present and
        # Russian markers dominate, treat as wrong language and fallback to deterministic templates.
        if language == PreferredLanguage.kz:
            kz_letters = ("ә", "і", "ң", "ғ", "ү", "ұ", "қ", "ө", "һ")
            kz_markers = (
                " және ",
                " үшін ",
                " бойынша ",
                " тақырып ",
                " сұрақ ",
                " қайталау ",
                " ұсыныс ",
                " нәтиже ",
                " пән ",
                " тапсырма ",
            )
            ru_markers = (
                " для ",
                " и ",
                " по ",
                " тема ",
                " вопрос ",
                " повтор",
                " рекомендац",
                " результат ",
                " предмет ",
                " задание ",
            )
            has_kz_signal = any(letter in normalized for letter in kz_letters) or any(marker in normalized for marker in kz_markers)
            has_ru_signal = any(marker in normalized for marker in ru_markers)
            if has_kz_signal:
                return True
            return not has_ru_signal

        # For Russian recommendations just require cyrillic and avoid obvious kazakh-only markers dominance.
        ru_cyrillic = re.search(r"[а-яё]", normalized) is not None
        kz_only_letters = ("ә", "і", "ң", "ғ", "ү", "ұ", "қ", "ө", "һ")
        kz_only_hits = sum(1 for letter in kz_only_letters if letter in normalized)
        return ru_cyrillic and kz_only_hits <= 1

    def _call_llm(
        self,
        prompt: str,
        *,
        audience: str,
        max_tokens: int | None = None,
        timeout_seconds: int = 35,
        temperature: float = 0.7,
    ) -> str:
        provider_name = self._teacher_provider_name() if audience == "teacher" else self._student_provider_name()
        effective_timeout = max(5, int(timeout_seconds))
        if provider_name == "openai":
            effective_timeout = max(effective_timeout, int(settings.openai_timeout_seconds))
        try:
            return llm_chat(
                system_prompt="You are a strict JSON generator for exam platforms.",
                user_prompt=prompt,
                temperature=temperature,
                timeout_seconds=effective_timeout,
                provider_name=provider_name,
                max_tokens=max_tokens,
                audience=audience,
            )
        except LLMProviderError:
            raise

    @staticmethod
    def _is_non_retryable_llm_error(exc: Exception) -> bool:
        if isinstance(exc, LLMProviderError):
            return not getattr(exc, "retryable", True)
        return False

    @staticmethod
    def _format_teacher_llm_error(exc: Exception) -> str:
        raw = str(exc).strip()
        normalized = raw.lower()
        if "model_not_found" in normalized or "must be verified to use the model" in normalized:
            return (
                "Модель OpenAI недоступна для вашего аккаунта. "
                "Проверьте верификацию организации или укажите резервную модель "
                "(например, OPENAI_MODEL=gpt-4.1-mini)."
            )
        if "api error 429" in normalized or "quota exceeded" in normalized or "resource_exhausted" in normalized:
            return (
                "Превышена квота OpenAI API. Подождите немного и повторите запрос, "
                "либо увеличьте лимиты/план OpenAI."
            )
        if "insufficient_quota" in normalized or "credit balance is too low" in normalized:
            return (
                "Недостаточно квоты/баланса OpenAI аккаунта. "
                "Пополните баланс или проверьте активный billing plan."
            )
        if "api key is invalid" in normalized or "invalid_api_key" in normalized or "authentication" in normalized:
            return "Неверный ключ OpenAI API. Проверьте OPENAI_API_KEY_TEACHER."
        return raw

    @staticmethod
    def _extract_json(content: str) -> dict:
        raw = (content or "").strip()
        if not raw:
            raise ValueError("Пустой ответ модели (ожидался JSON).")

        candidates: list[str] = [raw]
        # 1) Remove wrapping fence when the whole string is fenced.
        fenced_wrapped = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
        if fenced_wrapped != raw:
            candidates.append(fenced_wrapped)
        # 2) Extract fenced block from mixed text.
        fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE)
        if fenced_match:
            fenced_inner = (fenced_match.group(1) or "").strip()
            if fenced_inner:
                candidates.append(fenced_inner)

        # Try direct parse first (object or array root).
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
                if isinstance(parsed, list):
                    return {"questions": parsed}
            except json.JSONDecodeError:
                pass

        # Try extracting first object or array from free text.
        for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
            for candidate in candidates:
                match = re.search(pattern, candidate)
                if not match:
                    continue
                fragment = match.group(0)
                try:
                    parsed = json.loads(fragment)
                    if isinstance(parsed, dict):
                        return parsed
                    if isinstance(parsed, list):
                        return {"questions": parsed}
                except json.JSONDecodeError:
                    continue

        snippet = raw[:220].replace("\n", " ")
        raise ValueError(f"Модель вернула не-JSON ответ: {snippet}")

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

        # Preserve already natural stems (questions/commands) to avoid noisy paraphrases.
        base_lower = re.sub(r"\s+", " ", base.lower()).strip()
        protected_starts_ru = (
            "в каком", "в какой", "в какие", "какая", "какой", "какие", "как", "чему", "сколько",
            "решите", "найдите", "укажите", "выберите", "перед каким", "определите", "сопоставьте", "объясните",
        )
        protected_starts_kz = (
            "қай", "қандай", "қалай", "қанша", "теңдеуді шеш", "табыңыз", "көрсетіңіз",
            "таңдаңыз", "анықтаңыз", "сәйкестендіріңіз", "түсіндіріңіз",
        )
        if base.endswith("?"):
            return base
        if language == PreferredLanguage.ru and base_lower.startswith(protected_starts_ru):
            return base
        if language == PreferredLanguage.kz and base_lower.startswith(protected_starts_kz):
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
        difficulty_order: list[DifficultyLevel] = []
        for item in (difficulty, DifficultyLevel.medium, DifficultyLevel.easy, DifficultyLevel.hard):
            if item not in difficulty_order:
                difficulty_order.append(item)

        # Build local library pool only; do not trigger external LLM here.
        return self.generate_library_only_questions(
            subject=subject,
            language=language,
            mode=mode,
            num_questions=self.LIBRARY_QUESTIONS_PER_COMBINATION,
            seed=f"library::{subject.id}::{language.value}::{difficulty.value}::{mode.value}",
            difficulty_order=difficulty_order,
        )

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
            if question.type != QuestionType.single_choice:
                continue
            if not self._can_convert_choice_to_short_text(question=question):
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

        # Do not fabricate multi_choice by converting single_choice with synthetic
        # additional correct answers: it reduces question quality.
        return

    @staticmethod
    def _can_convert_choice_to_short_text(*, question: GeneratedQuestionPayload) -> bool:
        prompt = re.sub(r"\s+", " ", str(question.prompt or "").strip().lower())
        topic = re.sub(r"\s+", " ", str((question.explanation_json or {}).get("topic", "")).strip().lower())

        blocked_prompt_ru = [
            r"\bв каком слове\b",
            r"\bв каком предложении\b",
            r"\bперед каким союзом\b",
            r"\bвыберите синоним\b",
            r"\bвыберите антоним\b",
            r"\bвыберите верные утверждения\b",
            r"\bкак правильно написать\b",
            r"\bкакая часть речи\b",
            r"\bвыберите правильную форму\b",
        ]
        blocked_prompt_kz = [
            r"\bқай сөзде\b",
            r"\bқай сөйлемде\b",
            r"\bқандай жалғаулық\b",
            r"\bсиноним\b",
            r"\bантоним\b",
            r"\bдұрыс жаз\b",
            r"\bқай сөз табы\b",
            r"\bдұрыс форманы таңда\b",
        ]
        blocked_topic_parts = (
            "орфограф", "пунктуац", "лексик", "морфолог", "синтакс", "фонетик",
            "граммат", "grammar", "tenses", "spelling", "vocabulary",
        )

        if any(re.search(pattern, prompt) for pattern in [*blocked_prompt_ru, *blocked_prompt_kz]):
            return False
        if any(part in topic for part in blocked_topic_parts):
            return False

        options = list((question.options_json or {}).get("options", []) or [])
        option_texts: list[str] = []
        for item in options:
            if isinstance(item, dict):
                text = str(item.get("text", "")).strip()
            else:
                text = str(item).strip()
            if text:
                option_texts.append(re.sub(r"^\s*[A-ZА-Я]\s*[\).\:\-]\s*", "", text))

        # Lexical selector questions are poor candidates for free-text conversion.
        if option_texts:
            short_items = sum(1 for text in option_texts if len(text.split()) <= 4)
            if short_items / len(option_texts) >= 0.8:
                return False

        return True

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
        normalized_prompt = re.sub(
            r"^\s*(выберите (правильный|корректный|наиболее подходящий|наиболее точный) "
            r"(ответ|вариант)( ответа)?\s*:\s*)",
            "",
            normalized_prompt,
            flags=re.IGNORECASE,
        )
        normalized_prompt = re.sub(
            r"^\s*(укажите (верный|точный|правильный) (вариант|ответ)\s*:\s*)",
            "",
            normalized_prompt,
            flags=re.IGNORECASE,
        )
        normalized_prompt = re.sub(
            r"^\s*(дұрыс (жауапты|нұсқаны) (таңдаңыз|көрсетіңіз)\s*:\s*)",
            "",
            normalized_prompt,
            flags=re.IGNORECASE,
        )
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
            r"^по предмету\s+«[^»]+»\s+выполните задание по теме",
            r"выберите верное базовое утверждение",
            r"сопоставьте термин и смысл",
            r"найдите корректный факт по теме",
            r"используйте базовое правило темы",
            r"опирайтесь на школьный курс",
            r"выберите наиболее подходящий вариант:\s*выберите",
            r"выберите правильный ответ:\s*выберите",
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

    @staticmethod
    def _semantic_prompt_key(prompt: str) -> str:
        normalized = AIService._prompt_key(prompt)
        tokens = re.findall(r"[a-zа-яәіңғүұқөһ0-9]+", normalized)
        if not tokens:
            return normalized

        stopwords = {
            "и", "или", "в", "во", "на", "по", "к", "с", "со", "у", "о", "об", "за", "от", "до",
            "что", "это", "как", "какой", "какая", "какие", "каком", "чему", "сколько", "нужно",
            "найдите", "выберите", "укажите", "определите", "решите", "имеет", "имеют", "есть",
            "дұрыс", "жауап", "таңдаңыз", "көрсетіңіз", "анықтаңыз", "табыңыз",
        }
        cleaned: list[str] = []
        for token in tokens:
            if len(token) <= 1 or token in stopwords:
                continue
            base = token
            for suffix in (
                "иями", "ями", "ами", "ого", "ему", "ому", "ыми", "ими",
                "ение", "ения", "ния", "ние", "ости", "ость",
                "ый", "ий", "ой", "ая", "ое", "ые",
                "ах", "ях", "ом", "ем", "ам", "ям", "ов", "ев",
                "ия", "ие", "лар", "лер", "ы", "и", "а", "я",
            ):
                if base.endswith(suffix) and len(base) - len(suffix) >= 4:
                    base = base[: -len(suffix)]
                    break
            cleaned.append(base or token)
        if not cleaned:
            return normalized
        return " ".join(sorted(set(cleaned)))

    def _question_uniqueness_key(self, question: GeneratedQuestionPayload) -> str:
        explanation = dict(question.explanation_json or {})
        base_key = str(explanation.get("library_base_key", "")).strip().lower()
        if base_key:
            return f"base::{self._semantic_prompt_key(base_key)}"

        template_key = str(explanation.get("library_template_key", "")).strip().lower()
        if template_key:
            return f"tpl::{self._semantic_prompt_key(template_key)}"

        content_key = str(explanation.get("library_content_key", "")).strip().lower()
        if content_key:
            return f"cnt::{self._semantic_prompt_key(content_key)}"

        return f"pr::{self._semantic_prompt_key(question.prompt)}"

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
