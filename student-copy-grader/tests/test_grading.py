from copygrader.grading import grade_submission
from copygrader.rubric import parse_rubric, parse_submission


def test_grades_demo_submission_full_marks():
    rubric = parse_rubric(
        {
            "exam": {"title": "Demo"},
            "questions": [
                {"id": "1", "marks": 1, "type": "mcq", "answer": "B"},
                {"id": "2", "marks": 2, "type": "numeric", "answer": "12", "tolerance": 0.5},
                {
                    "id": "3",
                    "marks": 2,
                    "type": "short_answer",
                    "answer": "White light splits into colours through a prism.",
                    "rubric": [
                        {
                            "id": "split",
                            "marks": 1,
                            "description": "White light splits into colours",
                            "keywords": ["white light", "splits", "colours"],
                            "min_keywords": 2,
                        },
                        {
                            "id": "prism",
                            "marks": 1,
                            "description": "Mentions prism",
                            "keywords": ["prism"],
                        },
                    ],
                },
            ],
        }
    )
    submission = parse_submission(
        {
            "student": {"id": "S001"},
            "answers": {
                "1": "option b",
                "2": "12.2",
                "3": "White light splits into many colours using a prism.",
            },
        }
    )

    result = grade_submission(rubric, submission)

    assert result.awarded == 5
    assert result.possible == 5
    assert all(not question.needs_review for question in result.question_results[:2])


def test_short_answer_partial_marks_and_review_flag():
    rubric = parse_rubric(
        {
            "exam": {"title": "Demo"},
            "questions": [
                {
                    "id": "1",
                    "marks": 2,
                    "type": "short_answer",
                    "rubric": [
                        {
                            "id": "one",
                            "marks": 1,
                            "description": "Mentions photosynthesis",
                            "keywords": ["photosynthesis"],
                        },
                        {
                            "id": "two",
                            "marks": 1,
                            "description": "Mentions chlorophyll",
                            "keywords": ["chlorophyll"],
                        },
                    ],
                }
            ],
        }
    )
    submission = parse_submission({"student": {"id": "S001"}, "answers": {"1": "Plants do photosynthesis."}})

    result = grade_submission(rubric, submission)

    question = result.question_results[0]
    assert question.awarded == 1
    assert question.needs_review is True
    assert "chlorophyll" in " ".join(question.feedback).lower()

