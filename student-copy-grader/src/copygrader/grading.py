from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

from .models import GradingResult, ItemResult, Question, QuestionResult, Rubric, RubricItem, Submission


_WORD_RE = re.compile(r"[a-z0-9-]+")
_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+|\.\d+)")


def grade_submission(rubric: Rubric, submission: Submission) -> GradingResult:
    results = tuple(_grade_question(question, submission.answers.get(question.id, "")) for question in rubric.questions)
    awarded = round(sum(result.awarded for result in results), 2)
    possible = round(sum(result.possible for result in results), 2)
    return GradingResult(
        student=submission.student,
        awarded=awarded,
        possible=possible,
        question_results=results,
    )


def _grade_question(question: Question, answer: str) -> QuestionResult:
    answer = answer or ""
    if question.type == "mcq":
        return _grade_mcq(question, answer)
    if question.type == "numeric":
        return _grade_numeric(question, answer)
    return _grade_short_answer(question, answer)


def _grade_mcq(question: Question, answer: str) -> QuestionResult:
    expected = question.answer or ""
    expected_option = _normalize_option(expected)
    actual_option = _normalize_option(answer)
    matched = actual_option == expected_option
    awarded = question.marks if matched else 0.0
    feedback = ("Correct option selected.",) if matched else (f"Expected option {expected_option or expected}.",)
    return QuestionResult(
        question_id=question.id,
        awarded=awarded,
        possible=question.marks,
        answer=answer,
        item_results=(
            ItemResult(
                item_id="mcq_exact",
                description="Selected the correct option",
                awarded=awarded,
                possible=question.marks,
                matched=matched,
                evidence=answer,
            ),
        ),
        feedback=feedback,
        needs_review=not matched,
        confidence=0.98 if matched else 0.65,
    )


def _grade_numeric(question: Question, answer: str) -> QuestionResult:
    expected_number = _first_number(question.answer or "")
    actual_numbers = _all_numbers(answer)
    tolerance = question.tolerance if question.tolerance is not None else 0.0

    actual_number = (
        next((value for value in actual_numbers if math.isclose(value, expected_number, abs_tol=tolerance)), None)
        if expected_number is not None
        else None
    )
    matched = expected_number is not None and actual_number is not None
    if not actual_numbers:
        evidence = "No numeric answer found."
    elif expected_number is None:
        evidence = "No numeric answer configured in the key."
    else:
        evidence = f"found numbers {', '.join(f'{value:g}' for value in actual_numbers)}, expected {expected_number:g}, tolerance {tolerance:g}"

    awarded = question.marks if matched else 0.0
    feedback = ("Numeric answer is within tolerance.",) if matched else (evidence,)
    return QuestionResult(
        question_id=question.id,
        awarded=awarded,
        possible=question.marks,
        answer=answer,
        item_results=(
            ItemResult(
                item_id="numeric_match",
                description="Numeric answer within tolerance",
                awarded=awarded,
                possible=question.marks,
                matched=matched,
                evidence=evidence,
            ),
        ),
        feedback=feedback,
        needs_review=not matched,
        confidence=0.95 if matched else 0.55,
    )


def _grade_short_answer(question: Question, answer: str) -> QuestionResult:
    if not answer.strip():
        return QuestionResult(
            question_id=question.id,
            awarded=0.0,
            possible=question.marks,
            answer=answer,
            item_results=(),
            feedback=("No answer found.",),
            needs_review=True,
            confidence=0.2,
        )

    if question.rubric:
        item_results = tuple(_grade_rubric_item(item, answer, question.answer) for item in question.rubric)
        awarded = min(question.marks, round(sum(item.awarded for item in item_results), 2))
        feedback = tuple(_feedback_from_items(item_results))
        confidence = _confidence_from_items(item_results, awarded, question.marks)
        return QuestionResult(
            question_id=question.id,
            awarded=awarded,
            possible=question.marks,
            answer=answer,
            item_results=item_results,
            feedback=feedback,
            needs_review=confidence < 0.82 or awarded < question.marks,
            confidence=confidence,
        )

    similarity = _similarity(answer, question.answer or "")
    matched = similarity >= 0.72
    awarded = question.marks if matched else round(question.marks * similarity, 2)
    return QuestionResult(
        question_id=question.id,
        awarded=min(question.marks, awarded),
        possible=question.marks,
        answer=answer,
        item_results=(
            ItemResult(
                item_id="answer_similarity",
                description="Similarity to reference answer",
                awarded=min(question.marks, awarded),
                possible=question.marks,
                matched=matched,
                evidence=f"similarity {similarity:.2f}",
            ),
        ),
        feedback=(f"Reference-answer similarity: {similarity:.2f}.",),
        needs_review=not matched,
        confidence=max(0.35, min(0.9, similarity)),
    )


