# Research Notes

## Problem

The target workflow is simple from a teacher's point of view:

1. Upload the question paper.
2. Upload the official solution key or marking scheme.
3. Upload scanned student answer copies.
4. Get question-wise marks and clear reasons for deductions.
5. Review only the uncertain cases.

The hard engineering problem is that real school answer copies combine poor scans, varied handwriting, crossed-out work, diagrams, equations, partial methods, alternate valid answers, and subject-specific marking rules.

## Demand

The demand is strong in schools, coaching centers, and home tutors because teachers lose many hours checking handwritten descriptive copies. The value is highest where:

- each teacher checks 40+ copies per test
- answers are descriptive or step-based, not just MCQ
- parents/students ask why marks were deducted
- schools want consistent evaluation and analytics
- teachers want to reuse the same marking scheme across sections

CBSE is a good first target because the board publishes sample question papers and marking schemes. For example, CBSE Academic lists Class X and XII sample question papers and marking schemes for 2025-26, and the marking PDFs provide question-wise solutions and marks:

- [CBSE Class X SQP and Marking Scheme 2025-26](https://cbseacademic.nic.in/sqp_classx_2025-26.html)
- [CBSE Class XII SQP and Marking Scheme 2025-26](https://cbseacademic.nic.in/sqp_classxii_2025-26.html)
- [CBSE main marking scheme page](https://www.cbse.gov.in/cbsenew/marking-scheme.html)

CBSE marking schemes are not always one exact answer. In English, for example, CBSE's 2025-26 Class X marking scheme says the scheme carries suggested value points/sample answers. That means the product must support alternate wording and teacher judgment rather than exact string matching only.

## Supply

Commercial supply exists, which proves market demand:

- [Eklavvya AI answer sheet checking](https://www.eklavvya.com/ai-answer-sheet-checking/) claims AI-assisted handwritten answer-sheet grading and evaluation-time reduction.
- [GradeLab](https://gradelab.io/) positions itself around handwritten exam grading and teacher control.
- [CoGrader](https://cograder.com/) focuses on rubric-based grading and feedback for written work.
- [GradingPal handwritten grading](https://www.gradingpal.com/handwritten-grading) markets OCR plus rubric-based scoring for handwritten assignments.

The gap for this project is a free, open, local-first alternative that teachers can run without paid cloud APIs.

## Research Areas

### 1. Document Scanning And Preprocessing

Needed tasks:

- deskew, denoise, crop, page boundary detection
- split PDF into pages
- detect answer blocks and question numbers
- keep original image crops for teacher review

Open tools:

- OpenCV for image cleanup and segmentation
- PyMuPDF or Poppler for PDF rendering

### 2. OCR And Layout Analysis

Printed question papers and marking schemes are easier than handwritten copies.

Useful open-source tools:

- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR): open OCR/document parsing toolkit supporting many languages.
- [docTR](https://github.com/mindee/doctr): Apache-2.0 OCR library with text detection and recognition.
- [EasyOCR](https://github.com/JaidedAI/EasyOCR): OCR library supporting 80+ languages and scripts.
- Tesseract: useful for printed text, weak for messy handwriting.

### 3. Handwritten Text Recognition

This is the biggest technical risk. For handwritten English line recognition:

- [TrOCR documentation](https://huggingface.co/docs/transformers/en/model_doc/trocr) describes an end-to-end transformer OCR model.
- [microsoft/trocr-base-handwritten](https://huggingface.co/microsoft/trocr-base-handwritten) is intended for OCR on single text-line images.

Important limitation: TrOCR works best on isolated text lines, so the system needs page segmentation before recognition.

### 4. Math OCR

CBSE math/science copies require equations, fractions, diagrams, and steps. General OCR is not enough.

Useful open-source tools:

- [pix2tex / LaTeX-OCR](https://github.com/lukas-blecher/LaTeX-OCR): image of formula to LaTeX.
- [Pix2Text](https://github.com/breezedeus/pix2text): open tool for layout, text, table, and math-formula recognition.
- [Texify](https://pypi.org/project/texify/): converts images/PDFs with math into Markdown/LaTeX.

### 5. Automatic Short Answer Grading

Automatic short-answer grading is an active research area. The common approaches are:

- exact matching for MCQs and numeric answers
- keyword/value-point matching
- semantic similarity using embeddings
- supervised classifiers trained on marked examples
- local or cloud LLM rubric evaluation
- active learning where teacher marks some examples and the system learns the rest

Relevant research and code:

- [Automatic Short Answer Grading: A Survey, IIT Bombay PDF](https://www.cfilt.iitb.ac.in/resources/surveys/2024/survey_dishank_Ai-assisted-Answer-Graiding_2024.pdf)
- [Automatic Short Answer Grading with Feedback](https://arxiv.org/html/2407.12818v2)
- [SentenceTransformers documentation](https://sbert.net/) for semantic similarity models.
- [Computer-Assisted Short Answer Grading with Rubrics using Active Learning](https://github.com/Ganesamanian/Computer-Assisted-Short-Answer-Grading-with-Rubrics-using-Active-Learning)

### 6. Local LLM Grading

For richer feedback, an optional local LLM can be used. It must be constrained to return JSON and cite the rubric item it used.

Useful local tools:

- [Ollama](https://ollama.com/) for local open-model execution.
- [llama.cpp](https://github.com/ggml-org/llama.cpp) for local inference.

This should remain optional because teachers may not have the hardware, and smaller local models can be inconsistent.

## Product Principle

The correct product shape is not "AI replaces the teacher."

The correct product shape is:

- AI reads and pre-grades.
- Teacher sees image, OCR text, marks, and deductions.
- Low-confidence answers are queued first.
- Final marks are locked only after teacher review.

This approach is safer, more acceptable to schools, and more realistic technically.

## MVP Scope

Good first open-source release:

- upload or paste structured marking scheme JSON
- upload structured student answers JSON/CSV
- grade MCQ, numeric, keyword, and short-answer value points
- generate HTML report with marks and reasons
- expose OCR adapter interface for local engines
- provide Streamlit review app

Next release:

- scanned image/PDF OCR import
- teacher correction screen
- answer block to question mapping
- confidence scoring and review queue

