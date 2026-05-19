from app import config, database, matching, settings
from app.matching import classify_match, run_matching, score_candidate_resume
from tests.fixtures.sample_candidates import (
    ARBUZAU_RESUME,
    ARBUZOV_CANDIDATE,
    CHACHUKHA_CANDIDATE,
    CHACHUKHA_RESUME,
)


def test_matching_score_uses_only_name_transliteration():
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
    assert score >= 90
    assert "ФИО/транслитерация" in reason
    assert "overlapping skills" not in reason


def test_classify_match_thresholds_and_gap():
    assert classify_match(92, 80) == "matched"
    assert classify_match(92, 88) == "review"
    assert classify_match(95, 94) == "matched"
    assert classify_match(75, 10) == "review"
    assert classify_match(65, 10) == "unmatched"


def test_sample_candidate_arbuzov_matches_hleb_arbuzau_resume():
    confidence, reason = score_candidate_resume(ARBUZOV_CANDIDATE, ARBUZAU_RESUME)
    assert classify_match(confidence, 0) == "matched"
    assert confidence >= 90
    assert "ФИО/транслитерация" in reason
    assert "embedded vacancy" not in reason
    assert "overlapping skills" not in reason


def test_sample_candidate_chechukha_matches_vitali_chachukha_resume():
    confidence, reason = score_candidate_resume(CHACHUKHA_CANDIDATE, CHACHUKHA_RESUME)
    assert classify_match(confidence, 0) == "matched"
    assert confidence >= 90
    assert "ФИО/транслитерация" in reason
    assert "overlapping skills" not in reason


def test_match_does_not_depend_on_resume_filename():
    resume = {
        **ARBUZAU_RESUME,
        "original_filename": "document_001.pdf",
    }
    confidence, reason = score_candidate_resume(ARBUZOV_CANDIDATE, resume)
    assert classify_match(confidence, 0) == "matched"
    assert confidence >= 90
    assert "сходство имени файла" not in reason or "document_001" not in reason


def test_clear_name_conflict_blocks_skill_only_review_match():
    candidate = {
        "full_name": "Екатерина Федорова",
        "vacancy": "BA",
        "row_data": {
            "Фамилия, имя": "Екатерина Федорова",
            "вакансия": "BA",
            "оценка рекрутера": "embedded, embedded вакансии, анализ требований",
        },
    }
    resume = {
        "original_filename": "Стрижевич Дарья.pdf",
        "profile": {
            "full_name_original": "Стрижевич Дарья",
            "email": "",
            "phone": "",
            "current_position": "BA Embedded",
            "current_company": "",
            "key_skills": ["embedded"],
        },
    }

    confidence, reason = score_candidate_resume(candidate, resume)

    assert confidence == 0
    assert classify_match(confidence, 0) == "unmatched"
    assert "ФИО не совпадает" in reason


def test_exact_contact_does_not_override_name_conflict():
    candidate = {
        "full_name": "Екатерина Федорова",
        "vacancy": "BA",
        "row_data": {
            "Фамилия, имя": "Екатерина Федорова",
            "Email": "candidate@example.com",
            "вакансия": "BA",
        },
    }
    resume = {
        "original_filename": "Стрижевич Дарья.pdf",
        "profile": {
            "full_name_original": "Стрижевич Дарья",
            "email": "candidate@example.com",
            "phone": "",
            "current_position": "BA",
            "current_company": "",
            "key_skills": [],
        },
    }

    confidence, reason = score_candidate_resume(candidate, resume)

    assert confidence == 0
    assert "ФИО не совпадает" in reason


def test_score_uses_filename_when_full_name_original_is_empty():
    candidate = {
        "full_name": "Иванов Иван",
        "vacancy": "BA",
        "row_data": {"ФИО": "Иванов Иван"},
    }
    resume = {
        "original_filename": "Иванов_Иван.pdf",
        "profile": {"full_name_original": "", "email": "", "phone": ""},
    }

    confidence, reason = score_candidate_resume(candidate, resume)

    assert confidence >= 90
    assert classify_match(confidence, 0) == "matched"
    assert "имя файла" in reason


def test_exact_email_forces_match_when_no_name_conflict():
    candidate = {
        "full_name": "Иванов Иван",
        "vacancy": "BA",
        "row_data": {"Email": "candidate@example.com"},
    }
    resume = {
        "original_filename": "resume.pdf",
        "profile": {"full_name_original": "", "email": "candidate@example.com", "phone": ""},
    }

    confidence, reason = score_candidate_resume(candidate, resume)

    assert confidence == 100
    assert classify_match(confidence, 99) == "matched"
    assert "email" in reason


def test_exact_phone_forces_match_when_no_name_conflict():
    candidate = {
        "full_name": "Иванов Иван",
        "vacancy": "BA",
        "row_data": {"Телефон": "+7 (999) 111-22-33"},
    }
    resume = {
        "original_filename": "resume.pdf",
        "profile": {"full_name_original": "", "email": "", "phone": "8 999 111 22 33"},
    }

    confidence, reason = score_candidate_resume(candidate, resume)

    assert confidence == 100
    assert classify_match(confidence, 99) == "matched"
    assert "телефона" in reason


