# Student Copy Grader Backend

Optional production OCR backend for the public `index.html` app.

The GitHub Pages frontend cannot safely store API keys. This backend keeps
Mathpix and OpenAI credentials server-side, then returns extracted answers to
the browser app.

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
POST /api/ocr/extract
POST /api/grade/evaluate
```

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
- Log provider cost per copy before scaling to full batches.
- Do a pilot with at least 10 real checked copies before trusting routine use.
- Do not expose `.env` or API keys in GitHub Pages.
