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
        topics = self._topic_pool(subject=subject, language=language, focus_topics=focus_topics)
        questions: list[GeneratedQuestionPayload] = []

        for index in range(num_questions):
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
        questions = self._sanitize_questions(
            questions=questions,
            subject=subject,
            difficulty=difficulty,
            language=language,
            mode=mode,
            target_count=num_questions,
            focus_topics=focus_topics,
        )
        return GeneratedTestPayload(seed=seed, questions=questions)

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
        n = index + 1

        if language == PreferredLanguage.ru:
            prompt = f"[{subject_name}] Вопрос {n}: {topic}."
            explanation = {
                "topic": topic,
                "correct_explanation": f"Проверьте базовые определения и примените правило по теме «{topic}».",
            }
        else:
            prompt = f"[{subject_name}] {n}-сұрақ: {topic}."
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
