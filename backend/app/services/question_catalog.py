from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    CatalogQuestion,
    CatalogQuestionStatus,
    DifficultyLevel,
    PreferredLanguage,
    QuestionType,
    Subject,
    TestMode,
)
from app.services.question_bank import get_text_question_templates
from app.services.question_quality import validate_question_payload


@dataclass
class CatalogImportStats:
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    invalid: int = 0


@dataclass
class CatalogRevalidateStats:
    scanned: int = 0
    normalized: int = 0
    archived_invalid: int = 0
    invalid: int = 0


class QuestionCatalogService:
    @staticmethod
    def _row_to_validation_payload(row: CatalogQuestion) -> dict[str, Any]:
        raw_options = []
        options_block = row.options_json or {}
        if isinstance(options_block, dict):
            raw_options = list(options_block.get("options", []))
        elif isinstance(options_block, list):
            raw_options = list(options_block)

        normalized_options: list[str] = []
        for item in raw_options:
            if isinstance(item, dict):
                text = str(item.get("text", "")).strip()
            else:
                text = str(item).strip()
            if text:
                normalized_options.append(text)

        correct_answer_json = row.correct_answer_json or {}
        if not isinstance(correct_answer_json, dict):
            correct_answer_json = {}

        explanation_json = row.explanation_json or {}
        if not isinstance(explanation_json, dict):
            explanation_json = {}

        return {
            "type": row.type.value,
            "prompt": row.prompt,
            "options": normalized_options,
            "correct_option_ids": correct_answer_json.get("correct_option_ids", []),
            "sample_answer": correct_answer_json.get("sample_answer", ""),
            "keywords": correct_answer_json.get("keywords", []),
            "topic_tags": list(row.topic_tags_json or []),
            "explanation": explanation_json.get("correct_explanation", ""),
        }

    def _filter_valid_published_rows(self, *, rows: list[CatalogQuestion]) -> list[CatalogQuestion]:
        if not rows:
            return []
        valid_rows: list[CatalogQuestion] = []
        for row in rows:
            validation = validate_question_payload(
                payload=self._row_to_validation_payload(row),
                language=row.language,
                mode=row.mode,
                difficulty=row.difficulty,
            )
            if validation.is_valid:
                valid_rows.append(row)
        return valid_rows

    @staticmethod
    def _catalog_unique_key(
        *,
        subject_id: int,
        language: PreferredLanguage,
        difficulty: DifficultyLevel,
        content_hash: str,
    ) -> tuple[int, str, str, str, str]:
        return (
            int(subject_id),
            language.value,
            TestMode.text.value,
            difficulty.value,
            str(content_hash),
        )

    @staticmethod
    def _split_csv_items(raw: str) -> list[str]:
        value = str(raw or "").replace("\r", "")
        if "|" in value:
            parts = value.split("|")
        elif "\n" in value:
            parts = value.split("\n")
        elif ";" in value:
            parts = value.split(";")
        else:
            parts = [value]
        return [item.strip() for item in parts if item.strip()]

    @staticmethod
    def _parse_difficulties(raw: str) -> list[DifficultyLevel]:
        allowed = {item.value: item for item in DifficultyLevel}
        output: list[DifficultyLevel] = []
        for token in QuestionCatalogService._split_csv_items(raw):
            key = token.strip().lower()
            difficulty = allowed.get(key)
            if difficulty is None:
                continue
            if difficulty in output:
                continue
            output.append(difficulty)
        return output or [DifficultyLevel.medium]

    @staticmethod
    def _parse_correct_option_ids(raw: str) -> list[int]:
        output: list[int] = []
        for token in QuestionCatalogService._split_csv_items(raw):
            try:
                value = int(token)
            except (TypeError, ValueError):
                continue
            if value in output:
                continue
            output.append(value)
        return output

    @staticmethod
    def _upsert_catalog_question(
        *,
        db: Session,
        subject_id: int,
        language: PreferredLanguage,
        difficulty: DifficultyLevel,
        source: str,
        source_ref: str | None,
        normalized: dict[str, Any],
        publish: bool,
        now: datetime,
        stats: CatalogImportStats,
    ) -> None:
        content_hash = str(normalized["content_hash"])
        existing = db.scalar(
            select(CatalogQuestion).where(
                CatalogQuestion.subject_id == subject_id,
                CatalogQuestion.language == language,
                CatalogQuestion.mode == TestMode.text,
                CatalogQuestion.difficulty == difficulty,
                CatalogQuestion.content_hash == content_hash,
            )
        )
        status = CatalogQuestionStatus.published if publish else CatalogQuestionStatus.validated
        if existing:
            existing.prompt = normalized["prompt"]
            existing.options_json = normalized["options_json"]
            existing.correct_answer_json = normalized["correct_answer_json"]
            existing.explanation_json = normalized["explanation_json"]
            existing.topic_tags_json = list(normalized["topic_tags"])
            existing.correct_options_count = int(normalized.get("correct_options_count") or 0)
            existing.metadata_json = {
                **dict(existing.metadata_json or {}),
                "source": source,
            }
            existing.source = source
            if source_ref:
                existing.source_ref = source_ref
            existing.status = status
            existing.validated_at = now
            existing.published_at = now if publish else existing.published_at
            stats.updated += 1
            return

        db.add(
            CatalogQuestion(
                subject_id=subject_id,
                status=status,
                source=source,
                source_ref=source_ref,
                version=1,
                language=language,
                mode=TestMode.text,
                difficulty=difficulty,
                type=QuestionType(normalized["type"]),
                prompt=normalized["prompt"],
                options_json=normalized["options_json"],
                correct_answer_json=normalized["correct_answer_json"],
                explanation_json=normalized["explanation_json"],
                topic_tags_json=list(normalized["topic_tags"]),
                metadata_json={"source": source},
                correct_options_count=int(normalized.get("correct_options_count") or 0),
                content_hash=content_hash,
                validated_at=now,
                published_at=now if publish else None,
            )
        )
        stats.imported += 1

    def _template_to_payload(self, *, template: dict[str, Any]) -> dict[str, Any]:
        question_type = str(template.get("type", "single_choice")).strip()
        payload: dict[str, Any] = {
            "type": question_type,
            "topic_tags": [str(template.get("topic", "")).strip()] if str(template.get("topic", "")).strip() else [],
            "prompt": str(template.get("prompt", "")).strip(),
            "explanation": str(template.get("explanation", "")).strip(),
        }
        if question_type in {QuestionType.single_choice.value, QuestionType.multi_choice.value}:
            payload["options"] = [str(item).strip() for item in (template.get("options") or []) if str(item).strip()]
            payload["correct_option_ids"] = [int(value) + 1 for value in (template.get("correct_option_ids") or [])]
        else:
            payload["sample_answer"] = str(template.get("sample_answer", "")).strip()
            payload["keywords"] = [str(item).strip() for item in (template.get("keywords") or []) if str(item).strip()]
        return payload

    def import_from_question_bank(
        self,
        *,
        db: Session,
        source: str = "question_bank",
        min_questions_per_subject: int = 50,
        subject_id: int | None = None,
    ) -> CatalogImportStats:
        stats = CatalogImportStats()
        query = select(Subject).order_by(Subject.id.asc())
        if subject_id is not None:
            query = query.where(Subject.id == int(subject_id))
        subjects = db.scalars(query).all()

        for subject in subjects:
            for language in (PreferredLanguage.ru, PreferredLanguage.kz):
                for difficulty in (DifficultyLevel.easy, DifficultyLevel.medium, DifficultyLevel.hard):
                    templates = get_text_question_templates(
                        subject_name_ru=subject.name_ru,
                        language=language,
                        difficulty=difficulty,
                    )
                    if not templates:
                        continue

                    for template in templates:
                        raw_payload = self._template_to_payload(template=template)
                        validation = validate_question_payload(
                            payload=raw_payload,
                            language=language,
                            mode=TestMode.text,
                            difficulty=difficulty,
                        )
                        if not validation.is_valid:
                            stats.invalid += 1
                            continue

                        normalized = validation.payload
                        content_hash = str(normalized["content_hash"])
                        existing = db.scalar(
                            select(CatalogQuestion).where(
                                CatalogQuestion.subject_id == subject.id,
                                CatalogQuestion.language == language,
                                CatalogQuestion.mode == TestMode.text,
                                CatalogQuestion.difficulty == difficulty,
                                CatalogQuestion.content_hash == content_hash,
                            )
                        )
                        if existing:
                            existing.prompt = normalized["prompt"]
                            existing.options_json = normalized["options_json"]
                            existing.correct_answer_json = normalized["correct_answer_json"]
                            existing.explanation_json = normalized["explanation_json"]
                            existing.topic_tags_json = list(normalized["topic_tags"])
                            existing.correct_options_count = int(normalized.get("correct_options_count") or 0)
                            existing.metadata_json = {
                                **dict(existing.metadata_json or {}),
                                "source": source,
                            }
                            if existing.status == CatalogQuestionStatus.draft:
                                existing.status = CatalogQuestionStatus.validated
                                existing.validated_at = datetime.now(timezone.utc)
                            stats.updated += 1
                            continue

                        catalog_row = CatalogQuestion(
                            subject_id=subject.id,
                            status=CatalogQuestionStatus.validated,
                            source=source,
                            source_ref=str(template.get("base_prompt_key") or ""),
                            version=1,
                            language=language,
                            mode=TestMode.text,
                            difficulty=difficulty,
                            type=QuestionType(normalized["type"]),
                            prompt=normalized["prompt"],
                            options_json=normalized["options_json"],
                            correct_answer_json=normalized["correct_answer_json"],
                            explanation_json=normalized["explanation_json"],
                            topic_tags_json=list(normalized["topic_tags"]),
                            metadata_json={"source": source},
                            correct_options_count=int(normalized.get("correct_options_count") or 0),
                            content_hash=content_hash,
                            validated_at=datetime.now(timezone.utc),
                        )
                        db.add(catalog_row)
                        stats.imported += 1

            # Keep the catalog non-empty per subject by publishing immediately when needed.
            published_count = db.scalar(
                select(func.count(CatalogQuestion.id)).where(
                    CatalogQuestion.subject_id == subject.id,
                    CatalogQuestion.status == CatalogQuestionStatus.published,
                )
            )
            if int(published_count or 0) < min_questions_per_subject:
                self.publish_subject_questions(db=db, subject_id=subject.id)

        db.commit()
        return stats

    def import_from_csv_file(
        self,
        *,
        db: Session,
        csv_path: str,
        source: str = "csv_question_bank",
        publish: bool = True,
        replace_existing_source_prefix: str | None = None,
    ) -> CatalogImportStats:
        stats = CatalogImportStats()
        now = datetime.now(timezone.utc)
        file_path = Path(csv_path).expanduser()
        seen_keys_in_import: set[tuple[int, str, str, str, str]] = set()
        if not file_path.exists() or not file_path.is_file():
            raise ValueError(f"CSV file not found: {file_path}")

        subjects = db.scalars(select(Subject)).all()
        by_ru = {item.name_ru.strip().lower(): item for item in subjects}
        by_kz = {item.name_kz.strip().lower(): item for item in subjects}

        source_prefix = str(replace_existing_source_prefix or "").strip()
        if source_prefix:
            db.execute(
                delete(CatalogQuestion).where(
                    CatalogQuestion.source == source_prefix
                )
            )
            db.execute(
                delete(CatalogQuestion).where(
                    CatalogQuestion.source.like(f"{source_prefix}:%")
                )
            )

        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_index, row in enumerate(reader, start=2):
                if not isinstance(row, dict):
                    stats.skipped += 1
                    continue

                subject_raw = str(row.get("subject_ru", "")).strip().lower()
                if not subject_raw:
                    stats.invalid += 1
                    continue
                subject = by_ru.get(subject_raw) or by_kz.get(subject_raw)
                if subject is None:
                    stats.invalid += 1
                    continue

                difficulties = self._parse_difficulties(str(row.get("levels", "")))
                question_type = str(row.get("type", "single_choice")).strip()
                source_ref = f"{file_path.name}:row:{row_index}"

                for difficulty in difficulties:
                    for language, suffix in ((PreferredLanguage.ru, "ru"), (PreferredLanguage.kz, "kz")):
                        prompt = str(row.get(f"prompt_{suffix}", "")).strip()
                        if not prompt:
                            stats.skipped += 1
                            continue

                        options = self._split_csv_items(str(row.get(f"options_{suffix}", "")))
                        sample_answer = str(row.get(f"sample_answer_{suffix}", "")).strip()
                        keywords = self._split_csv_items(str(row.get(f"keywords_{suffix}", "")))
                        topic_tag = str(row.get(f"topic_{suffix}", "")).strip()
                        explanation = str(row.get(f"explanation_{suffix}", "")).strip()
                        raw_payload: dict[str, Any] = {
                            "type": question_type,
                            "prompt": prompt,
                            "options": options,
                            "correct_option_ids": self._parse_correct_option_ids(str(row.get("correct_option_ids", ""))),
                            "sample_answer": sample_answer,
                            "keywords": keywords,
                            "topic_tags": [topic_tag] if topic_tag else [],
                            "explanation": explanation,
                        }
                        validation = validate_question_payload(
                            payload=raw_payload,
                            language=language,
                            mode=TestMode.text,
                            difficulty=difficulty,
                        )
                        if not validation.is_valid:
                            stats.invalid += 1
                            continue

                        normalized = validation.payload
                        key = self._catalog_unique_key(
                            subject_id=subject.id,
                            language=language,
                            difficulty=difficulty,
                            content_hash=str(normalized["content_hash"]),
                        )
                        if key in seen_keys_in_import:
                            stats.skipped += 1
                            continue

                        self._upsert_catalog_question(
                            db=db,
                            subject_id=subject.id,
                            language=language,
                            difficulty=difficulty,
                            source=source,
                            source_ref=source_ref,
                            normalized=normalized,
                            publish=publish,
                            now=now,
                            stats=stats,
                        )
                        seen_keys_in_import.add(key)

        db.commit()
        return stats

    def validate_subject_questions(self, *, db: Session, subject_id: int) -> int:
        rows = db.scalars(
            select(CatalogQuestion).where(
                CatalogQuestion.subject_id == subject_id,
                CatalogQuestion.status == CatalogQuestionStatus.draft,
            )
        ).all()
        validated = 0
        now = datetime.now(timezone.utc)
        for row in rows:
            validation = validate_question_payload(
                payload={
                    "type": row.type.value,
                    "prompt": row.prompt,
                    "options": [
                        str(item.get("text", "")).strip()
                        for item in (row.options_json or {}).get("options", [])
                        if isinstance(item, dict)
                    ],
                    "correct_option_ids": (row.correct_answer_json or {}).get("correct_option_ids", []),
                    "sample_answer": (row.correct_answer_json or {}).get("sample_answer", ""),
                    "keywords": (row.correct_answer_json or {}).get("keywords", []),
                    "topic_tags": list(row.topic_tags_json or []),
                    "explanation": (row.explanation_json or {}).get("correct_explanation", ""),
                },
                language=row.language,
                mode=row.mode,
                difficulty=row.difficulty,
            )
            if validation.is_valid:
                row.status = CatalogQuestionStatus.validated
                row.validated_at = now
                row.correct_options_count = int(validation.payload.get("correct_options_count") or 0)
                validated += 1
        db.commit()
        return validated

    def publish_subject_questions(self, *, db: Session, subject_id: int) -> int:
        rows = db.scalars(
            select(CatalogQuestion).where(
                CatalogQuestion.subject_id == subject_id,
                CatalogQuestion.status.in_([CatalogQuestionStatus.validated, CatalogQuestionStatus.published]),
            )
        ).all()
        now = datetime.now(timezone.utc)
        count = 0
        for row in rows:
            row.status = CatalogQuestionStatus.published
            row.published_at = now
            count += 1
        db.commit()
        return count

    def ensure_subject_catalog_ready(self, *, db: Session, subject: Subject) -> None:
        count = db.scalar(
            select(func.count(CatalogQuestion.id)).where(
                CatalogQuestion.subject_id == subject.id,
                CatalogQuestion.status == CatalogQuestionStatus.published,
            )
        )
        if int(count or 0) > 0:
            return
        self.import_from_question_bank(db=db, subject_id=subject.id)

    def revalidate_published_questions(
        self,
        *,
        db: Session,
        source_prefix: str | None = None,
        archive_invalid: bool = True,
        normalize_valid: bool = True,
    ) -> CatalogRevalidateStats:
        stats = CatalogRevalidateStats()
        query = select(CatalogQuestion).where(
            CatalogQuestion.status == CatalogQuestionStatus.published,
        )
        prefix = str(source_prefix or "").strip()
        if prefix:
            query = query.where(
                (CatalogQuestion.source == prefix)
                | (CatalogQuestion.source.like(f"{prefix}:%"))
            )
        rows = db.scalars(query).all()
        for row in rows:
            stats.scanned += 1
            validation = validate_question_payload(
                payload=self._row_to_validation_payload(row),
                language=row.language,
                mode=row.mode,
                difficulty=row.difficulty,
            )
            if not validation.is_valid:
                stats.invalid += 1
                if archive_invalid:
                    row.status = CatalogQuestionStatus.archived
                    row.published_at = None
                    stats.archived_invalid += 1
                continue

            if not normalize_valid:
                continue

            normalized = validation.payload
            changed = False

            prompt = str(normalized.get("prompt") or "")
            options_json = normalized.get("options_json")
            correct_answer_json = normalized.get("correct_answer_json")
            explanation_json = normalized.get("explanation_json")
            topic_tags = list(normalized.get("topic_tags") or [])
            correct_options_count = int(normalized.get("correct_options_count") or 0)
            content_hash = str(normalized.get("content_hash") or "")

            if row.prompt != prompt:
                row.prompt = prompt
                changed = True
            if row.options_json != options_json:
                row.options_json = options_json
                changed = True
            if row.correct_answer_json != correct_answer_json:
                row.correct_answer_json = correct_answer_json
                changed = True
            if row.explanation_json != explanation_json:
                row.explanation_json = explanation_json
                changed = True
            if list(row.topic_tags_json or []) != topic_tags:
                row.topic_tags_json = topic_tags
                changed = True
            if int(row.correct_options_count or 0) != correct_options_count:
                row.correct_options_count = correct_options_count
                changed = True
            if str(row.content_hash or "") != content_hash:
                row.content_hash = content_hash
                changed = True

            if changed:
                stats.normalized += 1

        db.commit()
        return stats

    def get_published_candidates(
        self,
        *,
        db: Session,
        subject_id: int,
        difficulty: DifficultyLevel,
        language: PreferredLanguage,
        mode: TestMode,
        limit: int = 300,
        allow_mode_fallback: bool = False,
    ) -> list[CatalogQuestion]:
        mode_rows = db.scalars(
            select(CatalogQuestion)
            .where(
                CatalogQuestion.subject_id == subject_id,
                CatalogQuestion.status == CatalogQuestionStatus.published,
                CatalogQuestion.language == language,
                CatalogQuestion.difficulty == difficulty,
                CatalogQuestion.mode == mode,
            )
            .order_by(
                case(
                    (CatalogQuestion.source.like("csv_question_bank:%"), 0),
                    else_=1,
                ),
                CatalogQuestion.id.asc(),
            )
            .limit(limit)
        ).all()
        mode_rows = self._filter_valid_published_rows(rows=mode_rows)
        csv_mode_rows = [row for row in mode_rows if str(row.source or "").startswith("csv_question_bank")]
        if csv_mode_rows:
            return csv_mode_rows
        if mode_rows or not allow_mode_fallback:
            return mode_rows

        text_rows = db.scalars(
            select(CatalogQuestion)
            .where(
                CatalogQuestion.subject_id == subject_id,
                CatalogQuestion.status == CatalogQuestionStatus.published,
                CatalogQuestion.language == language,
                CatalogQuestion.difficulty == difficulty,
                CatalogQuestion.mode == TestMode.text,
            )
            .order_by(
                case(
                    (CatalogQuestion.source.like("csv_question_bank:%"), 0),
                    else_=1,
                ),
                CatalogQuestion.id.asc(),
            )
            .limit(limit)
        ).all()
        text_rows = self._filter_valid_published_rows(rows=text_rows)
        csv_text_rows = [row for row in text_rows if str(row.source or "").startswith("csv_question_bank")]
        if csv_text_rows:
            return csv_text_rows
        return text_rows


question_catalog_service = QuestionCatalogService()
