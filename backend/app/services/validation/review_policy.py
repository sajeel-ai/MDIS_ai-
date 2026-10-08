from app.config import settings


def requires_review(entity, issues, policy: str | None = None, threshold: float | None = None) -> bool:
    if (policy or settings.review_policy) == "all":
        return True
    confidence_threshold = settings.review_confidence_threshold if threshold is None else threshold
    return bool(
        any(issue.severity in {"warning", "error"} for issue in issues)
        or entity.assertion != "present"
        or entity.entity_type == "medication"
        or float(entity.confidence) < confidence_threshold
    )
