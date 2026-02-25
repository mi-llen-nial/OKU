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
    ) -> GeneratedTestPayload:
        seed = f"{int(time.time() * 1000)}-{user_id}-{subject.id}-{difficulty.value}"
        normalized_focus_topics = [str(topic).strip() for topic in (focus_topics or []) if str(topic).strip()]

        if settings.ai_provider.lower() == "deepseek" and settings.deepseek_api_key:
            try:
                return self._generate_test_deepseek(
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    mode=mode,
                    num_questions=num_questions,
                    seed=seed,
                    focus_topics=normalized_focus_topics,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("DeepSeek generation failed, fallback to mock: %s", exc)

        return self._generate_test_mock(
            subject=subject,
            difficulty=difficulty,
            language=language,
            mode=mode,
            num_questions=num_questions,
            seed=seed,
            focus_topics=normalized_focus_topics,
        )

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
            prompt_keys = {self._prompt_key(item.prompt) for item in sanitized_questions}
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
            raise ValueError("Unable to prepare enough valid questions for test")

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
            raise ValueError("Not enough generated tasks")
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
        base_text_templates: list[dict[str, Any]] = []

        if mode == TestMode.text:
            base_text_templates = get_text_question_templates(
                subject_name_ru=subject.name_ru,
                language=language,
                difficulty=difficulty,
            )
            questions.extend(
                self._generate_text_questions_from_bank(
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    num_questions=num_questions,
                    focus_topics=focus_topics,
                    templates=base_text_templates,
                    rng=rng,
                )
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

        if mode == TestMode.text and remaining > 0 and base_text_templates:
            questions.extend(
                self._generate_text_template_variants(
                    templates=base_text_templates,
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    count=remaining,
                    rng=rng,
                    variant_offset=0,
                )
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
        prompt_keys = {self._prompt_key(item.prompt) for item in output}
        variant_offset = 100

        for attempt in range(8):
            if len(output) >= target_count:
                break

            needed = target_count - len(output)
            extra_candidates: list[GeneratedQuestionPayload] = []

            if mode == TestMode.text:
                if is_math_subject:
                    extra_candidates.extend(
                        self._generate_math_text_extra_questions(
                            difficulty=difficulty,
                            language=language,
                            count=needed + 3,
                            rng=rng,
                        )
                    )

                if base_text_templates:
                    extra_candidates.extend(
                        self._generate_text_template_variants(
                            templates=base_text_templates,
                            subject=subject,
                            difficulty=difficulty,
                            language=language,
                            count=needed + 3,
                            rng=rng,
                            variant_offset=variant_offset,
                        )
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
                existing_prompt_keys=prompt_keys,
            )
            if not sanitized_extra:
                continue

            output.extend(sanitized_extra)
            for question in sanitized_extra:
                prompt_keys.add(self._prompt_key(question.prompt))

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
                template=template,
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
            base["prompt"] = self._variant_prompt(
                base_prompt,
                language=language,
                variant_index=variant_offset + index + 1,
            )
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

        for _ in range(count):
            template = rng.choice(weighted)(language=language, rng=rng)
            results.append(
                self._build_question_from_bank_template(
                    template=template,
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    rng=rng,
                )
            )
        return results

    @staticmethod
    def _variant_prompt(prompt: str, *, language: PreferredLanguage, variant_index: int) -> str:
        suffix_ru = [
            "Контрольный вариант.",
            "Практический вариант.",
            "Дополнительная проверка.",
            "Проверьте внимательность.",
            "Учебный вариант.",
        ]
        suffix_kz = [
            "Бақылау нұсқасы.",
            "Практикалық нұсқа.",
            "Қосымша тексеру.",
            "Мұқият орындаңыз.",
            "Оқу нұсқасы.",
        ]
        suffixes = suffix_ru if language == PreferredLanguage.ru else suffix_kz
        suffix = suffixes[(variant_index - 1) % len(suffixes)]
        if language == PreferredLanguage.ru:
            return f"{prompt} {suffix} Вариант {variant_index}."
        return f"{prompt} {suffix} Нұсқа {variant_index}."

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
        options = [str(new_price), str(new_price + base // 10), str(new_price - base // 10), str(base)]
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
                explanation_json={"topic": topic, "correct_explanation": explanation},
                tts_text=None,
            )

        option_count = self._choice_option_count(difficulty)
        options = [str(item).strip() for item in (template.get("options") or []) if str(item).strip()]
        correct_option_ids = [int(item) for item in (template.get("correct_option_ids") or [])]
        if not options:
            options = self._fallback_option_texts(topic=topic, language=language, count=option_count)
            correct_option_ids = [0]

        options, correct_option_ids = self._expand_and_shuffle_options_from_template(
            subject=subject,
            language=language,
            difficulty=difficulty,
            topic=topic,
            options=options,
            correct_option_ids=correct_option_ids,
            rng=rng,
        )
        question_type = QuestionType.multi_choice if len(correct_option_ids) > 1 else QuestionType.single_choice
        return GeneratedQuestionPayload(
            type=question_type,
            prompt=prompt,
            options_json={"options": [{"id": idx, "text": text} for idx, text in enumerate(options)]},
            correct_answer_json={"correct_option_ids": correct_option_ids},
            explanation_json={"topic": topic, "correct_explanation": explanation},
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
            safe_options = self._fallback_option_texts(topic=topic, language=language, count=option_count)

        safe_correct_ids = [value for value in correct_option_ids if 0 <= value < len(safe_options)]
        if not safe_correct_ids:
            safe_correct_ids = [0]

        distractor_pool = [
            *self._contextual_distractors_from_options(
                options=safe_options,
                language=language,
                needed=option_count * 2,
                rng=rng,
            ),
            *get_distractors(subject_name_ru=subject.name_ru, language=language),
            *self._fallback_option_texts(topic=topic, language=language, count=option_count * 2),
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

        short_options = [item for item in source if len(item.split()) <= 3]
        if short_options:
            if language == PreferredLanguage.ru:
                for candidate in ["Четыре", "Бесконечно много", "Не определено"]:
                    add(candidate)
            else:
                for candidate in ["Төрт", "Шексіз көп", "Анықталмаған"]:
                    add(candidate)

        numeric_values: list[tuple[float, str]] = []
        for item in source:
            match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*([%°]?)\s*", item)
            if not match:
                continue
            numeric_values.append((float(match.group(1)), match.group(2)))

        if numeric_values:
            suffix = numeric_values[0][1]
            base_values = [value for value, _ in numeric_values]
            average = sum(base_values) / len(base_values)
            offsets = [-30, -20, -10, -5, 5, 10, 20, 30]
            rng.shuffle(offsets)
            for offset in offsets:
                candidate = average + offset
                rendered = f"{int(candidate) if candidate.is_integer() else round(candidate, 2)}{suffix}"
                add(rendered)
                if len(pool) >= needed:
                    break

        if len(pool) < needed and language == PreferredLanguage.ru:
            add("Неверная подстановка коэффициентов")
            add("Пропущен важный знак в формуле")
        if len(pool) < needed and language == PreferredLanguage.kz:
            add("Коэффициенттер қате қойылған")
            add("Формулада маңызды белгі жіберілген")

        return pool[:needed]

    def _generate_recommendation_mock(
        self,
        *,
        subject: Subject,
        language: PreferredLanguage,
        weak_topics: list[str],
    ) -> RecommendationPayload:
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

            prompt = str(question.prompt).strip() or self._build_default_prompt(topic=topic, language=language, index=index)
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
                options = self._sanitize_choice_options(
                    topic=topic,
                    language=language,
                    option_count=self._choice_option_count(difficulty),
                    source_options=question.options_json,
                )
                correct_option_ids = self._sanitize_correct_option_ids(
                    source=question.correct_answer_json,
                    question_type=qtype,
                    option_count=len(options),
                )
                normalized = GeneratedQuestionPayload(
                    type=qtype,
                    prompt=prompt,
                    options_json={"options": options},
                    correct_answer_json={"correct_option_ids": correct_option_ids},
                    explanation_json={"topic": topic, "correct_explanation": explanation_text},
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
                        explanation_json={"topic": topic, "correct_explanation": explanation_text},
                        tts_text=tts_text,
                    )
            else:
                normalized = self._make_short_text_question(
                    prompt=prompt,
                    topic=topic,
                    explanation_json={"topic": topic, "correct_explanation": explanation_text},
                    language=language,
                    tts_text=tts_text,
                    source_correct_answer_json=question.correct_answer_json,
                    oral=(qtype == QuestionType.oral_answer),
                )

            key = self._prompt_key(normalized.prompt)
            if key in seen_prompt_keys:
                continue
            seen_prompt_keys.add(key)
            output.append(normalized)

        self._enforce_text_hard_mix(questions=output, language=language, mode=mode, difficulty=difficulty)
        return output[:target_count]

    def _enforce_text_hard_mix(
        self,
        *,
        questions: list[GeneratedQuestionPayload],
        language: PreferredLanguage,
        mode: TestMode,
        difficulty: DifficultyLevel,
    ) -> None:
        if mode != TestMode.text or difficulty != DifficultyLevel.hard or not questions:
            return

        required_short_questions = max(1, len(questions) // 4)
        current_short_questions = sum(1 for item in questions if item.type == QuestionType.short_text)
        if current_short_questions >= required_short_questions:
            return

        for index in range(len(questions) - 1, -1, -1):
            if current_short_questions >= required_short_questions:
                break
            question = questions[index]
            if question.type not in {QuestionType.single_choice, QuestionType.multi_choice}:
                continue
            topic = str(question.explanation_json.get("topic", "")).strip() or (
                "Причинно-следственный анализ" if language == PreferredLanguage.ru else "Себеп-салдар талдауы"
            )
            questions[index] = self._make_short_text_question(
                prompt=question.prompt,
                topic=topic,
                explanation_json=question.explanation_json,
                language=language,
            )
            current_short_questions += 1

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
            if language == PreferredLanguage.ru and "краткий" not in normalized_prompt.lower():
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
            },
            tts_text=tts_text,
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
        return re.sub(r"\s+", " ", prompt.lower()).strip()

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
