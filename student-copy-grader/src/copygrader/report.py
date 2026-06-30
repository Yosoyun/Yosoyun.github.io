from __future__ import annotations

from html import escape
from pathlib import Path

from .models import GradingResult, Rubric


def render_html_report(rubric: Rubric, result: GradingResult) -> str:
    student_name = result.student.name or result.student.id
    rows = "\n".join(_question_row(question) for question in result.question_results)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(rubric.exam.title)} - {escape(student_name)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2933; }}
    h1 {{ font-size: 28px; margin-bottom: 4px; }}
    .summary {{ margin: 16px 0 24px; font-size: 18px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 10px; vertical-align: top; text-align: left; }}
    th {{ background: #f0f4f8; }}
    .review {{ color: #9a3412; font-weight: 700; }}
    .ok {{ color: #166534; font-weight: 700; }}
    .feedback {{ margin: 0; padding-left: 18px; }}
    .answer {{ white-space: pre-wrap; max-width: 520px; }}
  </style>
</head>
<body>
  <h1>{escape(rubric.exam.title)}</h1>
  <div>Student: {escape(student_name)} ({escape(result.student.id)})</div>
  <div class="summary">Total: <strong>{result.awarded:g}/{result.possible:g}</strong></div>
  <table>
    <thead>
      <tr>
        <th>Question</th>
        <th>Marks</th>
        <th>Review</th>
        <th>Student Answer</th>
        <th>Feedback</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>
"""


def write_html_report(path: str | Path, rubric: Rubric, result: GradingResult) -> None:
    Path(path).write_text(render_html_report(rubric, result), encoding="utf-8")


def _question_row(question) -> str:
    status_class = "review" if question.needs_review else "ok"
    status = "Review" if question.needs_review else "OK"
    feedback = "".join(f"<li>{escape(line)}</li>" for line in question.feedback)
    return f"""<tr>
  <td>{escape(question.question_id)}</td>
  <td>{question.awarded:g}/{question.possible:g}</td>
  <td class="{status_class}">{status}<br><small>confidence {question.confidence:.2f}</small></td>
  <td class="answer">{escape(question.answer)}</td>
  <td><ul class="feedback">{feedback}</ul></td>
</tr>"""

