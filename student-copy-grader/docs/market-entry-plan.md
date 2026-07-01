# Indian Market Entry Plan

Student Copy Grader should enter the market as a CBSE/Indian school copy-checking assistant, not as a generic AI grader.

## Positioning

First wedge:

- Class 10-12 CBSE Maths, Physics, and Chemistry.
- Coaching centres with 100-1,000 students.
- Private CBSE schools where teachers check frequent written tests.

Promise:

- The system suggests marks, deduction reasons, confidence, and reports.
- The teacher approves final marks.
- Admin staff can scan and upload copies without deciding marks.

Avoid claiming:

- fully automatic board-exam correction
- perfect handwriting OCR
- perfect support for every subject from day one

## Offer

Free public app:

- demo grading
- rubric import
- browser-local records
- sample CBSE Maths flow
- lead generation for teachers and schools

Paid-quality backend:

- Mathpix OCR for handwritten STEM/math
- OpenAI-assisted rubric reasoning where configured
- batch upload
- teacher review and overrides
- HTML, CSV, and JSON reports
- default 30-day scan retention

## Pricing

Suggested pilot pricing:

- Teacher: Rs 999-1,999/month.
- Coaching centre: Rs 4,999-14,999/month.
- School annual: Rs 25,000 for small schools, Rs 75,000 for medium schools, Rs 1.5L+ for larger schools.
- Per-exam batch: Rs 499-1,999 for early pilots.

Provider cost estimate:

- Mathpix PDF OCR: about USD 0.005/page.
- 40 students x 5 pages = 200 pages = about USD 1 OCR cost.
- Add OpenAI grading/feedback cost depending on transcript size and feedback depth.
- Use the in-app calculator for quick pilot quotes.

## 90-Day Execution

Days 0-30:

- Use one polished Class XII Maths demo.
- Record a 3-minute English/Hindi demo video.
- Contact 30 coaching centres and 30 CBSE school HODs.
- Offer first 3 batches free for anonymized accuracy feedback.

Days 31-60:

- Run 5-10 real pilots.
- Measure time saved, OCR failures, mark agreement, and teacher override rate.
- Convert the best 2-3 pilots to paid plans.

Days 61-90:

- Add batch analytics and parent-ready PDF/HTML reports.
- Publish an anonymized case study.
- Add a referral offer for teachers and coaching centres.

## Sales Script

Use this simple pitch:

> We do not replace teachers. We reduce correction time. AI reads the copy, suggests marks and reasons, and the teacher approves.

## Success Metrics

Product:

- 40-copy batch processed in under 35 minutes including teacher review.
- At least 85% of question-level AI marks within half a mark of the teacher final marks.
- 95% of uncertain answers flagged for review.
- Reports download for every reviewed student.

Business:

- 10 pilots completed in 90 days.
- 3 paid conversions.
- Rs 25,000+ monthly recurring or batch revenue by the end of the pilot.

## Implementation Mapping

Frontend:

- Grade Copies: free demo and teacher workflow.
- Quality OCR: backend setup and OCR provider explanation.
- Market Pilot: market plan, pricing, cost calculator, proof links.

Backend:

- `POST /api/exams`
- `POST /api/batches`
- `POST /api/submissions`
- `POST /api/submissions/{id}/ocr`
- `POST /api/submissions/{id}/grade`
- `PATCH /api/grades/{id}/review`
- `GET /api/batches/{id}/reports`
- `DELETE /api/submissions/{id}`
- `POST /api/privacy/purge-expired`
