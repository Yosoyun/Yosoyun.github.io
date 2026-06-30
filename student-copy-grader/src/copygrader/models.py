from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RubricItem:
    id: str
    marks: float
    description: str
    accepted: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    min_keywords: int = 1
    reference: str | None = None
    similarity_threshold: float | None = None


@dataclass(frozen=True)
class Question:
    id: str
    marks: float
    type: str
    answer: str | None = None
    tolerance: float | None = None
    rubric: tuple[RubricItem, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Exam:
    title: str
    board: str | None = None
    class_level: str | None = None
    subject: str | None = None
    max_marks: float | None = None


@dataclass(frozen=True)
class Rubric:
    exam: Exam
    questions: tuple[Question, ...]


@dataclass(frozen=True)
class Student:
    id: str
    name: str | None = None


@dataclass(frozen=True)
class Submission:
    student: Student
    answers: dict[str, str]


@dataclass(frozen=True)
class ItemResult:
    item_id: str
    description: str
    awarded: float
    possible: float
    matched: bool
    evidence: str


@dataclass(frozen=True)
class QuestionResult:
    question_id: str
    awarded: float
    possible: float
    answer: str
    item_results: tuple[ItemResult, ...]
    feedback: tuple[str, ...]
    needs_review: bool
    confidence: float


@dataclass(frozen=True)
class GradingResult:
    student: Student
    awarded: float
    possible: float
    question_results: tuple[QuestionResult, ...]

