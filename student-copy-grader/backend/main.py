from __future__ import annotations

import base64
import json
import os
import re
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

MATHPIX_APP_ID = os.getenv("MATHPIX_APP_ID", "").strip()
MATHPIX_APP_KEY = os.getenv("MATHPIX_APP_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "").strip()
ALLOWED_ORIGINS = [item.strip() for item in os.getenv("ALLOWED_ORIGINS", "*").split(",") if item.strip()]

app = FastAPI(title="Student Copy Grader Backend", version="0.1.0")
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


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "ocr_provider": "mathpix" if _mathpix_configured() else "not_configured",
        "grading_provider": "openai" if OPENAI_API_KEY else "not_configured",
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
            "Return JSON only.",
        ],
        "rubric": request.rubric,
        "student": request.student,
        "answers": request.answers,
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
        return {"raw": output_text, "needs_review": True}


def _mathpix_configured() -> bool:
    return bool(MATHPIX_APP_ID and MATHPIX_APP_KEY)


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
    return "image/png"
