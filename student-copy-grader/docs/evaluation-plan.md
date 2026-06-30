# Evaluation Plan

This project must be measured like an education tool, not a demo.

## Ground Truth

For every pilot exam, keep four layers:

1. Original scanned answer image.
2. OCR text corrected by a human reviewer.
3. Teacher's official marks per question.
4. Teacher's deduction reasons per question.

The system should be judged against the teacher-approved layer, not against its own OCR.

## Pilot Dataset

Start small:

- 1 subject
- 1 class
- 1 chapter test
- 40 answer copies
- 5 to 10 questions
- official marking scheme

Anonymize names and roll numbers before using copies for model testing or open-source examples.

## Metrics

OCR:

- character error rate
- word error rate
- unreadable-answer rate
- question-block mapping accuracy

Grading:

- exact mark agreement with teacher
- within-0.5-mark agreement
- within-1-mark agreement
- false full-mark rate
- false zero-mark rate
- teacher override rate

Workflow:

- minutes per copy before using the tool
- minutes per copy after using the tool
- percentage of answers needing review
- teacher satisfaction score

## Release Gates

The first public release should not claim autonomous grading.

Suggested gates:

- MCQ/numeric answers: 95 percent or higher exact agreement after OCR correction
- short-answer value points: 80 percent or higher within-1-mark agreement after OCR correction
- scanned handwritten answers: require teacher review unless OCR confidence is high
- final report: every deduction must map to a rubric item

## Human Review Policy

Always flag for review when:

- OCR confidence is low
- answer is blank or unreadable
- score is near pass/fail boundary
- marks are deducted on a high-value question
- student answer uses an alternate method not covered by the rubric
- model and deterministic rubric disagree

## Fairness And Safety

The app should grade content, not handwriting neatness. Handwriting quality can be used only as an OCR confidence signal, never as a mark deduction reason unless the teacher's rubric explicitly says the answer is unreadable.

Do not send student scans to external services by default.

