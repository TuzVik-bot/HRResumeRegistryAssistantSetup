import re
from typing import Any

from app import database


ERROR_LEVELS = {"error", "critical"}
EVENT_FILTERS = {
    "all": "Все",
    "errors": "Ошибки",
    "upload": "Загрузки",
    "matching": "Сопоставление",
    "export": "Экспорт",
}

_SENSITIVE_KEY_MARKERS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "resume_text",
    "extracted_text",
    "row_data",
    "row_data_json",
    "profile_json",
    "email",
    "phone",
}


def log_event(level: str, category: str, action: str, message: str, context: dict[str, Any] | None = None) -> None:
    try:
        database.insert_event(
            level=level,
            category=category,
            action=action,
            message=message,
            context=sanitize_context(context),
        )
    except Exception:
        # Diagnostics must never break the main user flow.
        return


def recent_events(filter_name: str = "all", limit: int = 1000) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows = [dict(row) for row in database.fetch_recent_events(limit=limit)]
    counts = {
        "all": len(rows),
        "errors": sum(1 for row in rows if row["level"] in ERROR_LEVELS),
        "upload": sum(1 for row in rows if row["category"] == "upload"),
        "matching": sum(1 for row in rows if row["category"] == "matching"),
        "export": sum(1 for row in rows if row["category"] == "export"),
    }
    if filter_name == "errors":
        rows = [row for row in rows if row["level"] in ERROR_LEVELS]
    elif filter_name in {"upload", "matching", "export"}:
        rows = [row for row in rows if row["category"] == filter_name]
    return rows, counts


def sanitize_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not context:
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in context.items():
        sanitized[key] = _sanitize_value(key, value)
    return sanitized


def _sanitize_value(key: str, value: Any) -> Any:
    key_lower = key.lower()
    if any(marker in key_lower for marker in _SENSITIVE_KEY_MARKERS):
        return "[скрыто]"
    if isinstance(value, dict):
        return {child_key: _sanitize_value(child_key, child_value) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(key, item) for item in value[:20]]
    if isinstance(value, str):
        if _looks_like_email(value) or _looks_like_phone(value):
            return "[скрыто]"
        if len(value) > 400:
            return value[:397] + "..."
    return value


def _looks_like_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()))


def _looks_like_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return len(digits) >= 10 and len(digits) <= 16
