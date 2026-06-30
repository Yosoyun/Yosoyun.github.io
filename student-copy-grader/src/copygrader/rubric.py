from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Exam, Question, Rubric, RubricItem, Student, Submission


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def load_rubric(path: str | Path) -> Rubric:
    return parse_rubric(load_json(path))


def load_submission(path: str | Path) -> Submission:
    return parse_submission(load_json(path))


def parse_rubric(data: dict[str, Any]) -> Rubric:
    exam_data = data.get("exam") or {}
    if not isinstance(exam_data, dict):
        raise ValueError("exam must be an object")

    exam = Exam(
        title=str(exam_data.get("title") or "Untitled Exam"),
        board=_optional_str(exam_data.get("board")),
        class_level=_optional_str(exam_data.get("class_level")),
        subject=_optional_str(exam_data.get("subject")),
        max_marks=_optional_float(exam_data.get("max_marks")),
    )

    questions_data = data.get("questions")
    if not isinstance(questions_data, list) or not questions_data:
        raise ValueError("questions must be a non-empty list")

    questions = tuple(_parse_question(item) for item in questions_data)
    return Rubric(exam=exam, questions=questions)


def parse_submission(data: dict[str, Any]) -> Submission:
    student_data = data.get("student") or {}
    if not isinstance(student_data, dict):
        raise ValueError("student must be an object")

    answers = data.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("answers must be an object mapping question ids to answers")

    student = Student(
        id=str(student_data.get("id") or "unknown"),
        name=_optional_str(student_data.get("name")),
    )
    normalized_answers = {str(key): "" if value is None else str(value) for key, value in answers.items()}
    return Submission(student=student, answers=normalized_answers)


def _parse_question(data: dict[str, Any]) -> Question:
    if not isinstance(data, dict):
        raise ValueError("each question must be an object")
    question_id = str(data.get("id") or "").strip()
    if not question_id:
        raise ValueError("question id is required")

    marks = _required_float(data.get("marks"), f"question {question_id} marks")
    rubric_items = tuple(_parse_rubric_item(item, question_id) for item in data.get("rubric", []) or [])

    metadata = {
        key: value
        for key, value in data.items()
        if key not in {"id", "marks", "type", "answer", "tolerance", "rubric"}
    }

    return Question(
        id=question_id,
        marks=marks,
        type=str(data.get("type") or "short_answer").strip().lower(),
        answer=_optional_str(data.get("answer")),
        tolerance=_optional_float(data.get("tolerance")),
        rubric=rubric_items,
        metadata=metadata,
    )


def _parse_rubric_item(data: dict[str, Any], question_id: str) -> RubricItem:
    if not isinstance(data, dict):
        raise ValueError(f"rubric item in question {question_id} must be an object")

    item_id = str(data.get("id") or "").strip()
    if not item_id:
        raise ValueError(f"rubric item id is required in question {question_id}")

    return RubricItem(
        id=item_id,
        marks=_required_float(data.get("marks"), f"rubric item {item_id} marks"),
        description=str(data.get("description") or item_id),
        accepted=tuple(str(value) for value in data.get("accepted", []) or []),
        keywords=tuple(str(value) for value in data.get("keywords", []) or []),
        min_keywords=int(data.get("min_keywords") or 1),
        reference=_optional_str(data.get("reference")),
        similarity_threshold=_optional_float(data.get("similarity_threshold")),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _required_float(value: Any, field_name: str) -> float:
    if value is None or value == "":
        raise ValueError(f"{field_name} is required")
    return float(value)

