import json

from starlette.requests import Request

from app import config, database, main
from app.diagnostics import log_event, resume_error_report


def test_error_event_is_saved_and_masked_in_diagnostics(isolated_project_files, monkeypatch):
    monkeypatch.setattr(main, "EXPORT_DIR", config.EXPORT_DIR)
    monkeypatch.setattr(main, "REGISTRY_UPLOAD_DIR", config.REGISTRY_UPLOAD_DIR)
    monkeypatch.setattr(main, "RESUME_UPLOAD_DIR", config.RESUME_UPLOAD_DIR)

    database.init_db()
    log_event(
        "error",
        "upload",
        "resume_processing_error",
        "Ошибка обработки резюме",
        {
            "filename": "candidate.doc",
            "email": "person@example.com",
            "phone": "+375291112233",
            "key_status": "ключ задан",
        },
    )

    rows = database.fetch_recent_events(limit=10)
    assert len(rows) >= 1
    assert "person@example.com" not in rows[0]["context_json"]
    assert "[скрыто]" in rows[0]["context_json"]

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/diagnostics",
            "query_string": b"filter=errors",
            "headers": [],
            "app": main.app,
        }
    )
    response = main.diagnostics_page(request)

    context_payload = json.dumps(response.context, ensure_ascii=False, default=str)
    assert response.status_code == 200
    assert response.context["active_filter"] == "errors"
    assert "resume_processing_error" in context_payload
    assert "person@example.com" not in context_payload
    assert "ключ задан" in context_payload


def test_diagnostics_context_lists_resumes_without_registry_matches(isolated_project_files, monkeypatch):
    monkeypatch.setattr(main, "EXPORT_DIR", config.EXPORT_DIR)
    monkeypatch.setattr(main, "REGISTRY_UPLOAD_DIR", config.REGISTRY_UPLOAD_DIR)
    monkeypatch.setattr(main, "RESUME_UPLOAD_DIR", config.RESUME_UPLOAD_DIR)

    database.init_db()
    registry_id = database.insert_registry("registry.xlsx", config.REGISTRY_UPLOAD_DIR / "registry.xlsx")
    candidate_id = database.insert_candidate(
        registry_id=registry_id,
        excel_row_number=2,
        candidate_id="REG-2",
        row_data={"ФИО": "Иван Иванов"},
        full_name="Иван Иванов",
        vacancy="",
        status="",
        recruiter="",
        quality_warnings=[],
    )
    matched_resume_id = database.insert_resume(
        original_filename="Ivan_Ivanov.pdf",
        file_path=config.RESUME_UPLOAD_DIR / "Ivan_Ivanov.pdf",
        file_hash="matched",
        extracted_text="Ivan Ivanov",
        profile={"full_name_original": "Ivan Ivanov"},
    )
    unmatched_resume_id = database.insert_resume(
        original_filename="No_Registry_Row.pdf",
        file_path=config.RESUME_UPLOAD_DIR / "No_Registry_Row.pdf",
        file_hash="unmatched",
        extracted_text="No Registry Row",
        profile={"full_name_original": "No Registry Row"},
    )
    database.upsert_match(
        {
            "candidate_db_id": candidate_id,
            "resume_db_id": matched_resume_id,
            "score": 100,
            "second_score": 0,
            "status": "matched",
            "reason": "ФИО/транслитерация: совпадение 100/100",
            "needs_manual_review": False,
        }
    )

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/diagnostics",
            "query_string": b"",
            "headers": [],
            "app": main.app,
        }
    )
    response = main.diagnostics_page(request)

    filenames = [row["original_filename"] for row in response.context["unmatched_resumes"]]
    ids = [row["id"] for row in response.context["unmatched_resumes"]]
    assert response.status_code == 200
    assert filenames == ["No_Registry_Row.pdf"]
    assert ids == [unmatched_resume_id]


def test_resume_error_report_includes_processing_and_batch_failures(isolated_project_files):
    database.init_db()
    log_event(
        "error",
        "upload",
        "resume_processing_error",
        "Ошибка обработки резюме",
        {"filename": "candidate.doc", "format": ".doc", "detail": "LibreOffice не найден"},
    )
    log_event(
        "error",
        "upload",
        "resume_batch_failed",
        "Все резюме завершились с ошибкой обработки",
        {"files_total": 2, "failed": 2, "skipped": 0},
    )
    log_event("info", "upload", "registry_imported", "Реестр импортирован", {"filename": "registry.xlsx"})

    rows = resume_error_report()

    actions = [row["action"] for row in rows]
    assert actions == ["resume_batch_failed", "resume_processing_error"]
    assert rows[1]["filename"] == "candidate.doc"
    assert rows[0]["failed"] == 2


def test_diagnostics_csv_exports_resume_errors(isolated_project_files):
    database.init_db()
    log_event(
        "error",
        "upload",
        "resume_processing_error",
        "Ошибка обработки резюме",
        {"filename": "candidate.doc", "format": ".doc", "detail": "LibreOffice не найден"},
    )
    log_event("info", "upload", "registry_imported", "Реестр импортирован", {"filename": "registry.xlsx"})

    response = main.diagnostics_resume_errors_csv()
    body = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "text/csv" in response.media_type
    assert "candidate.doc" in body
    assert "resume_processing_error" in body
    assert "registry_imported" not in body


def test_matching_results_context_contains_resume_error_summary(isolated_project_files):
    database.init_db()
    log_event(
        "error",
        "upload",
        "resume_processing_error",
        "Ошибка обработки резюме",
        {"filename": "candidate.doc", "format": ".doc", "detail": "LibreOffice не найден"},
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/matching-results",
            "query_string": b"",
            "headers": [],
            "app": main.app,
        }
    )

    response = main.matching_results(request)

    assert response.context["resume_error_summary"]["count"] == 1


def test_matching_progress_endpoint_defaults_to_idle():
    main.MATCHING_PROGRESS.update({"state": "idle", "current": 0, "total": 0, "message": ""})

    payload = main.matching_progress()

    assert payload["state"] == "idle"
    assert payload["percent"] == 0


def test_run_matching_route_updates_progress_on_success(monkeypatch):
    monkeypatch.setattr(main, "run_matching", lambda: [{"status": "matched"}])

    response = main.run_matching_route()

    assert response.status_code == 303
    assert main.MATCHING_PROGRESS["state"] == "completed"


def test_run_matching_route_updates_progress_on_failure(monkeypatch):
    def fail():
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "run_matching", fail)

    try:
        main.run_matching_route()
    except RuntimeError:
        pass

    assert main.MATCHING_PROGRESS["state"] == "failed"


def test_missing_libreoffice_doc_can_use_filename_only_profile():
    assert main._can_use_filename_only_doc_profile(".doc", RuntimeError("Для файлов .doc требуется установленный LibreOffice"))
    assert not main._can_use_filename_only_doc_profile(".docx", RuntimeError("Для файлов .doc требуется установленный LibreOffice"))
