import re
import json
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
RESUME_ERROR_ACTIONS = {"resume_processing_error", "resume_batch_failed", "resume_scan_error"}
LEGACY_DOC_LIBREOFFICE_DETAIL = "Для файлов .doc требуется установленный LibreOffice"

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


def resume_error_report(limit: int = 1000) -> list[dict[str, Any]]:
    report = []
    for row in database.fetch_recent_events(limit=limit):
        if row["action"] not in RESUME_ERROR_ACTIONS:
            continue
        context = _parse_context(row["context_json"])
        if row["action"] == "resume_processing_error" and context.get("format") == ".doc":
            detail = str(context.get("detail", ""))
            if "LibreOffice" in detail:
                continue
        report.append(
            {
                "created_at": row["created_at"],
                "level": row["level"],
                "action": row["action"],
                "message": row["message"],
                "filename": context.get("filename", ""),
                "format": context.get("format", ""),
                "detail": context.get("detail", ""),
                "files_total": context.get("files_total", ""),
                "failed": context.get("failed", ""),
                "skipped": context.get("skipped", ""),
            }
        )
    return report


def resume_error_summary(limit: int = 1000) -> dict[str, Any]:
    rows = resume_error_report(limit=limit)
    return {
        "count": len(rows),
        "latest": rows[0] if rows else None,
    }


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


def _parse_context(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
