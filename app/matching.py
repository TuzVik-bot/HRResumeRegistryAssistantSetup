import json
import shutil
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from app import database
from app.config import MATCHED_RESUME_DIR
from app.settings import load_settings
from app.text_utils import name_variants, normalize_text, safe_filename


MIN_NAME_REVIEW_SCORE = 70


def score_candidate_resume(candidate: dict[str, Any], resume: dict[str, Any]) -> tuple[float, str]:
    profile = resume.get("profile", {})
    candidate_name = candidate.get("full_name", "")
    resume_name = str(profile.get("full_name_original", ""))
    if not _has_two_name_parts(candidate_name):
        return 0.0, "ФИО в реестре не заполнено полностью"
    if not _has_two_name_parts(resume_name):
        return 0.0, f"ФИО в резюме не распознано полностью: '{resume_name}'"
    name_score = _name_score_for_records(candidate, resume)
    if name_score < MIN_NAME_REVIEW_SCORE:
        return 0.0, f"ФИО не совпадает: реестр '{candidate_name}', резюме '{resume_name}'"
    return min(name_score, 100), f"ФИО/транслитерация: совпадение {name_score:.0f}/100"


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
        if resume and status == "matched":
            new_filename, output_path = copy_matched_resume(candidate, resume)
        match = {
            "candidate_db_id": candidate["db_id"],
            "resume_db_id": resume["db_id"] if resume else None,
            "score": round(best[0], 2),
            "second_score": round(second_score, 2),
            "status": status,
            "reason": f"{best[1]}; второй лучший score {second_score:.0f}",
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
    if score >= threshold_auto and gap >= gap_min:
        return "matched"
    if score >= threshold_review:
        return "review"
    return "unmatched"


def copy_matched_resume(candidate: dict[str, Any], resume: dict[str, Any]) -> tuple[str, Path]:
    source = Path(resume["file_path"])
    vacancy = safe_filename(candidate.get("vacancy") or "Vacancy")
    full_name = safe_filename(candidate.get("full_name") or "No_Name")
    new_filename = f"{candidate['candidate_id']}__{full_name}__{vacancy}{source.suffix.lower()}"
    target = MATCHED_RESUME_DIR / new_filename
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
    return {
        "db_id": row["id"],
        "original_filename": row["original_filename"],
        "file_path": row["file_path"],
        "file_hash": row["file_hash"] or "",
        "extracted_text": row["extracted_text"] or "",
        "profile": profile,
        "name_variants": name_variants(full_name),
        "name_parts_count": len(_name_tokens(full_name)),
    }


def _name_score(candidate_name: str, resume_name: str) -> float:
    candidate_variants = name_variants(candidate_name)
    resume_variants = name_variants(resume_name)
    return _name_score_from_variants(candidate_variants, resume_variants)


def _name_score_for_records(candidate: dict[str, Any], resume: dict[str, Any]) -> float:
    candidate_variants = candidate.get("name_variants") or name_variants(candidate.get("full_name", ""))
    resume_variants = resume.get("name_variants") or name_variants(str(resume.get("profile", {}).get("full_name_original", "")))
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
