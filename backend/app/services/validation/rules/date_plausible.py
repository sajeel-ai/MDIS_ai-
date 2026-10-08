import re
from datetime import date
from .base import EntityData, ValidationIssue, issue

DATES = re.compile(r"\b(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4})\b")

def validate(entity: EntityData) -> ValidationIssue | None:
    text = " ".join(str(v) for v in (entity.raw_text, entity.normalized_value, (entity.details or {}).get("date")) if v)
    for value in DATES.findall(text):
        try:
            if "-" in value:
                date.fromisoformat(value)
            else:
                month, day, year = map(int, value.split("/"))
                date(year, month, day)
        except ValueError:
            return issue("DATE_PLAUSIBLE", "warning", "Date value is not a plausible calendar date.")
    return None
