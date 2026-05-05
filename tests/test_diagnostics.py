import json

from starlette.requests import Request

from app import config, database, main
from app.diagnostics import log_event


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
