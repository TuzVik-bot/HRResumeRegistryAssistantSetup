import json
import re
import shutil
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from app import database
from app.config import MATCHED_RESUME_DIR
from app.settings import load_settings
from app.text_utils import name_variants, normalize_phone, normalize_text, safe_filename


MIN_NAME_REVIEW_SCORE = 70


def score_candidate_resume(candidate: dict[str, Any], resume: dict[str, Any]) -> tuple[float, str]:
    profile = resume.get("profile", {})
    candidate_name = candidate.get("full_name", "")
    profile_name = str(profile.get("full_name_original", ""))
    filename_name = _resume_filename_name(resume)
    resume_name, resume_name_source = _resume_name_for_matching(resume)
    if not _has_two_name_parts(candidate_name):
        return 0.0, "ФИО в реестре не заполнено полностью"
    contacts_match = _contacts_match(candidate, resume)
    if not _has_two_name_parts(resume_name):
        if contacts_match:
            return 100.0, f"точное совпадение {contacts_match}; ФИО в резюме не распознано"
        return 0.0, f"ФИО в резюме не распознано полностью: '{profile_name or filename_name}'"
    name_score = _name_score_for_records(candidate, resume)
    if name_score < MIN_NAME_REVIEW_SCORE:
        return 0.0, f"ФИО не совпадает: реестр '{candidate_name}', резюме '{resume_name}'"
    if contacts_match:
        return 100.0, f"точное совпадение {contacts_match}; ФИО не конфликтует ({name_score:.0f}/100)"
    source_label = "имя файла" if resume_name_source == "filename" else "резюме"
    return min(name_score, 100), f"ФИО/транслитерация ({source_label}): совпадение {name_score:.0f}/100"


def run_matching() -> list[dict[str, Any]]:
    MATCHED_RESUME_DIR.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    thresh_auto = int(settings.get("MATCH_THRESHOLD_AUTO", "90"))
    thresh_review = int(settings.get("MATCH_THRESHOLD_REVIEW", "70"))
    gap_min = int(settings.get("MATCH_GAP_MIN", "10"))

    candidates = [_candidate_from_row(row) for row in database.fetch_all("candidates")]
    resumes = [_resume_from_row(row) for row in database.fetch_all("resumes")]
    results = []
    for candidate in candidates:
        scored = []
        for resume in resumes:
            score, reason = score_candidate_resume(candidate, resume)
            scored.append((score, reason, resume))
        scored.sort(key=lambda item: item[0], reverse=True)
        best = scored[0] if scored else (0.0, "резюме не загружены", None)
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        status = classify_match(best[0], second_score, thresh_auto, thresh_review, gap_min)

        resume = best[2] if best[2] and status != "unmatched" else None
        output_path = None
        new_filename = None
        copy_error = None
        if resume and status in {"matched", "review"}:
            try:
                new_filename, output_path = copy_matched_resume(candidate, resume, status=status)
            except OSError as exc:
                copy_error = str(exc)
                database.insert_event(
                    "error",
                    "matching",
                    "resume_copy_error",
                    "Ошибка копирования сопоставленного резюме",
                    {
                        "candidate_id": candidate["candidate_id"],
                        "resume_filename": resume.get("original_filename", ""),
                        "detail": copy_error,
                    },
                )
        reason = f"{best[1]}; второй лучший score {second_score:.0f}"
        if copy_error:
            reason = f"{reason}; ошибка копирования: {copy_error}"
        match = {
            "candidate_db_id": candidate["db_id"],
            "resume_db_id": resume["db_id"] if resume else None,
            "score": round(best[0], 2),
            "second_score": round(second_score, 2),
            "status": status,
            "reason": reason,
            "new_filename": new_filename,
            "output_path": str(output_path) if output_path else None,
            "needs_manual_review": status != "matched",
        }
        results.append(match)
    database.upsert_matches_bulk(results)
    return results


def classify_match(
    score: float,
    second_score: float,
    threshold_auto: int = 90,
    threshold_review: int = 70,
    gap_min: int = 10,
) -> str:
    gap = score - second_score
    if score >= threshold_auto and (gap >= gap_min or score >= 95):
        return "matched"
    if score >= threshold_review:
        return "review"
    return "unmatched"


