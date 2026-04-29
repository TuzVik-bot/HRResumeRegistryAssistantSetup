from app.matching import classify_match, score_candidate_resume
from tests.fixtures.sample_candidates import (
    ARBUZAU_RESUME,
    ARBUZOV_CANDIDATE,
    CHACHUKHA_CANDIDATE,
    CHACHUKHA_RESUME,
)


def test_matching_score_uses_name_vacancy_and_skills():
    candidate = {
        "full_name": "Арбузов Глеб",
        "vacancy": "Embedded Software Engineer",
        "row_data": {
            "Фамилия, имя": "Арбузов Глеб",
            "вакансия": "Embedded Software Engineer",
            "оценка рекрутера": "STM32 FreeRTOS CAN C++",
        },
    }
    resume = {
        "original_filename": "Hleb_Arbuzau_Embedded.pdf",
        "profile": {
            "full_name_original": "Hleb Arbuzau",
            "email": "",
            "phone": "",
            "current_position": "Embedded Software Engineer",
            "current_company": "",
            "key_skills": ["stm32", "freertos", "can", "c++"],
        },
    }
    score, reason = score_candidate_resume(candidate, resume)
    assert score >= 55
    assert "transliteration" in reason
    assert "overlapping skills" in reason


def test_classify_match_thresholds_and_gap():
    assert classify_match(92, 80) == "matched"
    assert classify_match(92, 88) == "review"
    assert classify_match(75, 10) == "review"
    assert classify_match(65, 10) == "unmatched"


def test_sample_candidate_arbuzov_matches_hleb_arbuzau_resume():
    confidence, reason = score_candidate_resume(ARBUZOV_CANDIDATE, ARBUZAU_RESUME)
    assert classify_match(confidence, 0) == "matched"
    assert confidence >= 90
    assert "transliteration" in reason
    assert "Peleng" in reason or "peleng" in reason
    assert "embedded vacancy" in reason
    assert "overlapping skills" in reason


def test_sample_candidate_chechukha_matches_vitali_chachukha_resume():
    confidence, reason = score_candidate_resume(CHACHUKHA_CANDIDATE, CHACHUKHA_RESUME)
    assert classify_match(confidence, 0) == "matched"
    assert confidence >= 90
    assert "transliteration" in reason
    assert "overlapping skills" in reason


def test_match_does_not_depend_on_resume_filename():
    resume = {
        **ARBUZAU_RESUME,
        "original_filename": "document_001.pdf",
    }
    confidence, reason = score_candidate_resume(ARBUZOV_CANDIDATE, resume)
    assert classify_match(confidence, 0) == "matched"
    assert confidence >= 90
    assert "сходство имени файла" not in reason or "document_001" not in reason
