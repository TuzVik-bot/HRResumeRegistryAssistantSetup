from pathlib import Path

from app.config import PROJECT_FILES_DIR


ENV_PATH = PROJECT_FILES_DIR / ".env"


DEFAULT_SETTINGS = {
    "AI_EXTRACTION_ENABLED": "false",
    "AI_PROVIDER": "gemini",
    "AI_MODEL": "gemini-3-flash-preview",
    "AI_API_KEY": "",
    "MATCH_THRESHOLD_AUTO": "90",
    "MATCH_THRESHOLD_REVIEW": "70",
    "MATCH_GAP_MIN": "10",
    "OCR_FALLBACK_ENABLED": "true",
    "LLM_FALLBACK_FOR_UNMATCHED": "false",
    "LLM_FALLBACK_MAX_CANDIDATES": "50",
}


def load_settings() -> dict[str, str]:
    values = DEFAULT_SETTINGS.copy()
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def save_settings(
    enabled: bool,
    provider: str,
    api_key: str,
    model: str = "gemini-3-flash-preview",
    match_threshold_auto: int = 90,
    match_threshold_review: int = 70,
    match_gap_min: int = 10,
    ocr_fallback_enabled: bool = True,
    llm_fallback_for_unmatched: bool = True,
    llm_fallback_max_candidates: int = 50,
) -> None:
    provider = provider.strip() or "gemini"
    model = model.strip() or "gemini-3-flash-preview"
    settings = {
        "AI_EXTRACTION_ENABLED": "true" if enabled else "false",
        "AI_PROVIDER": provider,
        "AI_MODEL": model,
        "AI_API_KEY": api_key.strip(),
        "MATCH_THRESHOLD_AUTO": str(match_threshold_auto),
        "MATCH_THRESHOLD_REVIEW": str(match_threshold_review),
        "MATCH_GAP_MIN": str(match_gap_min),
        "OCR_FALLBACK_ENABLED": "true" if ocr_fallback_enabled else "false",
        "LLM_FALLBACK_FOR_UNMATCHED": "true" if llm_fallback_for_unmatched else "false",
        "LLM_FALLBACK_MAX_CANDIDATES": str(llm_fallback_max_candidates),
    }
    lines = [f"{key}={value}" for key, value in settings.items()]
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def is_ai_enabled() -> bool:
    settings = load_settings()
    return settings.get("AI_EXTRACTION_ENABLED", "false").lower() == "true" and bool(settings.get("AI_API_KEY"))