def copy_matched_resume(candidate: dict[str, Any], resume: dict[str, Any], status: str = "matched") -> tuple[str, Path]:
    source = Path(resume["file_path"])
    candidate_id = safe_filename(candidate.get("candidate_id") or "candidate", max_length=60)
    marker = "REVIEW" if status == "review" else "MATCHED"
    suffix = source.suffix.lower()
    reserved_length = len(candidate_id) + len(marker) + len(suffix) + 6
    remaining = max(40, 180 - reserved_length)
    full_name_limit = max(20, remaining // 2)
    vacancy_limit = max(20, remaining - full_name_limit)
    vacancy = safe_filename(candidate.get("vacancy") or "Vacancy", max_length=vacancy_limit)
    full_name = safe_filename(candidate.get("full_name") or "No_Name", max_length=full_name_limit)
    new_filename = f"{candidate_id}__{marker}__{full_name}__{vacancy}{suffix}"
    target = MATCHED_RESUME_DIR / new_filename
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(source, target)
    return new_filename, target


def _candidate_from_row(row: Any) -> dict[str, Any]:
    return {
        "db_id": row["id"],
        "candidate_id": row["candidate_id"],
        "full_name": row["full_name"] or "",
        "vacancy": row["vacancy"] or "",
        "status": row["status"] or "",
        "row_data": json.loads(row["row_data_json"]),
        "name_variants": name_variants(row["full_name"] or ""),
        "name_parts_count": len(_name_tokens(row["full_name"] or "")),
    }


def _resume_from_row(row: Any) -> dict[str, Any]:
    profile = json.loads(row["profile_json"])
    full_name = str(profile.get("full_name_original", ""))
    match_name = full_name or _filename_to_name(row["original_filename"])
    return {
        "db_id": row["id"],
        "original_filename": row["original_filename"],
        "file_path": row["file_path"],
        "file_hash": row["file_hash"] or "",
        "extracted_text": row["extracted_text"] or "",
        "profile": profile,
        "name_variants": name_variants(match_name),
        "name_parts_count": len(_name_tokens(match_name)),
    }


def _name_score(candidate_name: str, resume_name: str) -> float:
    candidate_variants = name_variants(candidate_name)
    resume_variants = name_variants(resume_name)
    return _name_score_from_variants(candidate_variants, resume_variants)


def _name_score_for_records(candidate: dict[str, Any], resume: dict[str, Any]) -> float:
    candidate_variants = candidate.get("name_variants") or name_variants(candidate.get("full_name", ""))
    resume_variants = resume.get("name_variants") or name_variants(_resume_name_for_matching(resume)[0])
    return _name_score_from_variants(candidate_variants, resume_variants)


def _name_score_from_variants(candidate_variants: set[str], resume_variants: set[str]) -> float:
    if not candidate_variants or not resume_variants:
        return 0
    return max(fuzz.token_sort_ratio(a, b) for a in candidate_variants for b in resume_variants)


def _has_two_name_parts(value: str | None) -> bool:
    return len(_name_tokens(value)) >= 2


def _name_tokens(value: str | None) -> list[str]:
    normalized = normalize_text(value)
    return [token for token in normalized.split() if token and not token.isdigit()]


def _resume_name_for_matching(resume: dict[str, Any]) -> tuple[str, str]:
    profile_name = str(resume.get("profile", {}).get("full_name_original", "") or "")
    if _has_two_name_parts(profile_name):
        return profile_name, "profile"
    filename_name = _resume_filename_name(resume)
    if _has_two_name_parts(filename_name):
        return filename_name, "filename"
    return profile_name or filename_name, "profile" if profile_name else "filename"


def _resume_filename_name(resume: dict[str, Any]) -> str:
    return _filename_to_name(str(resume.get("original_filename", "")))


def _filename_to_name(filename: str | None) -> str:
    stem = Path(str(filename or "")).stem
    return re.sub(r"[_\-.]+", " ", stem).strip()


def _contacts_match(candidate: dict[str, Any], resume: dict[str, Any]) -> str | None:
    candidate_emails, candidate_phones = _candidate_contacts(candidate)
    profile = resume.get("profile", {})
    resume_email = normalize_text(str(profile.get("email", "")))
    resume_phone = normalize_phone(str(profile.get("phone", "")))
    if resume_email and resume_email in candidate_emails:
        return "email"
    if resume_phone and len(resume_phone) >= 10 and resume_phone in candidate_phones:
        return "телефона"
    return None


def _candidate_contacts(candidate: dict[str, Any]) -> tuple[set[str], set[str]]:
    values = [str(value) for value in (candidate.get("row_data") or {}).values() if value is not None]
    emails: set[str] = set()
    phones: set[str] = set()
    for value in values:
        emails.update(normalize_text(match) for match in re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", value))
        phone = normalize_phone(value)
        if len(phone) >= 10:
            phones.add(phone)
    return emails, phones
