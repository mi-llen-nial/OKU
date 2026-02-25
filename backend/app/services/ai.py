from __future__ import annotations

import json
import logging
import random
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass

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
    def generate_test(
        self,
        *,
        subject: Subject,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        mode: TestMode,
        num_questions: int,
        user_id: int,
    ) -> GeneratedTestPayload:
        seed = f"{int(time.time() * 1000)}-{user_id}-{subject.id}-{difficulty.value}"

        if settings.ai_provider.lower() == "deepseek" and settings.deepseek_api_key:
            try:
                return self._generate_test_deepseek(
                    subject=subject,
                    difficulty=difficulty,
                    language=language,
                    mode=mode,
                    num_questions=num_questions,
                    seed=seed,
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
    ) -> GeneratedTestPayload:
        subject_name = subject.name_ru if language == PreferredLanguage.ru else subject.name_kz
        language_label = "русском" if language == PreferredLanguage.ru else "казахском"
        mode_hint = {
            TestMode.text: "Обычный текстовый тест.",
            TestMode.audio: "Добавь tts_text для каждого вопроса.",
            TestMode.oral: "Сфокусируйся на oral_answer и short_text, ожидается spoken_answer_text.",
        }[mode]
        difficulty_rules = {
            DifficultyLevel.easy: "Базовые факты и простые определения, без ловушек.",
            DifficultyLevel.medium: "Комбинированные задачи, умеренные отвлекающие варианты.",
            DifficultyLevel.hard: "Глубокие причинно-следственные вопросы, больше открытых ответов.",
        }[difficulty]

        prompt = f"""
Сгенерируй JSON без markdown для теста.
Предмет: {subject_name}
Язык: {language_label}
Сложность: {difficulty.value}
Правила сложности: {difficulty_rules}
Режим: {mode.value}. {mode_hint}
Количество вопросов: {num_questions}
Seed уникальности: {seed}

Формат JSON:
{{
  "questions": [
    {{
      "type": "single_choice|multi_choice|short_text|matching|oral_answer",
      "prompt": "...",
      "options_json": {{"options": [{{"id": 0, "text": "..."}}]}} или null,
      "correct_answer_json": {{...}},
      "explanation_json": {{"topic": "...", "correct_explanation": "..."}},
      "tts_text": "... или null"
    }}
  ]
}}

Условия:
- Все тексты только на выбранном языке.
- Для single_choice/multi_choice используй correct_option_ids.
- Для short_text/oral_answer используй keywords и sample_answer.
- Для matching используй matches словарь left->right.
- Для oral_answer в correct_answer_json добавь expected_field="spoken_answer_text".
- Верни ровно {num_questions} вопросов.
""".strip()

        content = self._call_deepseek(prompt)
        data = self._extract_json(content)
        questions = data.get("questions", [])
        parsed_questions = [GeneratedQuestionPayload.model_validate(item) for item in questions]
        if len(parsed_questions) != num_questions:
            raise ValueError("DeepSeek returned unexpected number of questions")

        for question in parsed_questions:
            if mode == TestMode.audio and not question.tts_text:
                question.tts_text = question.prompt

        return GeneratedTestPayload(seed=seed, questions=parsed_questions)

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
    ) -> GeneratedTestPayload:
        rng = random.Random(seed)
        topics = self._topics_for_subject(subject, language)
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
                rng=rng,
            )
            questions.append(question)

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
            "математика": ["Линейные уравнения", "Функции", "Проценты", "Геометрия", "Логика"],
            "физика": ["Кинематика", "Динамика", "Энергия", "Электричество", "Оптика"],
            "история": ["Хронология", "Причины и последствия", "Исторические личности", "Реформы", "Источники"],
        }
        topic_map_kz = {
            "математика": ["Сызықтық теңдеулер", "Функциялар", "Пайыз", "Геометрия", "Логика"],
            "физика": ["Кинематика", "Динамика", "Энергия", "Электр", "Оптика"],
            "история": ["Хронология", "Себеп пен салдар", "Тарихи тұлғалар", "Реформалар", "Дереккөздер"],
        }

        if language == PreferredLanguage.ru:
            return topic_map_ru.get(subject_key, ["Базовая теория", "Практика", "Анализ"])
        return topic_map_kz.get(subject_key, ["Негізгі теория", "Практика", "Талдау"])

    @staticmethod
    def _pick_question_type(
        *,
        difficulty: DifficultyLevel,
        mode: TestMode,
        rng: random.Random,
    ) -> QuestionType:
        if mode == TestMode.oral:
            pool = [QuestionType.oral_answer, QuestionType.short_text, QuestionType.single_choice]
        elif mode == TestMode.audio:
            pool = [QuestionType.single_choice, QuestionType.multi_choice, QuestionType.short_text, QuestionType.matching]
        else:
            pool = [QuestionType.single_choice, QuestionType.multi_choice, QuestionType.short_text, QuestionType.matching]

        if difficulty == DifficultyLevel.easy:
            weights = {
                QuestionType.single_choice: 0.45,
                QuestionType.multi_choice: 0.25,
                QuestionType.short_text: 0.2,
                QuestionType.matching: 0.1,
                QuestionType.oral_answer: 0.15,
            }
        elif difficulty == DifficultyLevel.medium:
            weights = {
                QuestionType.single_choice: 0.25,
                QuestionType.multi_choice: 0.25,
                QuestionType.short_text: 0.3,
                QuestionType.matching: 0.2,
                QuestionType.oral_answer: 0.3,
            }
        else:
            weights = {
                QuestionType.single_choice: 0.15,
                QuestionType.multi_choice: 0.2,
                QuestionType.short_text: 0.35,
                QuestionType.matching: 0.2,
                QuestionType.oral_answer: 0.4,
            }

        available = [q for q in pool if q in weights]
        values = [weights[q] for q in available]
        return rng.choices(available, weights=values, k=1)[0]

    def _build_question(
        self,
        *,
        index: int,
        subject: Subject,
        topic: str,
        qtype: QuestionType,
        language: PreferredLanguage,
        mode: TestMode,
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
            options = self._build_options(topic=topic, language=language, rng=rng, count=4)
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
            options = self._build_options(topic=topic, language=language, rng=rng, count=5)
            correct_ids = sorted(rng.sample(range(len(options)), 2))
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

        if language == PreferredLanguage.ru:
            prompt += " Дайте краткий текстовый ответ (1-2 предложения)."
            sample_answer = f"Ключевая идея темы «{topic}» связана с определением и применением правила."
        else:
            prompt += " Қысқа мәтіндік жауап беріңіз (1-2 сөйлем)."
            sample_answer = f"«{topic}» тақырыбының негізгі идеясы ережені қолданумен байланысты."

        keywords = [topic.split()[0].lower(), "правило" if language == PreferredLanguage.ru else "ереже"]
        return GeneratedQuestionPayload(
            type=QuestionType.short_text,
            prompt=prompt,
            options_json=None,
            correct_answer_json={"keywords": keywords, "sample_answer": sample_answer},
            explanation_json=explanation,
            tts_text=tts_text,
        )

    @staticmethod
    def _build_options(topic: str, language: PreferredLanguage, rng: random.Random, count: int) -> list[dict]:
        options = []
        for idx in range(count):
            if language == PreferredLanguage.ru:
                text = f"Вариант {idx + 1}: утверждение о теме «{topic}»"
            else:
                text = f"Нұсқа {idx + 1}: «{topic}» туралы тұжырым"
            options.append({"id": idx, "text": text})
        rng.shuffle(options)
        for new_idx, option in enumerate(options):
            option["id"] = new_idx
        return options


ai_service = AIService()
