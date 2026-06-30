from __future__ import annotations

import json
from dataclasses import asdict

import streamlit as st

from copygrader.grading import grade_submission
from copygrader.report import render_html_report
from copygrader.rubric import parse_rubric, parse_submission


st.set_page_config(page_title="Student Copy Grader", layout="wide")
st.title("Student Copy Grader")
st.caption("Local-first rubric grading prototype. No paid API calls.")

left, right = st.columns(2)

with left:
    st.subheader("Rubric JSON")
    rubric_file = st.file_uploader("Upload rubric", type=["json"])
    rubric_text = st.text_area("Or paste rubric JSON", height=360)

with right:
    st.subheader("Student Answers JSON")
    answers_file = st.file_uploader("Upload student answers", type=["json"])
    answers_text = st.text_area("Or paste student answers JSON", height=360)


def _read_json(uploaded_file, pasted_text: str):
    if uploaded_file is not None:
        return json.loads(uploaded_file.read().decode("utf-8"))
    if pasted_text.strip():
        return json.loads(pasted_text)
    return None


if st.button("Grade", type="primary"):
    try:
        rubric_data = _read_json(rubric_file, rubric_text)
        answers_data = _read_json(answers_file, answers_text)
        if rubric_data is None or answers_data is None:
            st.error("Please upload or paste both rubric JSON and student answers JSON.")
            st.stop()

        rubric = parse_rubric(rubric_data)
        submission = parse_submission(answers_data)
        result = grade_submission(rubric, submission)

        st.success(f"{submission.student.name or submission.student.id}: {result.awarded:g}/{result.possible:g}")
        st.dataframe(
            [
                {
                    "Question": item.question_id,
                    "Marks": f"{item.awarded:g}/{item.possible:g}",
                    "Confidence": item.confidence,
                    "Review": item.needs_review,
                    "Feedback": " ".join(item.feedback),
                }
                for item in result.question_results
            ],
            use_container_width=True,
        )

        report_html = render_html_report(rubric, result)
        st.download_button("Download HTML report", report_html, file_name="grading-report.html", mime="text/html")
        st.download_button(
            "Download JSON result",
            json.dumps(asdict(result), indent=2),
            file_name="grading-result.json",
            mime="application/json",
        )
    except Exception as exc:
        st.exception(exc)

