# Student Copy Grader Backend

Optional production OCR and pilot backend for the public `index.html` app.

The GitHub Pages frontend cannot safely store API keys. This backend keeps
Mathpix and OpenAI credentials server-side, then supports the paid-pilot
workflow: exams, batches, student submissions, OCR, grading, teacher review,
privacy deletion, and batch reports.

## Recommended Providers

- Mathpix for handwritten STEM/math OCR.
- OpenAI for rubric reasoning and low-confidence feedback.
- Browser Tesseract mode remains a free fallback, not the recommended path for
  handwritten maths.

## Setup

```bash
cd student-copy-grader/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env`:

```bash
MATHPIX_APP_ID=...
MATHPIX_APP_KEY=...
OPENAI_API_KEY=...
OPENAI_MODEL=...
ALLOWED_ORIGINS=https://yosoyun.github.io,http://localhost:8000
COPYGRADER_DATA_DIR=/tmp/student-copy-grader-data
COPYGRADER_RETENTION_DAYS=30
COPYGRADER_USD_TO_INR=95
```

Run locally:

```bash
uvicorn main:app --reload --port 8787
```

In the frontend, choose `Quality backend OCR` and set:

```text
http://localhost:8787
```

## Endpoints

```text
GET /health
POST /api/exams
POST /api/batches
POST /api/submissions
POST /api/submissions/{id}/ocr
POST /api/submissions/{id}/grade
PATCH /api/grades/{id}/review
GET /api/batches/{id}/reports?format=json|csv|html
DELETE /api/submissions/{id}
POST /api/privacy/purge-expired
GET /api/privacy/policy
POST /api/ocr/extract
POST /api/grade/evaluate
```

The new pilot workflow is:

1. `POST /api/exams` with the question paper, solution key, rubric, subject, and class.
2. `POST /api/batches` with the exam id and student list.
3. `POST /api/submissions` with `consent_confirmed=true`, student details, and scanned files or extracted answers.
4. `POST /api/submissions/{id}/ocr` to run Mathpix OCR when files are present.
5. `POST /api/submissions/{id}/grade` to generate suggested marks.
6. `PATCH /api/grades/{id}/review` after the teacher approves or edits marks.
7. `GET /api/batches/{id}/reports` to export JSON, CSV, or HTML reports.

`/api/ocr/extract` accepts multipart form data:

```text
files: one or more images/PDFs
paper_text: optional question paper text
rubric_text: optional rubric JSON
student_id: optional student identifier
```

It returns:

```json
{
  "provider": "mathpix",
  "answers": { "1": "...", "2": "..." },
  "transcript": "...",
  "warnings": []
}
```

## Production Notes

- Require teacher review for low-confidence answers.
- Log provider cost per copy before scaling to full batches. The backend estimates Mathpix OCR cost when submissions are uploaded.
- Do a pilot with at least 10 real checked copies before trusting routine use.
- Do not expose `.env` or API keys in GitHub Pages.
- Keep `COPYGRADER_DATA_DIR` outside the repository. Uploaded scans are runtime data, not source code.
- Use `DELETE /api/submissions/{id}` and `POST /api/privacy/purge-expired` for the default 30-day data retention policy.
