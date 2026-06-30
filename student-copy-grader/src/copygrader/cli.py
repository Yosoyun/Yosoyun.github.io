from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .grading import grade_submission
from .report import write_html_report
from .rubric import load_rubric, load_submission


def main() -> None:
    parser = argparse.ArgumentParser(prog="copygrader")
    subparsers = parser.add_subparsers(dest="command", required=True)

    grade_parser = subparsers.add_parser("grade", help="Grade one student submission against a rubric")
    grade_parser.add_argument("rubric", help="Path to rubric JSON")
    grade_parser.add_argument("submission", help="Path to student answers JSON")
    grade_parser.add_argument("--out", help="Write an HTML report to this path")
    grade_parser.add_argument("--json-out", help="Write machine-readable grading result JSON")

    args = parser.parse_args()
    if args.command == "grade":
        _grade(args)


def _grade(args: argparse.Namespace) -> None:
    rubric = load_rubric(args.rubric)
    submission = load_submission(args.submission)
    result = grade_submission(rubric, submission)

    print(f"{result.student.id}: {result.awarded:g}/{result.possible:g}")
    for question in result.question_results:
        review = " REVIEW" if question.needs_review else ""
        print(f"Q{question.question_id}: {question.awarded:g}/{question.possible:g}{review}")

    if args.out:
        write_html_report(args.out, rubric, result)
        print(f"HTML report written to {args.out}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        print(f"JSON result written to {args.json_out}")


if __name__ == "__main__":
    main()

