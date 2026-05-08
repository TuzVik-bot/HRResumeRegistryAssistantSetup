from dataclasses import dataclass
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import database
from app.ai_extraction import enrich_resume_with_ai_if_needed, should_use_ai_for_local_profile
from app.config import BASE_DIR, EXPORT_DIR, REGISTRY_UPLOAD_DIR, RESUME_UPLOAD_DIR, ensure_directories
from app.diagnostics import EVENT_FILTERS, log_event, recent_events
from app.exporter import export_enriched_excel
from app.file_utils import file_sha256
from app.i18n import reason_label, status_label, warning_label
from app.matching import copy_matched_resume, run_matching
from app.registry import import_registry
from app.ai_extraction import extract_text_via_gemini_vision
from app.resume_parser import empty_resume_profile, extract_text, needs_ocr, parse_resume_profile
from app.settings import load_settings, save_settings


app = FastAPI(title="HR-ассистент реестра резюме")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["status_label"] = status_label
templates.env.filters["reason_label"] = reason_label
templates.env.filters["warning_label"] = warning_label
templates.env.filters["from_json"] = lambda value: json.loads(value or "[]")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def startup() -> None:
    ensure_directories()
    database.init_db()
    log_event("info", "app", "startup", "Приложение запущено", {"base_dir": str(BASE_DIR)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log_event(
        "error",
        _category_from_path(request.url.path),
        "unhandled_exception",
        str(exc),
        {
            "path": request.url.path,
            "method": request.method,
            "exception_type": exc.__class__.__name__,
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка приложения. Откройте раздел «Диагностика» для деталей."},
    )


@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "registries_count": len(database.fetch_all("registries")),
            "candidates_count": len(database.fetch_all("candidates")),
            "resumes_count": len(database.fetch_all("resumes")),
            "matches_count": len(database.fetch_all("matches")),
        },
    )


@app.get("/upload-registry")
def upload_registry_page(request: Request):
    return templates.TemplateResponse("upload_registry.html", {"request": request})


@app.post("/upload-registry")
async def upload_registry(file: UploadFile = File(...)):
    try:
        if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
            raise HTTPException(status_code=400, detail="Загрузите Excel-файл .xlsx/.xlsm/.xls")
        stored = _store_upload_once(file, REGISTRY_UPLOAD_DIR)
        result = import_registry(stored.path, file.filename, file_hash=stored.file_hash)
        if result["duplicate"]:
            log_event(
                "info",
                "upload",
                "registry_duplicate_skipped",
                "Повторный Excel-реестр пропущен",
                {"filename": file.filename, "file_hash": stored.file_hash},
            )
        else:
            log_event(
                "info",
                "upload",
                "registry_imported",
                "Реестр импортирован",
                {
                    "filename": file.filename,
                    "file_hash": stored.file_hash,
                    "rows": result["rows"],
                    "source_schema": result["source_schema"],
                    "reused_existing_file": stored.reused_existing,
                },
            )
        return RedirectResponse("/", status_code=303)
    except sqlite3.OperationalError as exc:
        log_event("error", "upload", "registry_db_error", "Ошибка SQLite при импорте реестра", {"detail": str(exc)})
        return JSONResponse(
            status_code=503,
            content={"detail": f"База данных занята. Повторите загрузку через несколько секунд. Детали: {exc}"},
        )
    except ValueError as exc:
        log_event("error", "upload", "registry_validation_error", "Ошибка Excel-реестра", {"filename": file.filename, "detail": str(exc)})
        return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/upload-resumes")
def upload_resumes_page(request: Request):
    return templates.TemplateResponse("upload_resumes.html", {"request": request})


@app.post("/upload-resumes")
async def upload_resumes(files: list[UploadFile] = File(...)):
    try:
        allowed = {".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt"}
        uploaded = 0
        failed = 0
        skipped = 0
        for file in files:
            if not file.filename:
                continue
            suffix = Path(file.filename).suffix.lower()
            if suffix not in allowed:
                skipped += 1
                log_event(
                    "warn",
                    "upload",
                    "resume_skipped_extension",
                    "Файл пропущен — неподдерживаемое расширение",
                    {"filename": file.filename, "suffix": suffix},
                )
                continue
            stored = _store_upload_once(file, RESUME_UPLOAD_DIR)
            try:
                text = extract_text(stored.path)
                text = _ocr_fallback_if_needed(text, stored.path, stored.file_hash, suffix)
                profile = parse_resume_profile(text, file.filename)
                resume_id = database.insert_resume(file.filename, stored.path, stored.file_hash, text, profile)
                uploaded += 1
                log_event(
                    "info",
                    "upload",
                    "resume_uploaded",
                    "Резюме обработано локально",
                    {
                        "filename": file.filename,
                        "file_hash": stored.file_hash,
                        "format": suffix,
                        "reused_existing_file": stored.reused_existing,
                        "text_length": len(text),
                    },
                )
                if should_use_ai_for_local_profile(profile):
                    enrich_resume_with_ai_if_needed(
                        resume_id=resume_id,
                        file_hash=stored.file_hash,
                        resume_text=text,
                        local_profile=profile,
                        reason="локальное извлечение не нашло ключевые поля",
                    )
            except Exception as exc:
                database.insert_resume(
                    original_filename=file.filename,
                    file_path=stored.path,
                    file_hash=stored.file_hash,
                    extracted_text="",
                    profile=empty_resume_profile(file.filename),
                    processing_error=str(exc),
                )
                failed += 1
                log_event(
                    "error",
                    "upload",
                    "resume_processing_error",
                    "Ошибка обработки резюме",
                    {"filename": file.filename, "format": suffix, "detail": str(exc)},
                )
        if uploaded == 0:
            if failed:
                log_event(
                    "error",
                    "upload",
                    "resume_batch_failed",
                    "Все резюме завершились с ошибкой обработки",
                    {"files_total": len(files), "failed": failed, "skipped": skipped},
                )
                return RedirectResponse("/matching-results", status_code=303)
            return JSONResponse(status_code=400, content={
                "detail": f"Не найдено файлов PDF, DOC, DOCX, RTF, ODT или TXT для загрузки. Пропущено файлов с неподдерживаемым расширением: {skipped}."
            })
        log_event(
            "info",
            "upload",
            "resume_batch_completed",
            "Пакет резюме обработан",
            {"uploaded": uploaded, "failed": failed, "skipped": skipped, "files_total": len(files)},
        )
        return RedirectResponse("/matching-results", status_code=303)
    except sqlite3.OperationalError as exc:
        log_event("error", "upload", "resume_db_error", "Ошибка SQLite при загрузке резюме", {"detail": str(exc)})
        return JSONResponse(
            status_code=503,
            content={"detail": f"База данных занята. Повторите загрузку через несколько секунд. Детали: {exc}"},
        )
    except Exception as exc:
        log_event("error", "upload", "resume_upload_error", "Критическая ошибка загрузки резюме", {"detail": str(exc)})
        return JSONResponse(status_code=400, content={"detail": f"Не удалось обработать резюме: {exc}"})


@app.get("/scan-folder")
def scan_folder_page(request: Request):
    return templates.TemplateResponse("upload_resumes.html", {"request": request})


@app.post("/scan-folder")
def scan_folder(folder_path: str = Form(...)):
    folder = Path(folder_path.strip())
    if not folder.exists() or not folder.is_dir():
        return JSONResponse(status_code=400, content={"detail": f"Папка не найдена: {folder_path}"})

    allowed = {".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt"}
    uploaded = 0
    failed = 0
    skipped = 0
    skipped_files: list[str] = []

    for file_path in folder.rglob("*"):
        if not file_path.is_file():
            continue
        suffix = file_path.suffix.lower()
        if suffix not in allowed:
            skipped += 1
            skipped_files.append(file_path.name)
            continue
        stored = _store_disk_file_once(file_path, RESUME_UPLOAD_DIR)
        if stored.reused_existing:
            uploaded += 1
            continue
        try:
            text = extract_text(stored.path)
            text = _ocr_fallback_if_needed(text, stored.path, stored.file_hash, suffix)
            profile = parse_resume_profile(text, file_path.name)
            resume_id = database.insert_resume(file_path.name, stored.path, stored.file_hash, text, profile)
            uploaded += 1
            log_event(
                "info",
                "upload",
                "resume_scanned",
                "Резюме из папки обработано",
                {"filename": file_path.name, "format": suffix, "text_length": len(text)},
            )
            if should_use_ai_for_local_profile(profile):
                enrich_resume_with_ai_if_needed(
                    resume_id=resume_id,
                    file_hash=stored.file_hash,
                    resume_text=text,
                    local_profile=profile,
                    reason="локальное извлечение не нашло ключевые поля",
                )
        except Exception as exc:
            database.insert_resume(
                original_filename=file_path.name,
                file_path=stored.path,
                file_hash=stored.file_hash,
                extracted_text="",
                profile=empty_resume_profile(file_path.name),
                processing_error=str(exc),
            )
            failed += 1
            log_event(
                "error",
                "upload",
                "resume_scan_error",
                "Ошибка обработки файла из папки",
                {"filename": file_path.name, "format": suffix, "detail": str(exc)},
            )

    log_event(
        "info",
        "upload",
        "folder_scan_completed",
        "Сканирование папки завершено",
        {"folder": str(folder), "uploaded": uploaded, "failed": failed, "skipped": skipped},
    )
    return RedirectResponse(
        f"/matching-results?scan_uploaded={uploaded}&scan_failed={failed}&scan_skipped={skipped}",
        status_code=303,
    )


@app.post("/run-matching")
def run_matching_route():
    results = run_matching()
    log_event(
        "info",
        "matching",
        "matching_completed",
        "Сопоставление завершено",
        {
            "rows_total": len(results),
            "matched": sum(1 for item in results if item["status"] == "matched"),
            "review": sum(1 for item in results if item["status"] == "review"),
            "unmatched": sum(1 for item in results if item["status"] == "unmatched"),
        },
    )
    return RedirectResponse("/matching-results", status_code=303)


@app.get("/matching-results")
def matching_results(request: Request):
    return templates.TemplateResponse(
        "matching_results.html",
        {"request": request, "rows": database.fetch_candidates_with_matches()},
    )


@app.get("/manual-review")
def manual_review(request: Request):
    rows = [row for row in database.fetch_candidates_with_matches() if row["needs_manual_review"] or row["match_status"] != "matched"]
    return templates.TemplateResponse(
        "manual_review.html",
        {"request": request, "rows": rows, "resumes": database.fetch_all("resumes")},
    )


@app.post("/manual-review/{candidate_db_id}")
def update_manual_review(
    candidate_db_id: int,
    action: str = Form(...),
    resume_id: str = Form(default=""),
    resume_query: str = Form(default=""),
):
    candidate = database.fetch_candidate(candidate_db_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")

    selected_resume = None if action == "reject" and not resume_id else _resolve_resume_selection(resume_id, resume_query)

    new_filename = None
    output_path = None
    if action == "confirm":
        if not selected_resume:
            raise HTTPException(status_code=400, detail="Выберите резюме для подтверждения совпадения")
        candidate_payload = {
            "candidate_id": candidate["candidate_id"],
            "full_name": candidate["full_name"],
            "vacancy": candidate["vacancy"],
        }
        resume_payload = {
            "file_path": selected_resume["file_path"],
        }
        new_filename, copied_path = copy_matched_resume(candidate_payload, resume_payload)
        output_path = str(copied_path)
        database.set_manual_match(
            candidate_db_id=candidate_db_id,
            resume_db_id=selected_resume["id"],
            status="matched",
            reason="Ручная проверка: совпадение подтверждено пользователем",
            score=100,
            new_filename=new_filename,
            output_path=output_path,
        )
    elif action == "reject":
        database.set_manual_match(
            candidate_db_id=candidate_db_id,
            resume_db_id=selected_resume["id"] if selected_resume else None,
            status="unmatched",
            reason="Ручная проверка: совпадение отклонено пользователем",
            score=0,
        )
    elif action == "review":
        database.set_manual_match(
            candidate_db_id=candidate_db_id,
            resume_db_id=selected_resume["id"] if selected_resume else None,
            status="review",
            reason="Ручная проверка: оставлено на дополнительную проверку",
            score=50,
        )
    else:
        raise HTTPException(status_code=400, detail="Неизвестное действие ручной проверки")
    log_event(
        "info",
        "matching",
        "manual_review_updated",
        "Пользователь обновил результат ручной проверки",
        {"candidate_db_id": candidate_db_id, "action": action, "resume_id": resume_id or None},
    )
    return RedirectResponse("/manual-review", status_code=303)


def _resolve_resume_selection(resume_id: str, resume_query: str):
    if resume_id:
        return database.fetch_resume(int(resume_id))
    query = resume_query.strip().lower()
    if not query:
        return None
    resumes = database.fetch_all("resumes")
    exact_matches = [resume for resume in resumes if resume["original_filename"].lower() == query]
    if exact_matches:
        return exact_matches[0]
    partial_matches = [resume for resume in resumes if query in resume["original_filename"].lower()]
    if len(partial_matches) == 1:
        return partial_matches[0]
    if len(partial_matches) > 1:
        raise HTTPException(status_code=400, detail="Найдено несколько резюме. Уточните название файла.")
    raise HTTPException(status_code=400, detail="Резюме с таким названием не найдено.")


@app.get("/data-quality")
def data_quality(request: Request):
    rows = database.fetch_candidates_with_matches()
    return templates.TemplateResponse("data_quality.html", {"request": request, "rows": rows})


@app.get("/diagnostics")
def diagnostics_page(request: Request):
    filter_name = request.query_params.get("filter", "all")
    if filter_name not in EVENT_FILTERS:
        filter_name = "all"
    rows, counts = recent_events(filter_name=filter_name, limit=1000)
    unmatched_resumes = database.fetch_resumes_without_registry_matches()
    return templates.TemplateResponse(
        "diagnostics.html",
        {
            "request": request,
            "rows": rows,
            "unmatched_resumes": unmatched_resumes,
            "active_filter": filter_name,
            "filters": EVENT_FILTERS,
            "counts": counts,
        },
    )


@app.get("/settings")
def settings_page(request: Request):
    settings = load_settings()
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings,
            "api_key_mask": _mask_secret(settings.get("AI_API_KEY", "")),
        },
    )


