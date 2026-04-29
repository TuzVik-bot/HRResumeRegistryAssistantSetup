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
from app.exporter import export_enriched_excel
from app.file_utils import file_sha256
from app.i18n import reason_label, status_label, warning_label
from app.matching import run_matching
from app.matching import copy_matched_resume
from app.registry import import_registry
from app.resume_parser import extract_text, parse_resume_profile
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


@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
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
        database.reset_working_data()
        target = _store_upload_once(file, REGISTRY_UPLOAD_DIR)
        import_registry(target, file.filename)
        return RedirectResponse("/", status_code=303)
    except sqlite3.OperationalError as exc:
        return JSONResponse(
            status_code=503,
            content={"detail": f"База данных занята. Повторите загрузку через несколько секунд. Детали: {exc}"},
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/upload-resumes")
def upload_resumes_page(request: Request):
    return templates.TemplateResponse("upload_resumes.html", {"request": request})


@app.post("/upload-resumes")
async def upload_resumes(files: list[UploadFile] = File(...)):
    try:
        allowed = {".pdf", ".docx", ".txt"}
        uploaded = 0
        for file in files:
            if not file.filename:
                continue
            suffix = Path(file.filename).suffix.lower()
            if suffix not in allowed:
                continue
            target = _store_upload_once(file, RESUME_UPLOAD_DIR)
            file_hash = file_sha256(target)
            text = extract_text(target)
            profile = parse_resume_profile(text, file.filename)
            resume_id = database.insert_resume(file.filename, target, file_hash, text, profile)
            uploaded += 1
            if should_use_ai_for_local_profile(profile):
                enrich_resume_with_ai_if_needed(
                    resume_id=resume_id,
                    file_hash=file_hash,
                    resume_text=text,
                    local_profile=profile,
                    reason="локальное извлечение не нашло ключевые поля",
                )
        if uploaded == 0:
            return JSONResponse(status_code=400, content={"detail": "Не найдено файлов PDF, DOCX или TXT для загрузки."})
        return RedirectResponse("/matching-results", status_code=303)
    except sqlite3.OperationalError as exc:
        return JSONResponse(
            status_code=503,
            content={"detail": f"База данных занята. Повторите загрузку через несколько секунд. Детали: {exc}"},
        )
    except Exception as exc:
        return JSONResponse(status_code=400, content={"detail": f"Не удалось обработать резюме: {exc}"})


@app.post("/run-matching")
def run_matching_route():
    run_matching()
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
):
    current = load_settings()
    final_key = api_key.strip() or current.get("AI_API_KEY", "")
    save_settings(
        enabled=enabled == "on",
        provider=provider,
        model=model,
        api_key=final_key,
    )
    return RedirectResponse("/settings", status_code=303)


@app.get("/export")
def export_page(request: Request):
    return templates.TemplateResponse("export.html", {"request": request})


@app.post("/export")
def export_file():
    output_path = export_enriched_excel()
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


def _store_upload_once(file: UploadFile, target_dir: Path) -> Path:
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
                return existing
        target = _unique_path(target_dir / (file.filename or f"upload{suffix}"))
        shutil.move(str(tmp_path), target)
        return target
    finally:
        tmp_path.unlink(missing_ok=True)


def _mask_secret(value: str) -> str:
    if not value:
        return "не задан"
    return "ключ задан"
