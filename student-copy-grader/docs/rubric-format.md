# Rubric Format

The rubric is JSON so it can be edited manually, generated from a marking-scheme PDF later, or exported from a school system.

## Minimal Shape

```json
{
  "exam": {
    "title": "Class X Science Unit Test",
    "board": "CBSE",
    "class_level": "X",
    "subject": "Science",
    "max_marks": 20
  },
  "questions": [
    {
      "id": "1",
      "marks": 1,
      "type": "mcq",
      "answer": "C"
    },
    {
      "id": "2",
      "marks": 2,
      "type": "short_answer",
      "answer": "Dispersion is splitting of white light into its constituent colours.",
      "rubric": [
        {
          "id": "meaning",
          "marks": 1,
          "description": "States that white light splits into colours",
          "keywords": ["white light", "splitting", "colours"],
          "min_keywords": 2
        },
        {
          "id": "medium",
          "marks": 1,
          "description": "Mentions prism or refraction through a medium",
          "keywords": ["prism", "refraction", "medium"],
          "min_keywords": 1
        }
      ]
    }
  ]
}
```

## Student Answers

```json
{
  "student": {
    "id": "S001",
    "name": "Demo Student"
  },
  "answers": {
    "1": "C",
    "2": "White light splits into seven colours when it passes through a prism."
  }
}
```

## Supported Question Types In The First Engine

- `mcq`: exact option matching after normalization
- `numeric`: numeric answer with optional tolerance
- `short_answer`: value-point grading with keywords, accepted phrases, and simple similarity

## Rubric Item Fields

- `id`: stable value-point id
- `marks`: marks for this value point
- `description`: teacher-readable reason
- `accepted`: accepted exact or phrase alternatives
- `keywords`: keywords or phrases to search for
- `min_keywords`: minimum keyword count needed
- `reference`: optional reference sentence for similarity
- `similarity_threshold`: simple text similarity threshold from `0` to `1`

## Design Rule

Every awarded mark should map to a rubric item. Every deduction should have a visible reason.