def _grade_rubric_item(item: RubricItem, answer: str, question_answer: str | None) -> ItemResult:
    accepted_match = _match_accepted(answer, item.accepted)
    keyword_match_count = _keyword_match_count(answer, item.keywords)
    keyword_matched = bool(item.keywords) and keyword_match_count >= item.min_keywords

    reference = item.reference or question_answer or ""
    similarity = _similarity(answer, reference) if item.similarity_threshold and reference else 0.0
    similarity_matched = bool(item.similarity_threshold and similarity >= item.similarity_threshold)

    matched = accepted_match or keyword_matched or similarity_matched
    evidence_parts: list[str] = []
    if accepted_match:
        evidence_parts.append("accepted phrase matched")
    if item.keywords:
        evidence_parts.append(f"{keyword_match_count}/{len(item.keywords)} keywords matched")
    if item.similarity_threshold:
        evidence_parts.append(f"similarity {similarity:.2f}")

    return ItemResult(
        item_id=item.id,
        description=item.description,
        awarded=item.marks if matched else 0.0,
        possible=item.marks,
        matched=matched,
        evidence=", ".join(evidence_parts) or "no matching rule configured",
    )


def _feedback_from_items(item_results: tuple[ItemResult, ...]) -> list[str]:
    feedback: list[str] = []
    for item in item_results:
        if item.matched:
            feedback.append(f"+{item.awarded:g}: {item.description}.")
        else:
            feedback.append(f"0/{item.possible:g}: Missing or unclear - {item.description}.")
    return feedback


def _confidence_from_items(item_results: tuple[ItemResult, ...], awarded: float, possible: float) -> float:
    if not item_results or possible <= 0:
        return 0.4
    configured = sum(1 for item in item_results if item.evidence != "no matching rule configured")
    coverage = configured / len(item_results)
    score_ratio = awarded / possible
    return round(max(0.25, min(0.95, 0.35 + 0.35 * coverage + 0.25 * score_ratio)), 2)


def _normalize_text(text: str) -> str:
    normalized_math = re.sub(r"\b([a-z])\s*\^\s*2\b", r"\g<1>2", text, flags=re.IGNORECASE)
    normalized_math = re.sub(r"\b([a-z])\s*\^\s*3\b", r"\g<1>3", normalized_math, flags=re.IGNORECASE)
    normalized_math = re.sub(r"\b([a-z])\s+squared\b", r"\g<1>2", normalized_math, flags=re.IGNORECASE)
    normalized_math = re.sub(r"\b([a-z])\s+cubed\b", r"\g<1>3", normalized_math, flags=re.IGNORECASE)
    normalized_math = (
        normalized_math.replace("²", "2")
        .replace("³", "3")
        .replace("×", "x")
        .replace("−", "-")
    )
    normalized_math = re.sub(r"\bsquared\b", "2", normalized_math, flags=re.IGNORECASE)
    normalized_math = re.sub(r"\bcubed\b", "3", normalized_math, flags=re.IGNORECASE)
    return " ".join(_WORD_RE.findall(normalized_math.lower()))


def _normalize_option(text: str) -> str:
    normalized = _normalize_text(text)
    words = normalized.split()
    if not words:
        return ""
    for word in words:
        if re.fullmatch(r"[a-d]", word):
            return word
    option_cues = {"option", "answer", "ans", "choose", "selected", "select"}
    for index, word in enumerate(words[:-1]):
        if word in option_cues and re.fullmatch(r"[a-d]", words[index + 1]):
            return words[index + 1]
    return words[0]


def _match_accepted(answer: str, accepted: tuple[str, ...]) -> bool:
    normalized_answer = _normalize_text(answer)
    return any(_normalize_text(value) in normalized_answer for value in accepted if _normalize_text(value))


def _keyword_match_count(answer: str, keywords: tuple[str, ...]) -> int:
    normalized_answer = _normalize_text(answer)
    return sum(1 for keyword in keywords if _normalize_text(keyword) in normalized_answer)


def _similarity(left: str, right: str) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _first_number(text: str) -> float | None:
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    return float(match.group(0))


def _all_numbers(text: str) -> list[float]:
    return [float(match.group(0)) for match in _NUMBER_RE.finditer(text)]
