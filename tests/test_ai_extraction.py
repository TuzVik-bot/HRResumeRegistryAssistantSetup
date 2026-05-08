import pytest
from pydantic import ValidationError

from app.ai_extraction import (
    AIExtractionError,
    AIResumeProfile,
    MAX_AI_CHARS,
    build_prompt,
    call_gemini_resume_extraction,
    match_candidate_with_llm,
    merge_profiles,
)


def test_ai_resume_profile_validates_strict_json_shape():
    profile = AIResumeProfile.model_validate(
        {
            "full_name_original": "HLEB ARBUZAU",
            "full_name_ru_guess": "Арбузов Глеб",
            "email": "hleb.arbuzau@gmail.com",
            "phone": "",
            "city": "",
            "current_position": "Embedded Software Engineer",
            "current_company": "JSC Peleng",
            "years_experience": None,
            "education": "",
            "english_level": "",
            "programming_languages": ["C"],
            "embedded_stack": ["STM32"],
            "protocols": ["SPI"],
            "tools": [],
            "summary_ru": "Embedded-разработчик.",
            "interview_questions_ru": ["Какой опыт с STM32?"],
            "confidence": 0.9,
        }
    )
    assert profile.full_name_ru_guess == "Арбузов Глеб"


def test_ai_resume_profile_rejects_extra_fields():
    with pytest.raises(ValidationError):
        AIResumeProfile.model_validate(
            {
                "full_name_original": "",
                "full_name_ru_guess": "",
                "email": "",
                "phone": "",
                "city": "",
                "current_position": "",
                "current_company": "",
                "years_experience": None,
                "education": "",
                "english_level": "",
                "programming_languages": [],
                "embedded_stack": [],
                "protocols": [],
                "tools": [],
                "summary_ru": "",
                "interview_questions_ru": [],
                "confidence": 0.0,
                "unexpected": "field",
            }
        )


def test_build_prompt_limits_resume_text_to_6000_characters():
    long_text = "a" * (MAX_AI_CHARS + 500)
    prompt = build_prompt(long_text[:MAX_AI_CHARS], "тест")
    assert "a" * MAX_AI_CHARS in prompt
    assert "a" * (MAX_AI_CHARS + 1) not in prompt


def test_merge_profiles_preserves_local_and_adds_ai_skills():
    local = {"full_name_original": "Файл резюме", "programming_languages": ["C"], "embedded_stack": [], "protocols": [], "tools": []}
    ai = {
        "full_name_original": "Vitali Chachukha",
        "programming_languages": ["C++"],
        "embedded_stack": ["Yocto"],
        "protocols": [],
        "tools": ["Git"],
        "confidence": 0.8,
    }
    merged = merge_profiles(local, ai)
    assert merged["full_name_original"] == "Vitali Chachukha"
    assert set(merged["key_skills"]) == {"C", "C++", "Yocto", "Git"}
    assert merged["ai_confidence"] == 0.8


def test_call_gemini_resume_extraction_wraps_timeout(monkeypatch):
    def fake_urlopen(*args, **kwargs):
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr("app.ai_extraction.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(AIExtractionError, match="timed out"):
        call_gemini_resume_extraction("key", "gemini-test", "resume text", "test")


def test_match_candidate_with_llm_returns_error_on_timeout(monkeypatch):
    def fake_urlopen(*args, **kwargs):
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr("app.ai_extraction.urllib.request.urlopen", fake_urlopen)

    matched_id, confidence, reason = match_candidate_with_llm(
        candidate={"full_name": "Иван Иванов", "vacancy": "Engineer", "row_data": {}},
        top_resumes=[{"db_id": 10, "original_filename": "ivan.pdf", "extracted_text": "Иван Иванов"}],
        api_key="key",
        model="gemini-test",
    )

    assert matched_id is None
    assert confidence == 0.0
    assert "LLM matching error" in reason
    assert "timed out" in reason
