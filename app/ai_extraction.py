import json
import re
import urllib.error
import urllib.request
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import database
from app.settings import load_settings
from app.skills import flatten_skills


MAX_AI_CHARS = 6000


class AIResumeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name_original: str = ""
    full_name_ru_guess: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    current_position: str = ""
    current_company: str = ""
    years_experience: float | None = None
    education: str = ""
    english_level: str = ""
    programming_languages: list[str] = Field(default_factory=list)
    embedded_stack: list[str] = Field(default_factory=list)
    protocols: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    summary_ru: str = ""
    interview_questions_ru: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


def should_use_ai_for_local_profile(profile: dict[str, Any]) -> bool:
    important_fields = [
        "full_name_original",
        "email",
        "phone",
        "current_position",
        "current_company",
    ]
    filled = sum(1 for field in important_fields if profile.get(field))
    return filled <= 1


def enrich_resume_with_ai_if_needed(
    resume_id: int,
    file_hash: str,
    resume_text: str,
    local_profile: dict[str, Any],
    reason: str,
) -> tuple[dict[str, Any], str | None]:
    settings = load_settings()
    if not file_hash:
        return local_profile, "file_hash не задан"
    if settings.get("AI_EXTRACTION_ENABLED", "false").lower() != "true":
        return local_profile, None
    if settings.get("AI_PROVIDER", "gemini").lower() != "gemini":
        return local_profile, "AI провайдер пока не поддерживается"
    api_key = settings.get("AI_API_KEY", "").strip()
    if not api_key:
        return local_profile, "AI ключ не задан"

    provider = "gemini"
    model = settings.get("AI_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash"
    cached = database.get_cached_ai_response(file_hash, provider, model)
    try:
        ai_profile = cached or call_gemini_resume_extraction(api_key, model, resume_text, reason)
        if not cached:
            database.upsert_ai_response(file_hash, provider, model, ai_profile)
        merged = merge_profiles(local_profile, ai_profile)
        database.update_resume_profile(resume_id, merged, ai_profile=ai_profile, processing_error=None)
        return merged, None
    except (AIExtractionError, ValidationError, ValueError) as exc:
        processing_error = f"AI extraction failed: {exc}"
        database.update_resume_profile(resume_id, local_profile, processing_error=processing_error)
        return local_profile, processing_error


def call_gemini_resume_extraction(api_key: str, model: str, resume_text: str, reason: str) -> dict[str, Any]:
    prompt = build_prompt(resume_text[:MAX_AI_CHARS], reason)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise AIExtractionError(str(exc)) from exc
    text = _extract_gemini_text(data)
    parsed = AIResumeProfile.model_validate(_strict_json_loads(text))
    return parsed.model_dump()


def build_prompt(resume_text: str, reason: str) -> str:
    return f"""
Ты извлекаешь структурированный профиль из резюме для HR-реестра.
Верни только строгий JSON без Markdown, пояснений и комментариев.
Если данных нет, верни пустую строку, пустой массив, null или 0.0 согласно схеме.
Причина AI-обработки: {reason}

Схема JSON:
{{
  "full_name_original": "",
  "full_name_ru_guess": "",
  "email": "",
  "phone": "",
  "city": "",
  "current_position": "",
  "current_company": "",
  "years_experience": null,
  "education": "",
  "english_level": "",
  "programming_languages": [],
  "embedded_stack": [],
  "protocols": [],
  "tools": [],
  "summary_ru": "",
  "interview_questions_ru": [],
  "confidence": 0.0
}}

Текст резюме, максимум 6000 символов:
{resume_text}
""".strip()


def merge_profiles(local_profile: dict[str, Any], ai_profile: dict[str, Any]) -> dict[str, Any]:
    merged = local_profile.copy()
    for key, value in ai_profile.items():
        if key == "confidence":
            merged["ai_confidence"] = value
            continue
        if key in {"programming_languages", "embedded_stack", "protocols", "tools", "interview_questions_ru"}:
            merged[key] = sorted(set((merged.get(key) or []) + (value or [])), key=str.lower)
        elif value not in ("", None, []):
            merged[key] = value
    merged["key_skills"] = flatten_skills(
        {
            "programming_languages": merged.get("programming_languages", []),
            "embedded_stack": merged.get("embedded_stack", []),
            "protocols": merged.get("protocols", []),
            "tools": merged.get("tools", []),
        }
    )
    return merged


def _extract_gemini_text(data: dict[str, Any]) -> str:
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise AIExtractionError("Gemini response has no text") from exc


def _strict_json_loads(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


class AIExtractionError(Exception):
    pass
