# Student Copy Grader

Free, local-first assistant for checking scanned student answer copies against a question paper, answer key, and marking scheme.

This project is designed for CBSE-style school evaluation where a teacher may need to check 40+ handwritten copies and still explain exactly why marks were deducted.

## Current Position

The realistic first version is a teacher-assist system, not a fully automatic final examiner.

It should:

- read scanned copies locally when OCR tools are installed
- let a teacher verify the OCR text beside the original scan
- apply a structured marking scheme question by question
- give marks, deducted reasons, and review flags
- avoid paid APIs and keep student data on the teacher's machine

It should not silently finalize marks when handwriting, equations, diagrams, or alternative methods are uncertain.

## Why This Is Needed

Teachers commonly grade batches of 40, 80, or 200+ copies. Manual checking is slow, tiring, and inconsistent. Commercial AI grading products exist, but most are closed, paid, cloud-based, or institution-priced. The open-source world has strong parts - OCR, handwritten text recognition, math OCR, semantic similarity, local LLMs - but not a complete free CBSE-focused workflow.

## Free And Local Architecture

Recommended stack:

- App: Streamlit or FastAPI, local machine first
- OCR/layout: PaddleOCR, docTR, EasyOCR, Tesseract as swappable engines
- Handwriting: TrOCR-style line recognition for English handwriting, with line segmentation
- Math OCR: pix2tex/Pix2Text for equation crops
- Grading: deterministic rubric checks first, semantic similarity second, optional local LLM via Ollama
- Storage: SQLite plus local folders
- Review: teacher confirms OCR and marks before export

No paid API is required.

## Quick Start

From this folder:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m copygrader grade examples/cbse_science_demo_rubric.json examples/student_answers_demo.json --out report.html
```

Then open `report.html`.

Optional local web app:

```bash
pip install -e ".[app]"
streamlit run app.py
```

Optional local OCR:

```bash
pip install -e ".[ocr]"
```

Tesseract also needs the system binary installed separately. On macOS:

```bash
brew install tesseract
```

## Project Files

- `docs/research.md` - demand, supply, research areas, tool landscape
- `docs/architecture.md` - end-to-end system design
- `docs/rubric-format.md` - marking scheme JSON format
- `docs/evaluation-plan.md` - pilot protocol and accuracy metrics
- `index.html` - public browser app for GitHub Pages
- `src/copygrader/grading.py` - first scoring engine
- `src/copygrader/ocr.py` - local OCR adapter skeleton
- `app.py` - local Streamlit teacher-review prototype
- `examples/` - demo rubric and student answers

## Development Roadmap

1. Structured answer grading from JSON/CSV input.
2. OCR import with teacher correction screen.
3. Page segmentation: question number detection, answer block mapping, image crop review.
4. CBSE marking-scheme importer for official PDFs.
5. Math and diagram-aware grading helpers.
6. Local LLM rubric evaluator with strict JSON output and confidence flags.
7. Active learning: teacher grades a few copies, system learns common answer variants.
8. Batch reports: marksheet, feedback, class analytics, common mistakes.

## Sources

The initial research summary links to official CBSE pages, OCR projects, ASAG papers, and commercial competitors in `docs/research.md`.