@app.post("/settings")
def update_settings(
    enabled: str | None = Form(default=None),
    provider: str = Form(default="gemini"),
    model: str = Form(default="gemini-1.5-flash"),
    api_key: str = Form(default=""),
    match_threshold_auto: int = Form(default=90),
    match_threshold_review: int = Form(default=70),
    match_gap_min: int = Form(default=10),
    ocr_fallback_enabled: str | None = Form(default=None),
    llm_fallback_for_unmatched: str | None = Form(default=None),
    llm_fallback_max_candidates: int = Form(default=50),
):
    current = load_settings()
    final_key = api_key.strip() or current.get("AI_API_KEY", "")
    save_settings(
        enabled=enabled == "on",
        provider=provider,
        model=model,
        api_key=final_key,
        match_threshold_auto=match_threshold_auto,
        match_threshold_review=match_threshold_review,
        match_gap_min=match_gap_min,
        ocr_fallback_enabled=ocr_fallback_enabled == "on",
        llm_fallback_for_unmatched=False,
        llm_fallback_max_candidates=llm_fallback_max_candidates,
    )
    log_event(
        "info",
        "app",
        "settings_updated",
        "Настройки ИИ обновлены",
        {
            "enabled": enabled == "on",
            "provider": provider,
            "model": model,
            "key_status": "ключ задан" if final_key else "не задан",
        },
    )
    return RedirectResponse("/settings", status_code=303)