def test_same_name_in_transliteration_matches_without_other_signals():
    candidate = {
        "full_name": "Стрижевич Дарья",
        "vacancy": "BA",
        "row_data": {"Фамилия, имя": "Стрижевич Дарья"},
    }
    resume = {
        "original_filename": "random.pdf",
        "profile": {
            "full_name_original": "Darya Strizhevich",
            "email": "",
            "phone": "",
            "current_position": "Other role",
            "current_company": "",
            "key_skills": [],
        },
    }

    confidence, reason = score_candidate_resume(candidate, resume)

    assert confidence >= 90
    assert "ФИО/транслитерация" in reason


def test_run_matching_stays_local_even_when_ai_is_enabled(isolated_project_files, monkeypatch):
    monkeypatch.setattr(matching, "MATCHED_RESUME_DIR", config.MATCHED_RESUME_DIR)
    database.init_db()
    settings.save_settings(
        enabled=True,
        provider="gemini",
        api_key="test-key",
        model="gemini-test",
        llm_fallback_for_unmatched=True,
        llm_fallback_max_candidates=200,
    )
    registry_id = database.insert_registry("registry.xlsx", config.REGISTRY_UPLOAD_DIR / "registry.xlsx")
    database.insert_candidate(
        registry_id=registry_id,
        excel_row_number=2,
        candidate_id="REG-2",
        row_data={"ФИО": "Екатерина Федорова"},
        full_name="Екатерина Федорова",
        vacancy="BA",
        status="",
        recruiter="",
        quality_warnings=[],
    )
    database.insert_resume(
        original_filename="Strizhevich_Darya.pdf",
        file_path=config.RESUME_UPLOAD_DIR / "Strizhevich_Darya.pdf",
        file_hash="resume-hash",
        extracted_text="Darya Strizhevich BA embedded",
        profile={"full_name_original": "Darya Strizhevich"},
    )

    def fail_if_network_is_used(*args, **kwargs):
        raise AssertionError("matching must not call AI/network")

    monkeypatch.setattr("app.ai_extraction.urllib.request.urlopen", fail_if_network_is_used)

    results = run_matching()

    assert results[0]["status"] == "unmatched"
    assert results[0]["resume_db_id"] is None


def test_review_creates_renamed_copy(isolated_project_files, monkeypatch):
    monkeypatch.setattr(matching, "MATCHED_RESUME_DIR", config.MATCHED_RESUME_DIR)
    database.init_db()
    settings.save_settings(
        enabled=False,
        provider="gemini",
        api_key="",
        match_threshold_auto=101,
        match_threshold_review=70,
    )
    source = config.RESUME_UPLOAD_DIR / "Ivanov_Ivan.pdf"
    source.write_text("Ivanov Ivan", encoding="utf-8")
    registry_id = database.insert_registry("registry.xlsx", config.REGISTRY_UPLOAD_DIR / "registry.xlsx")
    database.insert_candidate(
        registry_id=registry_id,
        excel_row_number=2,
        candidate_id="REG-2",
        row_data={"ФИО": "Иванов Иван"},
        full_name="Иванов Иван",
        vacancy="BA",
        status="",
        recruiter="",
        quality_warnings=[],
    )
    database.insert_resume(
        original_filename="Ivanov_Ivan.pdf",
        file_path=source,
        file_hash="resume-hash-1",
        extracted_text="Ivanov Ivan",
        profile={"full_name_original": "Ivanov Ivan"},
    )
    database.insert_resume(
        original_filename="Ivan_Ivanov.pdf",
        file_path=source,
        file_hash="resume-hash-2",
        extracted_text="Ivan Ivanov",
        profile={"full_name_original": "Ivan Ivanov"},
    )

    results = run_matching()

    assert results[0]["status"] == "review"
    assert "__REVIEW__" in results[0]["new_filename"]
    assert (config.MATCHED_RESUME_DIR / results[0]["new_filename"]).exists()


def test_run_matching_continues_when_copy_fails(isolated_project_files, monkeypatch):
    monkeypatch.setattr(matching, "MATCHED_RESUME_DIR", config.MATCHED_RESUME_DIR)
    database.init_db()
    source = config.RESUME_UPLOAD_DIR / "Ivanov_Ivan.pdf"
    source.write_text("Ivanov Ivan", encoding="utf-8")
    registry_id = database.insert_registry("registry.xlsx", config.REGISTRY_UPLOAD_DIR / "registry.xlsx")
    for index, full_name in enumerate(["Иванов Иван", "Петров Петр"], start=2):
        database.insert_candidate(
            registry_id=registry_id,
            excel_row_number=index,
            candidate_id=f"REG-{index}",
            row_data={"ФИО": full_name},
            full_name=full_name,
            vacancy="BA",
            status="",
            recruiter="",
            quality_warnings=[],
        )
        database.insert_resume(
            original_filename=f"{full_name.replace(' ', '_')}.pdf",
            file_path=source,
            file_hash=f"resume-hash-{index}",
            extracted_text=full_name,
            profile={"full_name_original": full_name},
        )

    calls = {"count": 0}
    original_copy = matching.copy_matched_resume

    def flaky_copy(candidate, resume, status="matched"):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("copy failed")
        return original_copy(candidate, resume, status=status)

    monkeypatch.setattr(matching, "copy_matched_resume", flaky_copy)

    results = run_matching()

    assert len(results) == 2
    assert "ошибка копирования" in results[0]["reason"]
    assert results[1]["new_filename"]
