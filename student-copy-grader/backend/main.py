from __future__ import annotations

import base64
import csv
import io
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

load_dotenv()

MATHPIX_APP_ID = os.getenv("MATHPIX_APP_ID", "").strip()
MATHPIX_APP_KEY = os.getenv("MATHPIX_APP_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "").strip()
ALLOWED_ORIGINS = [item.strip() for item in os.getenv("ALLOWED_ORIGINS", "*").split(",") if item.strip()]
DATA_DIR = Path(os.getenv("COPYGRADER_DATA_DIR", "/tmp/student-copy-grader-data")).expanduser()
UPLOAD_DIR = DATA_DIR / "uploads"
STATE_FILE = DATA_DIR / "state.json"
RETENTION_DAYS = int(os.getenv("COPYGRADER_RETENTION_DAYS", "30"))
USD_TO_INR = float(os.getenv("COPYGRADER_USD_TO_INR", "95"))
MATHPIX_IMAGE_USD = 0.002
MATHPIX_PDF_PAGE_USD = 0.005

app = FastAPI(title="Student Copy Grader Backend", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GradeRequest(BaseModel):
    rubric: dict[str, Any]
    answers: dict[str, str]
    student: dict[str, Any] = Field(default_factory=dict)


class ExamCreate(BaseModel):
    title: str
    subject: str = "Mathematics"
    board: str = "CBSE"
    class_level: str = "XII"
    question_paper: str = ""
    solution_key: str = ""
    rubric: dict[str, Any]
    total_marks: float | None = None


class StudentRef(BaseModel):
    id: str
    name: str = ""


class BatchCreate(BaseModel):
    exam_id: str
    name: str
    centre_name: str = ""
    target_market: str = "CBSE coaching"
    students: list[StudentRef] = Field(default_factory=list)
    consent_note: str = "School/teacher confirms authority to upload student copies for grading assistance."


class GradeRunRequest(BaseModel):
    use_openai: bool = True


class QuestionOverride(BaseModel):
    question_id: str
    awarded: float | None = None
    feedback: list[str] | None = None
    needs_review: bool | None = None
    confidence: float | None = None


class GradeReviewRequest(BaseModel):
    approved_by: str
    notes: str = ""
    final_awarded: float | None = None
    question_overrides: list[QuestionOverride] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "0.2.0",
        "ocr_provider": "mathpix" if _mathpix_configured() else "not_configured",
        "grading_provider": "openai" if OPENAI_API_KEY and OPENAI_MODEL else "local_review_mode",
        "retention_days": RETENTION_DAYS,
        "data_dir": str(DATA_DIR),
        "endpoints": [
            "POST /api/exams",
            "POST /api/batches",
            "POST /api/submissions",
            "POST /api/submissions/{id}/ocr",
            "POST /api/submissions/{id}/grade",
            "PATCH /api/grades/{id}/review",
            "GET /api/batches/{id}/reports",
        ],
    }


@app.post("/api/exams")
def create_exam(request: ExamCreate) -> dict[str, Any]:
    _ensure_data_dirs()
    store = _read_store()
    exam_id = _new_id("exam")
    rubric = _normalize_backend_rubric(request.rubric, request)
    total_marks = request.total_marks or _rubric_total(rubric)
    exam = {
        "id": exam_id,
        "title": request.title.strip(),
        "subject": request.subject.strip(),
        "board": request.board.strip(),
        "class_level": request.class_level.strip(),
        "question_paper": request.question_paper,
        "solution_key": request.solution_key,
        "rubric": rubric,
        "total_marks": total_marks,
        "created_at": _now(),
    }
    store["exams"][exam_id] = exam
    _write_store(store)
    return exam


@app.post("/api/batches")
def create_batch(request: BatchCreate) -> dict[str, Any]:
    _ensure_data_dirs()
    store = _read_store()
    if request.exam_id not in store["exams"]:
        raise HTTPException(status_code=404, detail="Exam not found.")
    batch_id = _new_id("batch")
    batch = {
        "id": batch_id,
        "exam_id": request.exam_id,
        "name": request.name.strip(),
        "centre_name": request.centre_name.strip(),
        "target_market": request.target_market.strip(),
        "students": [student.model_dump() for student in request.students],
        "consent_note": request.consent_note,
        "created_at": _now(),
        "cost": _empty_cost(),
    }
    store["batches"][batch_id] = batch
    _write_store(store)
    return batch


@app.post("/api/submissions")
async def create_submission(
    batch_id: str = Form(...),
    student_id: str = Form(...),
    student_name: str = Form(""),
    consent_confirmed: bool = Form(False),
    answers_json: str = Form(""),
    transcript: str = Form(""),
    files: list[UploadFile] | None = File(None),
) -> dict[str, Any]:
    _ensure_data_dirs()
    if not consent_confirmed:
        raise HTTPException(status_code=400, detail="Confirm school/teacher consent before storing student scans.")

    store = _read_store()
    batch = store["batches"].get(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found.")

    submission_id = _new_id("sub")
    submission_dir = UPLOAD_DIR / submission_id
    submission_dir.mkdir(parents=True, exist_ok=True)
    stored_files: list[dict[str, Any]] = []
    cost = _empty_cost()

    for upload in files or []:
        data = await upload.read()
        if not data:
            continue
        safe_name = _safe_name(upload.filename or "copy")
        target = submission_dir / safe_name
        target.write_bytes(data)
        estimate = _estimate_upload_cost(data, safe_name, upload.content_type or "")
        stored_files.append(
            {
                "filename": safe_name,
                "content_type": upload.content_type or _mime_from_name(safe_name),
                "size": len(data),
                "path": f"{submission_id}/{safe_name}",
                **estimate,
            }
        )
        _merge_cost(cost, estimate["cost"])

    answers = _answers_from_json_or_text(answers_json, transcript)
    submission = {
        "id": submission_id,
        "batch_id": batch_id,
        "exam_id": batch["exam_id"],
        "student": {"id": student_id.strip(), "name": student_name.strip()},
        "consent_confirmed": True,
        "files": stored_files,
        "answers": answers,
        "transcript": transcript.strip(),
        "ocr_provider": "not_run",
        "warnings": [],
        "status": "uploaded",
        "cost": cost,
        "created_at": _now(),
        "retention_delete_after": (datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)).isoformat(),
    }
    store["submissions"][submission_id] = submission
    _merge_cost(batch["cost"], cost)
    _write_store(store)
    return submission


@app.post("/api/submissions/{submission_id}/ocr")
async def ocr_submission(submission_id: str) -> dict[str, Any]:
    _ensure_data_dirs()
    store = _read_store()
    submission = store["submissions"].get(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found.")
    if not submission.get("files") and submission.get("transcript"):
        submission["answers"] = _parse_question_entries(submission["transcript"]) or {"1": submission["transcript"]}
        submission["ocr_provider"] = "stored_transcript"
        submission["status"] = "ocr_complete"
        _write_store(store)
        return submission
    if not _mathpix_configured():
        raise HTTPException(status_code=503, detail="Mathpix credentials are not configured on the backend.")
    if not submission.get("files"):
        raise HTTPException(status_code=400, detail="Submission has no stored files to OCR.")

    pages: list[dict[str, str]] = []
    warnings: list[str] = []
    async with httpx.AsyncClient(timeout=90) as client:
        for stored in submission["files"]:
            file_path = UPLOAD_DIR / stored["path"]
            if not file_path.exists():
                warnings.append(f"{stored['filename']}: stored file missing")
                continue
            data = file_path.read_bytes()
            for page_name, image_bytes, mime_type in _iter_ocr_images(data, stored["filename"], stored["content_type"]):
                try:
                    ocr = await _mathpix_ocr(client, image_bytes, mime_type)
                    text = _best_mathpix_text(ocr)
                    pages.append({"page": page_name, "text": text})
                except Exception as exc:  # keep batch processing alive for the teacher
                    warnings.append(f"{page_name}: {exc}")

    transcript = "\n\n".join(f"--- {page['page']} ---\n{page['text']}" for page in pages if page["text"]).strip()
    answers = _parse_question_entries(transcript)
    if not answers and transcript:
        answers = {"1": transcript}
        warnings.append("Could not split OCR by question number; transcript was placed under Q1 for teacher review.")

    submission["answers"] = answers
    submission["transcript"] = transcript
    submission["warnings"] = warnings
    submission["ocr_provider"] = "mathpix"
    submission["status"] = "ocr_complete" if answers else "needs_review"
    store["submissions"][submission_id] = submission
    _write_store(store)
    return submission


@app.post("/api/submissions/{submission_id}/grade")
async def grade_submission_endpoint(submission_id: str, request: GradeRunRequest | None = None) -> dict[str, Any]:
    _ensure_data_dirs()
    request = request or GradeRunRequest()
    store = _read_store()
    submission = store["submissions"].get(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found.")
    exam = store["exams"].get(submission["exam_id"])
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found.")

    answers = submission.get("answers") or _parse_question_entries(submission.get("transcript", ""))
    if not answers:
        raise HTTPException(status_code=400, detail="No answers found. Run OCR or add answers before grading.")

    provider = "local_rubric"
    if request.use_openai and OPENAI_API_KEY and OPENAI_MODEL:
        result = await _evaluate_payload_with_openai(exam["rubric"], answers, submission["student"])
        provider = "openai"
    else:
        result = _local_grade(exam["rubric"], answers, submission["student"])

    grade_id = _new_id("grade")
    review_count = sum(1 for item in result.get("questionResults", []) if item.get("needsReview"))
    grade = {
        "id": grade_id,
        "submission_id": submission_id,
        "batch_id": submission["batch_id"],
        "exam_id": submission["exam_id"],
        "student": submission["student"],
        "provider": provider,
        "status": "needs_teacher_review" if review_count else "ai_suggested",
        "review_count": review_count,
        "result": result,
        "created_at": _now(),
        "updated_at": _now(),
    }
    store["grades"][grade_id] = grade
    submission["grade_id"] = grade_id
    submission["status"] = "graded_needs_review" if review_count else "graded"
    store["submissions"][submission_id] = submission
    _write_store(store)
    return grade


@app.patch("/api/grades/{grade_id}/review")
def review_grade(grade_id: str, request: GradeReviewRequest) -> dict[str, Any]:
    _ensure_data_dirs()
    store = _read_store()
    grade = store["grades"].get(grade_id)
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found.")

    result = grade["result"]
    questions = result.get("questionResults", [])
    by_id = {str(item.get("questionId")): item for item in questions}
    for override in request.question_overrides:
        item = by_id.get(str(override.question_id))
        if not item:
            continue
        if override.awarded is not None:
            item["awarded"] = round(float(override.awarded), 2)
        if override.feedback is not None:
            item["feedback"] = override.feedback
        if override.needs_review is not None:
            item["needsReview"] = bool(override.needs_review)
        if override.confidence is not None:
            item["confidence"] = float(override.confidence)

    result["awarded"] = (
        round(float(request.final_awarded), 2)
        if request.final_awarded is not None
        else round(sum(float(item.get("awarded", 0)) for item in questions), 2)
    )
    result["possible"] = round(sum(float(item.get("possible", 0)) for item in questions), 2)
    grade["status"] = "teacher_approved"
    grade["review_count"] = sum(1 for item in questions if item.get("needsReview"))
    grade["review"] = {
        "approved_by": request.approved_by.strip(),
        "notes": request.notes,
        "approved_at": _now(),
    }
    grade["updated_at"] = _now()
    store["grades"][grade_id] = grade
    _write_store(store)
    return grade


@app.get("/api/batches/{batch_id}/reports")
def batch_reports(batch_id: str, format: str = Query("json", pattern="^(json|csv|html)$")):
    _ensure_data_dirs()
    store = _read_store()
    batch = store["batches"].get(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found.")
    exam = store["exams"].get(batch["exam_id"], {})
    grades = [grade for grade in store["grades"].values() if grade.get("batch_id") == batch_id]
    grades.sort(key=lambda item: item.get("student", {}).get("id", ""))
    report = _batch_report_payload(batch, exam, grades)

    if format == "json":
        return JSONResponse(report)
    if format == "csv":
        return PlainTextResponse(_batch_report_csv(report), media_type="text/csv")
    return HTMLResponse(_batch_report_html(report))


@app.delete("/api/submissions/{submission_id}")
def delete_submission(submission_id: str) -> dict[str, Any]:
    _ensure_data_dirs()
    store = _read_store()
    removed = _delete_submission_from_store(store, submission_id)
    _write_store(store)
    return {"deleted": removed, "submission_id": submission_id}


@app.post("/api/privacy/purge-expired")
def purge_expired_submissions() -> dict[str, Any]:
    _ensure_data_dirs()
    store = _read_store()
    now = datetime.now(timezone.utc)
    removed: list[str] = []
    for submission_id, submission in list(store["submissions"].items()):
        delete_after = _parse_datetime(submission.get("retention_delete_after"))
        if delete_after and delete_after <= now:
            if _delete_submission_from_store(store, submission_id):
                removed.append(submission_id)
    _write_store(store)
    return {"purged": removed, "retention_days": RETENTION_DAYS}


@app.get("/api/privacy/policy")
def privacy_policy() -> dict[str, Any]:
    return {
        "student_data": "Store only exam, batch, student identifier, OCR transcript, teacher-approved marks, and uploaded scans needed for review.",
        "retention_days": RETENTION_DAYS,
        "deletion": "Use DELETE /api/submissions/{id} for a single copy or POST /api/privacy/purge-expired for retention cleanup.",
        "keys": "Mathpix and OpenAI keys must stay in backend environment variables, never in the public frontend.",
        "consent": "The API requires consent_confirmed=true before storing student scans.",
    }


@app.post("/api/ocr/extract")
async def extract_answers(
    files: list[UploadFile] = File(...),
    paper_text: str = Form(""),
    rubric_text: str = Form(""),
    student_id: str = Form(""),
) -> dict[str, Any]:
    if not _mathpix_configured():
        raise HTTPException(status_code=503, detail="Mathpix credentials are not configured on the backend.")
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one student copy file.")

    pages: list[dict[str, str]] = []
    warnings: list[str] = []
    async with httpx.AsyncClient(timeout=90) as client:
        for upload in files:
            data = await upload.read()
            for page_name, image_bytes, mime_type in _iter_ocr_images(data, upload.filename or "copy", upload.content_type or ""):
                try:
                    ocr = await _mathpix_ocr(client, image_bytes, mime_type)
                    text = _best_mathpix_text(ocr)
                    pages.append({"page": page_name, "text": text})
                except Exception as exc:  # keep batch processing alive for the teacher
                    warnings.append(f"{page_name}: {exc}")

    transcript = "\n\n".join(f"--- {page['page']} ---\n{page['text']}" for page in pages if page["text"]).strip()
    answers = _parse_question_entries(transcript)
    if not answers and transcript:
        answers = {"1": transcript}
        warnings.append("Could not split OCR by question number; transcript was placed under Q1 for teacher review.")

    return {
        "provider": "mathpix",
        "student_id": student_id,
        "answers": answers,
        "transcript": transcript,
        "warnings": warnings,
        "paper_received": bool(paper_text.strip()),
        "rubric_received": bool(rubric_text.strip()),
    }


@app.post("/api/grade/evaluate")
async def evaluate_with_openai(request: GradeRequest) -> dict[str, Any]:
    return await _evaluate_payload_with_openai(request.rubric, request.answers, request.student)


async def _evaluate_payload_with_openai(rubric: dict[str, Any], answers: dict[str, str], student: dict[str, Any]) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OpenAI API key is not configured on the backend.")
    if not OPENAI_MODEL:
        raise HTTPException(status_code=503, detail="Set OPENAI_MODEL in the backend environment.")

    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Install the openai Python package.") from exc

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    prompt = {
        "task": "Grade handwritten student answers from OCR transcript. Do not invent work that is not present.",
        "rules": [
            "Use the rubric marks exactly.",
            "Give question-wise awarded marks, feedback, confidence, and needs_review.",
            "Flag low confidence, unclear OCR, missing steps, diagrams, and unusual methods.",
            "Return JSON only using keys: student, awarded, possible, questionResults.",
        ],
        "rubric": rubric,
        "student": student,
        "answers": answers,
    }

    response = await client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {
                "role": "system",
                "content": "You are a careful teacher-assistant grader. You never silently correct OCR mistakes.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=True)},
        ],
    )
    output_text = getattr(response, "output_text", "") or "{}"
    try:
        return json.loads(output_text)
    except json.JSONDecodeError:
        return {"raw": output_text, "needsReview": True}


def _mathpix_configured() -> bool:
    return bool(MATHPIX_APP_ID and MATHPIX_APP_KEY)


def _ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        _write_store(_empty_store())


def _empty_store() -> dict[str, Any]:
    return {"exams": {}, "batches": {}, "submissions": {}, "grades": {}}


def _read_store() -> dict[str, Any]:
    _ensure_data_dirs()
    try:
        loaded = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        loaded = _empty_store()
    store = _empty_store()
    for key in store:
        store[key] = loaded.get(key, store[key])
    return store


def _write_store(store: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(store, indent=2, ensure_ascii=True), encoding="utf-8")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _safe_name(filename: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(filename).name).strip("-")
    return name or "copy"


def _empty_cost() -> dict[str, float]:
    return {
        "ocr_units": 0,
        "estimated_ocr_usd": 0.0,
        "estimated_openai_usd": 0.0,
        "estimated_total_usd": 0.0,
        "estimated_total_inr": 0.0,
    }


def _merge_cost(target: dict[str, float], cost: dict[str, float]) -> None:
    for key, value in cost.items():
        target[key] = round(float(target.get(key, 0)) + float(value or 0), 4)
    target["estimated_total_usd"] = round(float(target.get("estimated_ocr_usd", 0)) + float(target.get("estimated_openai_usd", 0)), 4)
    target["estimated_total_inr"] = round(target["estimated_total_usd"] * USD_TO_INR, 2)


def _estimate_upload_cost(data: bytes, filename: str, content_type: str) -> dict[str, Any]:
    lowered = filename.lower()
    is_pdf = content_type == "application/pdf" or lowered.endswith(".pdf")
    if is_pdf:
        pages = _pdf_page_count(data)
        usd = round(pages * MATHPIX_PDF_PAGE_USD, 4)
        return {
            "page_count": pages,
            "ocr_unit_type": "pdf_page",
            "cost": {
                "ocr_units": pages,
                "estimated_ocr_usd": usd,
                "estimated_openai_usd": 0.0,
                "estimated_total_usd": usd,
                "estimated_total_inr": round(usd * USD_TO_INR, 2),
            },
        }
    usd = MATHPIX_IMAGE_USD
    return {
        "page_count": 1,
        "ocr_unit_type": "image",
        "cost": {
            "ocr_units": 1,
            "estimated_ocr_usd": usd,
            "estimated_openai_usd": 0.0,
            "estimated_total_usd": usd,
            "estimated_total_inr": round(usd * USD_TO_INR, 2),
        },
    }


def _pdf_page_count(data: bytes) -> int:
    try:
        import fitz

        document = fitz.open(stream=data, filetype="pdf")
        return max(1, document.page_count)
    except Exception:
        return 1


def _normalize_backend_rubric(rubric: dict[str, Any], request: ExamCreate | None = None) -> dict[str, Any]:
    raw = rubric or {}
    metadata = raw.get("metadata") or raw.get("exam") or {}
    questions = raw.get("questions")
    if not isinstance(questions, list) or not questions:
        raise HTTPException(status_code=400, detail="Rubric must contain a non-empty questions array.")
    normalized_questions = []
    for question in questions:
        qid = str(question.get("id") or question.get("qno") or question.get("question_no") or "").strip()
        if not qid:
            raise HTTPException(status_code=400, detail="Every rubric question needs id or qno.")
        marks = float(question.get("marks") or question.get("mark") or 1)
        normalized_questions.append({**question, "id": qid, "marks": marks, "type": question.get("type") or "short_answer"})
    return {
        "exam": {
            "title": metadata.get("paper") or metadata.get("title") or (request.title if request else "Student Copy Grader Exam"),
            "board": metadata.get("board") or (request.board if request else "CBSE"),
            "class_level": metadata.get("class") or metadata.get("class_level") or (request.class_level if request else ""),
            "subject": metadata.get("subject") or (request.subject if request else ""),
            "max_marks": metadata.get("max_marks") or metadata.get("total_marks") or sum(q["marks"] for q in normalized_questions),
        },
        "questions": normalized_questions,
    }


def _rubric_total(rubric: dict[str, Any]) -> float:
    return round(sum(float(question.get("marks", 0)) for question in rubric.get("questions", [])), 2)


def _answers_from_json_or_text(answers_json: str, transcript: str) -> dict[str, str]:
    if answers_json.strip():
        try:
            parsed = json.loads(answers_json)
        except json.JSONDecodeError:
            return _parse_question_entries(answers_json) or {"1": answers_json.strip()}
        if isinstance(parsed, dict) and isinstance(parsed.get("answers"), dict):
            return {str(key): str(value) for key, value in parsed["answers"].items()}
        if isinstance(parsed, dict):
            return {str(key): str(value) for key, value in parsed.items() if key not in {"student", "metadata"}}
    if transcript.strip():
        return _parse_question_entries(transcript) or {"1": transcript.strip()}
    return {}


def _local_grade(rubric: dict[str, Any], answers: dict[str, str], student: dict[str, Any]) -> dict[str, Any]:
    question_results = [_local_grade_question(question, answers.get(str(question.get("id")), "")) for question in rubric.get("questions", [])]
    awarded = round(sum(item["awarded"] for item in question_results), 2)
    possible = round(sum(item["possible"] for item in question_results), 2)
    return {"student": student, "awarded": awarded, "possible": possible, "questionResults": question_results}


def _local_grade_question(question: dict[str, Any], answer: str) -> dict[str, Any]:
    qid = str(question.get("id"))
    possible = float(question.get("marks", 0))
    if not answer.strip():
        return _question_result(qid, 0, possible, answer, ["No answer found."], True, 0.2)

    type_name = str(question.get("type", "short_answer")).lower()
    final_answer = str(question.get("answer") or question.get("final_answer") or question.get("finalAnswer") or "")
    correct_option = question.get("correct_option") or question.get("correctOption")
    if type_name == "mcq" or correct_option:
        expected = _normalize_option(str(correct_option or final_answer))
        actual = _normalize_option(answer)
        matched = bool(expected and expected == actual)
        return _question_result(
            qid,
            possible if matched else 0,
            possible,
            answer,
            ["Correct option selected."] if matched else [f"Expected option {expected or final_answer}."],
            not matched,
            0.96 if matched else 0.55,
        )

    expected_number = _first_number(final_answer)
    if type_name == "numeric" or (expected_number is not None and len(_normalize_text(final_answer).split()) <= 4):
        actual_numbers = _all_numbers(answer)
        tolerance = float(question.get("tolerance", 0))
        matched = expected_number is not None and any(abs(expected_number - value) <= tolerance for value in actual_numbers)
        return _question_result(
            qid,
            possible if matched else 0,
            possible,
            answer,
            ["Numeric answer is within tolerance."] if matched else [f"Expected {expected_number}; found {actual_numbers or 'no number'}."],
            not matched,
            0.94 if matched else 0.5,
        )

    items = question.get("rubric")
    if not isinstance(items, list) or not items:
        keywords = _as_list(question.get("keywords"))
        alternates = _as_list(question.get("alternateAnswers") or question.get("alternate_answers"))
        items = [
            {
                "id": "expected_answer",
                "marks": possible,
                "description": f"Matches expected answer for Q{qid}",
                "keywords": keywords,
                "accepted": [final_answer, *alternates, *keywords],
                "min_keywords": question.get("min_keywords") or 1,
            }
        ]

    item_results = [_local_grade_item(item, answer) for item in items]
    awarded = round(min(possible, sum(item["awarded"] for item in item_results)), 2)
    feedback = [
        f"+{_fmt(item['awarded'])}: {item['description']}." if item["matched"] else f"0/{_fmt(item['possible'])}: Missing or unclear - {item['description']}."
        for item in item_results
    ]
    confidence = round(max(0.25, min(0.95, 0.35 + 0.5 * (awarded / possible if possible else 0))), 2)
    return _question_result(qid, awarded, possible, answer, feedback, confidence < 0.82 or awarded < possible, confidence, item_results)


def _local_grade_item(item: dict[str, Any], answer: str) -> dict[str, Any]:
    accepted = _as_list(item.get("accepted"))
    keywords = _as_list(item.get("keywords"))
    normalized_answer = _normalize_text(answer)
    accepted_match = any(_normalize_text(value) and _normalize_text(value) in normalized_answer for value in accepted)
    keyword_count = sum(1 for value in keywords if _normalize_text(value) in normalized_answer)
    min_keywords = int(item.get("min_keywords") or 1)
    keyword_match = bool(keywords and keyword_count >= min_keywords)
    matched = accepted_match or keyword_match
    marks = float(item.get("marks", 0))
    return {
        "itemId": item.get("id") or "rubric_item",
        "description": item.get("description") or item.get("id") or "Rubric item",
        "awarded": marks if matched else 0,
        "possible": marks,
        "matched": matched,
        "evidence": "accepted phrase matched" if accepted_match else f"{keyword_count}/{len(keywords)} keywords matched",
    }


def _question_result(
    question_id: str,
    awarded: float,
    possible: float,
    answer: str,
    feedback: list[str],
    needs_review: bool,
    confidence: float,
    item_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "questionId": question_id,
        "awarded": round(float(awarded), 2),
        "possible": round(float(possible), 2),
        "answer": answer,
        "feedback": feedback,
        "needsReview": needs_review,
        "confidence": confidence,
        "itemResults": item_results or [],
    }


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [str(item) for item in value.values() if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _normalize_text(value: Any) -> str:
    normalized = (
        str(value or "")
        .replace("π", "pi")
        .replace("Π", "pi")
        .replace("√", "sqrt")
        .replace("×", "x")
        .replace("−", "-")
        .replace("⁻", "-")
        .replace("²", "2")
        .replace("³", "3")
    )
    return " ".join(re.findall(r"[a-z0-9-]+", normalized.lower()))


def _normalize_option(value: str) -> str:
    words = _normalize_text(value).split()
    for index, word in enumerate(words):
        if word in {"option", "answer", "ans", "choose", "selected"} and index + 1 < len(words):
            if re.fullmatch(r"[a-d1-9]", words[index + 1]):
                return words[index + 1]
    for word in words:
        if re.fullmatch(r"[a-d1-9]", word):
            return word
    return words[0] if words else ""


def _first_number(value: Any) -> float | None:
    match = re.search(r"[-+]?(?:\d+\.\d+|\d+|\.\d+)", str(value or ""))
    return float(match.group(0)) if match else None


def _all_numbers(value: Any) -> list[float]:
    return [float(match.group(0)) for match in re.finditer(r"[-+]?(?:\d+\.\d+|\d+|\.\d+)", str(value or ""))]


def _fmt(value: float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")


def _batch_report_payload(batch: dict[str, Any], exam: dict[str, Any], grades: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for grade in grades:
        result = grade.get("result", {})
        possible = float(result.get("possible", 0) or 0)
        awarded = float(result.get("awarded", 0) or 0)
        rows.append(
            {
                "grade_id": grade["id"],
                "student_id": grade.get("student", {}).get("id", ""),
                "student_name": grade.get("student", {}).get("name", ""),
                "awarded": awarded,
                "possible": possible,
                "percent": round((awarded / possible * 100), 1) if possible else 0,
                "status": grade.get("status", ""),
                "review_count": grade.get("review_count", 0),
            }
        )
    possible_scores = [row["percent"] for row in rows if row["possible"]]
    return {
        "batch": batch,
        "exam": {"id": exam.get("id"), "title": exam.get("title"), "subject": exam.get("subject"), "class_level": exam.get("class_level")},
        "summary": {
            "students_graded": len(rows),
            "average_percent": round(sum(possible_scores) / len(possible_scores), 1) if possible_scores else 0,
            "teacher_approved": sum(1 for grade in grades if grade.get("status") == "teacher_approved"),
            "needs_review": sum(1 for grade in grades if grade.get("status") != "teacher_approved"),
            "estimated_cost": batch.get("cost", _empty_cost()),
        },
        "rows": rows,
    }


def _batch_report_csv(report: dict[str, Any]) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Student ID", "Student Name", "Awarded", "Possible", "Percent", "Status", "Review Items"])
    for row in report["rows"]:
        writer.writerow([row["student_id"], row["student_name"], row["awarded"], row["possible"], row["percent"], row["status"], row["review_count"]])
    return stream.getvalue()


def _batch_report_html(report: dict[str, Any]) -> str:
    rows = "\n".join(
        f"<tr><td>{_html(row['student_id'])}</td><td>{_html(row['student_name'])}</td><td>{row['awarded']}/{row['possible']}</td><td>{row['percent']}%</td><td>{_html(row['status'])}</td><td>{row['review_count']}</td></tr>"
        for row in report["rows"]
    )
    cost = report["summary"]["estimated_cost"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{_html(report['exam'].get('title') or 'Batch Report')}</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #17202a; margin: 28px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
    th, td {{ border: 1px solid #d8e0e7; padding: 9px; text-align: left; }}
    th {{ background: #f4f7f9; }}
  </style>
</head>
<body>
  <h1>{_html(report['exam'].get('title') or 'Batch Report')}</h1>
  <p>{_html(report['batch'].get('name', ''))} · {report['summary']['students_graded']} students graded · Average {report['summary']['average_percent']}%</p>
  <p>Estimated provider cost: ${cost.get('estimated_total_usd', 0)} / Rs {cost.get('estimated_total_inr', 0)}</p>
  <table>
    <thead><tr><th>ID</th><th>Name</th><th>Marks</th><th>Percent</th><th>Status</th><th>Review</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""


def _html(value: Any) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _delete_submission_from_store(store: dict[str, Any], submission_id: str) -> bool:
    submission = store["submissions"].pop(submission_id, None)
    for grade_id, grade in list(store["grades"].items()):
        if grade.get("submission_id") == submission_id:
            store["grades"].pop(grade_id, None)
    submission_dir = UPLOAD_DIR / submission_id
    if submission_dir.exists():
        shutil.rmtree(submission_dir)
    return bool(submission)


def _iter_ocr_images(data: bytes, filename: str, content_type: str):
    lowered = filename.lower()
    if content_type == "application/pdf" or lowered.endswith(".pdf"):
        try:
            import fitz
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="PyMuPDF is required for PDF OCR.") from exc
        document = fitz.open(stream=data, filetype="pdf")
        for index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            yield f"{filename} page {index}", pixmap.tobytes("png"), "image/png"
        return
    mime_type = content_type if content_type.startswith("image/") else _mime_from_name(filename)
    yield filename, data, mime_type


async def _mathpix_ocr(client: httpx.AsyncClient, image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "src": f"data:{mime_type};base64,{encoded}",
        "formats": ["text", "latex_styled"],
        "data_options": {"include_asciimath": True, "include_latex": True},
    }
    response = await client.post(
        "https://api.mathpix.com/v3/text",
        headers={
            "app_id": MATHPIX_APP_ID,
            "app_key": MATHPIX_APP_KEY,
            "Content-Type": "application/json",
        },
        json=payload,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Mathpix returned {response.status_code}: {response.text[:240]}")
    return response.json()


def _best_mathpix_text(payload: dict[str, Any]) -> str:
    return str(payload.get("text") or payload.get("latex_styled") or "").strip()


def _parse_question_entries(text: str) -> dict[str, str]:
    clean = text.replace("\r", "").strip()
    if not clean:
        return {}
    pattern = re.compile(r"(?:^|\n)\s*(?:q(?:uestion)?\s*)?(\d+[a-z]?)\s*[\).:\-]\s*", re.IGNORECASE)
    matches = list(pattern.finditer(clean))
    answers: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(clean)
        value = re.sub(r"\n{3,}", "\n\n", clean[start:end].strip())
        if value:
            answers[match.group(1)] = value
    return answers


def _mime_from_name(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith(".tif") or lowered.endswith(".tiff"):
        return "image/tiff"
    if lowered.endswith(".pdf"):
        return "application/pdf"
    return "image/png"
