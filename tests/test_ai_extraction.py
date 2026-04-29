import pytest
from pydantic import ValidationError

from app.ai_extraction import AIResumeProfile, MAX_AI_CHARS, build_prompt, merge_profiles


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
