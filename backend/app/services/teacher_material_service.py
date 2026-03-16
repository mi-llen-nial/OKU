from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.models import DifficultyLevel, PreferredLanguage, TestMode
from app.schemas.teacher_tests import TeacherCustomMaterialQuestion
from app.services.llm import LLMProviderError, is_llm_provider_configured, llm_chat
from app.services.question_quality import validate_question_payload


class MaterialQualityError(ValueError):
    pass


class MaterialProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class TeacherMaterialResult:
    questions: list[TeacherCustomMaterialQuestion]
    rejected_count: int


@dataclass(frozen=True)
class LLMRequestProfile:
    temperature: float
    timeout_seconds: int
    max_tokens: int


class TeacherMaterialService:
    def generate_and_validate(
        self,
        *,
        topic: str,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        questions_count: int,
        user_id: int,
    ) -> TeacherMaterialResult:
        if not is_llm_provider_configured(audience="teacher"):
            raise MaterialProviderError("MATERIAL_PROVIDER_FAILED: LLM provider is not configured for teacher generation.")

        normalized_topic = str(topic).strip()
        requested = max(1, int(questions_count))
        accepted: list[TeacherCustomMaterialQuestion] = []
        rejected = 0
        seen_prompt_keys: set[str] = set()
        last_quality_error: str | None = None
        last_provider_error: str | None = None
        successful_batches = 0

        max_calls = 8 if difficulty == DifficultyLevel.hard else 6
        for attempt in range(1, max_calls + 1):
            remaining = max(0, requested - len(accepted))
            if remaining <= 0:
                break
            # Ask for a slightly bigger batch than remaining so validation can reject low-quality items.
            oversample_ratio = 0.6 if difficulty == DifficultyLevel.hard else 0.4
            oversample = max(3 if difficulty == DifficultyLevel.hard else 2, round(remaining * oversample_ratio))
            batch_size = min(16, remaining + oversample)
            try:
                llm_items = self._generate_raw_with_llm(
                    topic=normalized_topic,
                    difficulty=difficulty,
                    language=language,
                    questions_count=batch_size,
                    target_questions_count=requested,
                    user_id=user_id,
                    attempt=attempt,
                )
                successful_batches += 1
            except LLMProviderError as exc:
                last_provider_error = str(exc)
                continue
            except MaterialProviderError as exc:
                last_provider_error = str(exc)
                continue
            except Exception as exc:  # noqa: BLE001
                last_provider_error = str(exc)
                continue

            before_count = len(accepted)
            accepted, rejected = self._validate_batch(
                topic=normalized_topic,
                difficulty=difficulty,
                language=language,
                questions_count=requested,
                raw_items=llm_items,
                seen_prompt_keys=seen_prompt_keys,
                accepted_prefix=accepted,
                rejected_prefix=rejected,
            )
            if len(accepted) == before_count:
                last_quality_error = "LLM returned batch without valid questions."
            if len(accepted) >= requested:
                return TeacherMaterialResult(
                    questions=self._postprocess_questions(accepted[:requested], difficulty=difficulty),
                    rejected_count=rejected,
                )

        if accepted:
            return TeacherMaterialResult(
                questions=self._postprocess_questions(accepted[:requested], difficulty=difficulty),
                rejected_count=rejected,
            )

        if successful_batches == 0:
            details = last_provider_error or "LLM provider returned no successful response."
            raise MaterialProviderError(f"MATERIAL_PROVIDER_FAILED: {details}")

        details = last_quality_error or "LLM returned no valid questions."
        raise MaterialQualityError(f"MATERIAL_QUALITY_FAILED: {details}")

    def _generate_raw_with_llm(
        self,
        *,
        topic: str,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        questions_count: int,
        target_questions_count: int,
        user_id: int,
        attempt: int,
    ) -> list[dict[str, Any]]:
        language_label = "RU" if language == PreferredLanguage.ru else "KZ"
        blueprint = self._build_blueprint(
            topic=topic,
            difficulty=difficulty,
            language=language,
            batch_size=questions_count,
        )
        difficulty_rubric = self._difficulty_rubric(difficulty=difficulty)
        option_requirement = (
            "Если answer_type=choice: в КАЖДОМ вопросе строго 6 или 8 вариантов ответа."
            if difficulty == DifficultyLevel.hard
            else "Если answer_type=choice: в КАЖДОМ вопросе минимум 4 варианта ответа."
        )
        system_prompt = (
            "Ты помощник преподавателя. Сгенерируй валидный набор вопросов для теста. "
            "Отвечай строго JSON-объектом без markdown и комментариев. "
            'Формат: {"questions":[{"answer_type":"choice|free_text","prompt":"...","options":[...],'
            '"correct_option_index":0,"sample_answer":"...","topic":"...","explanation":"..."}]}. '
            f"{option_requirement} "
            "Для answer_type=choice: ровно один правильный индекс. "
            "Для answer_type=free_text: options пустой массив, sample_answer обязателен. "
            "Запрещены пустые или шаблонные формулировки. "
            "Сложность соблюдай строго согласно рубрике."
        )
        user_prompt = (
            f"Тема: {topic}\n"
            f"Сложность: {difficulty.value}\n"
            f"Язык: {language_label}\n"
            f"Требуемый размер итогового теста: {target_questions_count}\n"
            f"Сгенерировать в этой пачке: {questions_count}\n"
            f"Попытка: {attempt}\n"
            f"User id: {user_id}\n"
            "Требования:\n"
            f"0) Рубрика сложности:\n{difficulty_rubric}\n"
            "1) Вопросы должны быть строго по теме.\n"
            "2) Без дублей формулировок.\n"
            "3) Никаких placeholders.\n"
            "4) Для choice не используй варианты 'все ответы верны' или 'нет правильного ответа'.\n"
            "5) В поле topic у каждого вопроса используй формат '<основная тема>: <подтема>'.\n"
            "6) Если тема короткая (одно слово), раскрой ее через разные подтемы.\n"
            "7) Держи баланс типов вопросов по плану ниже.\n"
            f"{blueprint}\n"
            "8) Приоритет answer_type=choice. free_text допускается, но не более 30% в пачке.\n"
            "9) Для choice распределяй correct_option_index равномерно по индексам 0,1,2,3 в пределах пачки."
        )
        profile = self._build_llm_request_profile(
            difficulty=difficulty,
            batch_size=questions_count,
            attempt=attempt,
        )
        raw = llm_chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=profile.temperature,
            timeout_seconds=profile.timeout_seconds,
            max_tokens=profile.max_tokens,
            audience="teacher",
        )
        payload = self._extract_json(raw)
        questions = payload.get("questions")
        if not isinstance(questions, list):
            raise MaterialQualityError("MATERIAL_QUALITY_FAILED: LLM response must include `questions` array.")
        return [item for item in questions if isinstance(item, dict)]

    def _extract_json(self, content: str) -> dict[str, Any]:
        normalized = str(content or "").strip()
        if not normalized:
            raise MaterialQualityError("MATERIAL_QUALITY_FAILED: empty LLM response.")
        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            pass

        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", normalized, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            return json.loads(fenced.group(1))

        start = normalized.find("{")
        end = normalized.rfind("}")
        if start >= 0 and end > start:
            return json.loads(normalized[start : end + 1])
        raise MaterialQualityError("MATERIAL_QUALITY_FAILED: non-JSON LLM response.")

    def _validate_batch(
        self,
        *,
        topic: str,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        questions_count: int,
        raw_items: list[dict[str, Any]],
        seen_prompt_keys: set[str],
        accepted_prefix: list[TeacherCustomMaterialQuestion],
        rejected_prefix: int,
    ) -> tuple[list[TeacherCustomMaterialQuestion], int]:
        accepted = list(accepted_prefix)
        rejected = int(rejected_prefix)

        for raw in raw_items:
            converted = self._normalize_raw_question(
                raw,
                topic_fallback=topic,
                difficulty=difficulty,
            )
            if not converted:
                rejected += 1
                continue

            prompt = str(converted.get("prompt", "")).strip()
            prompt_key = _prompt_key(prompt)
            if prompt_key in seen_prompt_keys:
                rejected += 1
                continue
            if not self._is_topic_relevant(
                topic=topic,
                prompt=prompt,
                sample_answer=str(converted.get("sample_answer", "")),
                explanation=str(converted.get("explanation", "")),
                topic_tags=converted.get("topic_tags"),
            ):
                rejected += 1
                continue

            validation = validate_question_payload(
                payload=converted,
                language=language,
                mode=TestMode.text,
                difficulty=difficulty,
            )
            if not validation.is_valid:
                rejected += 1
                continue

            normalized = validation.payload
            question = self._to_schema_item(normalized)
            if question is None:
                rejected += 1
                continue

            accepted.append(question)
            seen_prompt_keys.add(prompt_key)
            if len(accepted) >= questions_count:
                break

        return accepted, rejected

    def _normalize_raw_question(
        self,
        raw: dict[str, Any],
        *,
        topic_fallback: str,
        difficulty: DifficultyLevel,
    ) -> dict[str, Any] | None:
        prompt = str(raw.get("prompt", "")).strip()
        if not prompt:
            return None
        topic_value = str(raw.get("topic") or "").strip() or str(topic_fallback).strip()
        topic_tags = [topic_value] if topic_value else []

        answer_type = str(raw.get("answer_type", "choice")).strip().lower()
        if answer_type in {"free_text", "short_text", "text"}:
            sample_answer = str(raw.get("sample_answer", "")).strip()
            if not sample_answer:
                return None
            return {
                "type": "short_text",
                "prompt": prompt,
                "sample_answer": sample_answer,
                "keywords": [str(item).strip() for item in (raw.get("keywords") or []) if str(item).strip()],
                "topic_tags": topic_tags,
                "explanation": str(raw.get("explanation") or sample_answer).strip(),
            }

        options = [str(option).strip() for option in (raw.get("options") or []) if str(option).strip()]
        min_options = 6 if difficulty == DifficultyLevel.hard else 4
        if len(options) < min_options:
            return None
        raw_correct_index = raw.get("correct_option_index")
        try:
            correct_index = int(raw_correct_index) if raw_correct_index is not None else None
        except (TypeError, ValueError):
            correct_index = None
        if correct_index is None or correct_index < 0 or correct_index >= len(options):
            return None

        if difficulty == DifficultyLevel.hard:
            # Enforce 6/8 options for hard difficulty while preserving the correct option.
            if len(options) >= 8:
                if len(options) > 8:
                    keep = list(range(8))
                    if correct_index not in keep:
                        keep[-1] = correct_index
                    keep = sorted(set(keep))
                    options = [options[idx] for idx in keep]
                    correct_index = keep.index(correct_index)
                else:
                    options = options[:8]
            elif len(options) == 7:
                # Convert 7->6 by removing a distractor, not the correct option.
                remove_idx = 6 if correct_index != 6 else 5
                options = [item for idx, item in enumerate(options) if idx != remove_idx]
                if correct_index > remove_idx:
                    correct_index -= 1
            elif len(options) == 6:
                pass
            else:
                return None
            if len(options) not in {6, 8}:
                return None
        else:
            options = options[:8]

        return {
            "type": "single_choice",
            "prompt": prompt,
            "options": options,
            "correct_option_ids": [correct_index + 1],
            "topic_tags": topic_tags,
            "explanation": str(raw.get("explanation") or prompt).strip(),
        }

    def _postprocess_questions(
        self,
        questions: list[TeacherCustomMaterialQuestion],
        *,
        difficulty: DifficultyLevel,
    ) -> list[TeacherCustomMaterialQuestion]:
        if not questions:
            return []

        output = [item.model_copy(deep=True) for item in questions]
        choice_indexes = [
            idx
            for idx, question in enumerate(output)
            if question.answer_type == "choice"
            and isinstance(question.correct_option_index, int)
            and question.correct_option_index is not None
            and question.options
        ]
        if not choice_indexes:
            return output

        rng = random.SystemRandom()
        target_positions = self._build_balanced_correct_positions(len(choice_indexes), rng=rng)
        for order_idx, question_idx in enumerate(choice_indexes):
            question = output[question_idx]
            options = [str(item).strip() for item in (question.options or []) if str(item).strip()]
            if not options:
                continue
            correct_index = int(question.correct_option_index or 0)
            if correct_index < 0 or correct_index >= len(options):
                continue

            if difficulty == DifficultyLevel.hard:
                if len(options) > 8:
                    options = options[:8]
                if len(options) not in {6, 8}:
                    continue
            else:
                if len(options) < 4:
                    continue

            target = target_positions[order_idx]
            if target >= len(options):
                target = len(options) - 1

            options[target], options[correct_index] = options[correct_index], options[target]
            current_correct = target

            distractor_indexes = [idx for idx in range(len(options)) if idx != current_correct]
            distractors = [options[idx] for idx in distractor_indexes]
            rng.shuffle(distractors)
            for idx, value in zip(distractor_indexes, distractors):
                options[idx] = value

            question.options = options
            question.correct_option_index = current_correct

        return output

    def _build_balanced_correct_positions(
        self,
        count: int,
        *,
        rng: random.SystemRandom,
    ) -> list[int]:
        if count <= 0:
            return []
        base = [0, 1, 2, 3]
        positions: list[int] = []
        while len(positions) < count:
            chunk = base[:]
            rng.shuffle(chunk)
            positions.extend(chunk)
        return positions[:count]

    def _to_schema_item(self, normalized_payload: dict[str, Any]) -> TeacherCustomMaterialQuestion | None:
        question_type = str(normalized_payload.get("type", "single_choice"))
        if question_type == "short_text":
            sample_answer = str((normalized_payload.get("correct_answer_json") or {}).get("sample_answer", "")).strip()
            if not sample_answer:
                return None
            return TeacherCustomMaterialQuestion(
                prompt=str(normalized_payload.get("prompt", "")).strip(),
                answer_type="free_text",
                options=[],
                correct_option_index=None,
                sample_answer=sample_answer,
                image_data_url=None,
            )

        options = [
            str(item.get("text", "")).strip()
            for item in (normalized_payload.get("options_json") or {}).get("options", [])
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        correct_ids = [
            int(item)
            for item in (normalized_payload.get("correct_answer_json") or {}).get("correct_option_ids", [])
            if isinstance(item, (int, float, str)) and str(item).lstrip("-").isdigit()
        ]
        if len(options) < 2 or len(correct_ids) != 1:
            return None
        return TeacherCustomMaterialQuestion(
            prompt=str(normalized_payload.get("prompt", "")).strip(),
            answer_type="choice",
            options=options,
            correct_option_index=correct_ids[0] - 1,
            sample_answer=None,
            image_data_url=None,
        )

    def _is_topic_relevant(
        self,
        *,
        topic: str,
        prompt: str,
        sample_answer: str,
        explanation: str,
        topic_tags: Any,
    ) -> bool:
        topic_tokens = _tokens(topic)
        if not topic_tokens:
            return True
        tags_text = " ".join(str(tag).strip() for tag in (topic_tags or []) if str(tag).strip())
        joined = f"{prompt} {sample_answer} {explanation} {tags_text}".strip().lower()
        content_tokens = _tokens(joined)
        if not content_tokens:
            return False
        overlap = topic_tokens.intersection(content_tokens)
        if (len(overlap) / max(1, len(topic_tokens))) >= 0.2:
            return True
        if _fuzzy_token_overlap(topic_tokens, content_tokens) >= 0.35:
            return True
        return any(token in joined for token in topic_tokens)

    def _build_blueprint(
        self,
        *,
        topic: str,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        batch_size: int,
    ) -> str:
        lang_hint = "русском" if language == PreferredLanguage.ru else "казахском"
        categories = self._difficulty_categories(difficulty=difficulty)
        plan_lines: list[str] = []
        remaining = batch_size
        for idx, (name, weight) in enumerate(categories):
            if idx == len(categories) - 1:
                count = remaining
            else:
                count = max(1, round(batch_size * weight))
                count = min(count, remaining - max(0, (len(categories) - idx - 1)))
            remaining -= count
            plan_lines.append(f"- {name}: {count}")

        return (
            f"Тема: {topic}\n"
            f"Язык: {lang_hint}\n"
            "Распределение по категориям:\n"
            + "\n".join(plan_lines)
            + "\nИзбегай повторения одного и того же шаблона вопроса."
        )

    def _difficulty_categories(self, *, difficulty: DifficultyLevel) -> list[tuple[str, float]]:
        if difficulty == DifficultyLevel.easy:
            return [
                ("термины и определения", 0.28),
                ("базовая теория", 0.24),
                ("свойства и формулы", 0.20),
                ("понимание понятий", 0.16),
                ("простое применение", 0.12),
            ]
        if difficulty == DifficultyLevel.medium:
            return [
                ("термины и определения", 0.18),
                ("теория и свойства", 0.22),
                ("формулы и преобразования", 0.20),
                ("типовые задачи", 0.24),
                ("типичные ошибки", 0.16),
            ]
        return [
            ("продвинутая теория", 0.16),
            ("термины и взаимосвязи", 0.16),
            ("формулы и ограничения", 0.20),
            ("задачи повышенной сложности", 0.26),
            ("ошибки и контрпримеры", 0.22),
        ]

    def _difficulty_rubric(self, *, difficulty: DifficultyLevel) -> str:
        if difficulty == DifficultyLevel.easy:
            return (
                "- Уровень сложности: школьная программа СНГ, 6-8 классы.\n"
                "- 70% вопросов: термины, базовые свойства, распознавание понятий.\n"
                "- 30% вопросов: простое применение правил и одношаговые вычисления.\n"
                "- Формулировки короткие, без сложных многоэтапных рассуждений."
            )
        if difficulty == DifficultyLevel.medium:
            return (
                "- Уровень сложности: школьная программа СНГ, 9-11 классы.\n"
                "- 50% вопросов: теория, взаимосвязи понятий, формулы.\n"
                "- 50% вопросов: типовые задачи в 1-2 шага и выбор корректного метода.\n"
                "- Требуются уверенные школьные знания, без олимпиадной перегрузки."
            )
        return (
            "- Уровень сложности: ЕГЭ (профильный уровень).\n"
            "- 40% вопросов: продвинутая теория, тонкие различия, типичные ловушки.\n"
            "- 60% вопросов: задачи повышенной сложности в 2-3 шага и интерпретация условий.\n"
            "- Для answer_type=choice в каждом вопросе строго 6 или 8 вариантов."
        )

    def _build_llm_request_profile(
        self,
        *,
        difficulty: DifficultyLevel,
        batch_size: int,
        attempt: int,
    ) -> LLMRequestProfile:
        base_timeout = int(settings.openai_timeout_seconds or 45)
        safe_timeout = max(20, base_timeout)
        safe_batch = max(1, int(batch_size))
        normalized_attempt = max(1, int(attempt))

        if difficulty == DifficultyLevel.hard:
            timeout = min(120, safe_timeout + 35 + ((normalized_attempt - 1) * 5))
            max_tokens = min(9000, max(1800, safe_batch * 520))
            temperature = 0.14 if normalized_attempt == 1 else 0.10
            return LLMRequestProfile(
                temperature=temperature,
                timeout_seconds=timeout,
                max_tokens=max_tokens,
            )

        if difficulty == DifficultyLevel.medium:
            timeout = min(90, safe_timeout + 10 + ((normalized_attempt - 1) * 3))
            max_tokens = min(7000, max(1100, safe_batch * 340))
            temperature = 0.18 if normalized_attempt == 1 else 0.15
            return LLMRequestProfile(
                temperature=temperature,
                timeout_seconds=timeout,
                max_tokens=max_tokens,
            )

        timeout = min(75, safe_timeout + 5 + ((normalized_attempt - 1) * 2))
        max_tokens = min(5200, max(900, safe_batch * 250))
        temperature = 0.2 if normalized_attempt == 1 else 0.16
        return LLMRequestProfile(
            temperature=temperature,
            timeout_seconds=timeout,
            max_tokens=max_tokens,
        )


def _prompt_key(prompt: str) -> str:
    normalized = re.sub(r"\s+", " ", prompt.lower()).strip()
    normalized = re.sub(r"[^\wа-яәіңғүұқөһ ]+", "", normalized, flags=re.IGNORECASE)
    return normalized


def _tokens(value: str) -> set[str]:
    parts = re.split(r"[^\wа-яәіңғүұқөһ]+", value.lower(), flags=re.IGNORECASE)
    return {part for part in parts if len(part) >= 3}


def _fuzzy_token_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    matched = 0
    for left_token in left:
        if any(_tokens_are_related(left_token, right_token) for right_token in right):
            matched += 1
    return matched / max(1, len(left))


def _tokens_are_related(left: str, right: str) -> bool:
    l = _token_stem(left)
    r = _token_stem(right)
    if not l or not r:
        return False
    if l == r:
        return True
    min_len = min(len(l), len(r))
    if min_len < 5:
        return False
    prefix_len = 6 if min_len >= 8 else 5
    return l[:prefix_len] == r[:prefix_len]


def _token_stem(token: str) -> str:
    value = re.sub(r"[^a-zа-яәіңғүұқөһ0-9]", "", str(token or "").lower())
    if len(value) <= 5:
        return value
    endings = (
        "иями",
        "ями",
        "ами",
        "ией",
        "ий",
        "ый",
        "ой",
        "ая",
        "ое",
        "ее",
        "ые",
        "ого",
        "ему",
        "ыми",
        "ими",
        "ать",
        "ять",
        "ить",
        "еть",
        "ться",
        "ция",
        "ции",
        "цию",
        "циям",
        "лардың",
        "лердің",
        "лары",
        "лері",
    )
    for ending in endings:
        if value.endswith(ending) and len(value) - len(ending) >= 4:
            return value[: -len(ending)]
    return value


teacher_material_service = TeacherMaterialService()