@app.get("/export")
def export_page(request: Request):
    return templates.TemplateResponse("export.html", {"request": request})


@app.post("/export")
def export_file():
    output_path = export_enriched_excel()
    log_event("info", "export", "export_created", "Сформирован Excel-экспорт", {"filename": output_path.name})
    return RedirectResponse(f"/download/{output_path.name}", status_code=303)


@app.get("/download/{filename}")
def download(filename: str):
    output_path = EXPORT_DIR / filename
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(output_path, filename=filename)


@app.get("/source/registry/{registry_id}")
def source_registry(registry_id: int):
    registry = database.fetch_registry(registry_id)
    if not registry:
        raise HTTPException(status_code=404, detail="Реестр не найден")
    path = Path(registry["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Файл реестра не найден")
    return FileResponse(path, filename=registry["filename"])


@app.get("/source/resume/{resume_id}")
def source_resume(resume_id: int):
    resume = database.fetch_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Резюме не найдено")
    path = Path(resume["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Файл резюме не найден")
    return FileResponse(path, filename=resume["original_filename"])


def _unique_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 1
    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


@dataclass
class StoredUpload:
    path: Path
    file_hash: str
    reused_existing: bool


def _store_upload_once(file: UploadFile, target_dir: Path) -> StoredUpload:
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        incoming_hash = file_sha256(tmp_path)
        for existing in target_dir.iterdir():
            if existing.is_file() and file_sha256(existing) == incoming_hash:
                tmp_path.unlink(missing_ok=True)
                return StoredUpload(path=existing, file_hash=incoming_hash, reused_existing=True)
        target = _unique_path(target_dir / (file.filename or f"upload{suffix}"))
        shutil.move(str(tmp_path), target)
        return StoredUpload(path=target, file_hash=incoming_hash, reused_existing=False)
    finally:
        tmp_path.unlink(missing_ok=True)


def _ocr_fallback_if_needed(text: str, file_path: Path, file_hash: str, suffix: str) -> str:
    """If a PDF returned too little text, try Gemini Vision OCR."""
    if suffix != ".pdf" or not needs_ocr(text):
        return text
    settings = load_settings()
    if settings.get("OCR_FALLBACK_ENABLED", "true").lower() != "true":
        return text
    if settings.get("AI_EXTRACTION_ENABLED", "false").lower() != "true":
        return text
    api_key = settings.get("AI_API_KEY", "").strip()
    if not api_key:
        return text
    model = settings.get("AI_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash"
    try:
        ocr_text = extract_text_via_gemini_vision(file_path, api_key, model)
        if len(ocr_text.strip()) > len(text.strip()):
            log_event(
                "info",
                "upload",
                "ocr_applied",
                "Применён OCR через Gemini Vision для сканированного PDF",
                {"file_hash": file_hash, "ocr_chars": len(ocr_text)},
            )
            return ocr_text
    except Exception as exc:
        log_event(
            "warn",
            "upload",
            "ocr_failed",
            "OCR через Gemini Vision не удался",
            {"file_hash": file_hash, "detail": str(exc)},
        )
    return text


def _store_disk_file_once(file_path: Path, target_dir: Path) -> StoredUpload:
    """Like _store_upload_once but for files already on disk."""
    target_dir.mkdir(parents=True, exist_ok=True)
    incoming_hash = file_sha256(file_path)
    for existing in target_dir.iterdir():
        if existing.is_file() and file_sha256(existing) == incoming_hash:
            return StoredUpload(path=existing, file_hash=incoming_hash, reused_existing=True)
    target = _unique_path(target_dir / file_path.name)
    shutil.copy2(file_path, target)
    return StoredUpload(path=target, file_hash=incoming_hash, reused_existing=False)


def _mask_secret(value: str) -> str:
    if not value:
        return "не задан"
    return "ключ задан"


def _category_from_path(path: str) -> str:
    if path.startswith("/upload-"):
        return "upload"
    if path.startswith("/run-matching") or path.startswith("/matching") or path.startswith("/manual-review"):
        return "matching"
    if path.startswith("/export") or path.startswith("/download"):
        return "export"
    return "app"
