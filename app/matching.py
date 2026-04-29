import json
import shutil
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from app import database
from app.ai_extraction import enrich_resume_with_ai_if_needed
from app.config import MATCHED_RESUME_DIR
from app.registry import COLUMN_ALIASES, map_columns
from app.skills import extract_skills, flatten_skills
from app.text_utils import name_variants, normalize_phone, normalize_text, safe_filename


def score_candidate_resume(candidate: dict[str, Any], resume: dict[str, Any]) -> tuple[float, str]:
    row_data = candidate.get("row_data", {})
    columns = list(row_data.keys())
    profile = resume.get("profile", {})
    reasons: list[str] = []
    score = 0.0

    email_candidate = _find_email(row_data)
    if email_candidate and email_candidate.lower() == str(profile.get("email", "")).lower():
        score += 30
        reasons.append("точное совпадение email (+30)")

    phone_candidate = normalize_phone(_find_phone(row_data))
    if phone_candidate and phone_candidate == profile.get("phone"):
        score += 25
        reasons.append("точное совпадение телефона (+25)")

    name_score = _name_score(candidate.get("full_name", ""), str(profile.get("full_name_original", "")))
    score += name_score * 0.40
    reasons.append(f"transliteration: совпадение ФИО {name_score:.0f}/100 (+{name_score * 0.40:.0f})")

    vacancy = candidate.get("vacancy") or ""
    position = str(profile.get("current_position", ""))
    vacancy_score = _vacancy_score(vacancy, position)
    score += vacancy_score * 0.20
    if vacancy_score:
        reasons.append(f"embedded vacancy: сходство вакансии и позиции {vacancy_score:.0f}/100 (+{vacancy_score * 0.20:.0f})")

    recruiter_text = _recruiter_signal_text(row_data, columns)
    recruiter_skills = set(flatten_skills(extract_skills(recruiter_text)))
    cv_skills = set(profile.get("key_skills") or [])
    overlap = recruiter_skills & cv_skills
    if recruiter_skills:
        skill_score = min(32, 32 * len(overlap) / max(len(recruiter_skills), 1))
        score += skill_score
        overlap_text = ", ".join(sorted(overlap, key=str.lower)) or "нет"
        reasons.append(f"overlapping skills: {len(overlap)}/{len(recruiter_skills)} ({overlap_text}) (+{skill_score:.0f})")

    company_score, company_reason = _company_score(row_data, str(profile.get("current_company", "")))
    score += company_score
    if company_score:
        reasons.append(f"совпадение компании {company_reason} (+{company_score:.0f})")

    filename_score = fuzz.token_set_ratio(normalize_text(candidate.get("full_name", "")), normalize_text(resume.get("original_filename", "")))
    score += filename_score * 0.05
    if filename_score:
        reasons.append(f"сходство имени файла {filename_score:.0f}/100 (+{filename_score * 0.05:.0f})")

    return min(score, 100), "; ".join(reasons) or "нет сильных сигналов"


def run_matching() -> list[dict[str, Any]]:
    MATCHED_RESUME_DIR.mkdir(parents=True, exist_ok=True)
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
        status = classify_match(best[0], second_score)
        if status == "review" and best[2]:
            enhanced_profile, processing_error = enrich_resume_with_ai_if_needed(
                resume_id=best[2]["db_id"],
                file_hash=best[2].get("file_hash", ""),
                resume_text=best[2].get("extracted_text", ""),
                local_profile=best[2]["profile"],
                reason="результат сопоставления требует ручной проверки",
            )
            if enhanced_profile != best[2]["profile"]:
                best[2]["profile"] = enhanced_profile
                rescored_score, rescored_reason = score_candidate_resume(candidate, best[2])
                best = (rescored_score, f"{rescored_reason}; AI уточнил профиль", best[2])
                scored[0] = best
                scored.sort(key=lambda item: item[0], reverse=True)
                second_score = scored[1][0] if len(scored) > 1 else 0.0
                status = classify_match(best[0], second_score)
            elif processing_error:
                best = (best[0], f"{best[1]}; processing_error: {processing_error}", best[2])
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
        database.upsert_match(match)
        results.append(match)
    return results


def classify_match(score: float, second_score: float) -> str:
    gap = score - second_score
    if score >= 90 and gap >= 10:
        return "matched"
    if score >= 70:
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
    }


def _resume_from_row(row: Any) -> dict[str, Any]:
    return {
        "db_id": row["id"],
        "original_filename": row["original_filename"],
        "file_path": row["file_path"],
        "file_hash": row["file_hash"] or "",
        "extracted_text": row["extracted_text"] or "",
        "profile": json.loads(row["profile_json"]),
    }


def _name_score(candidate_name: str, resume_name: str) -> float:
    candidate_variants = name_variants(candidate_name)
    resume_variants = name_variants(resume_name)
    if not candidate_variants or not resume_variants:
        return 0
    return max(fuzz.token_sort_ratio(a, b) for a in candidate_variants for b in resume_variants)


def _find_email(row_data: dict[str, Any]) -> str:
    for value in row_data.values():
        text = str(value or "")
        if "@" in text:
            return text.strip()
    return ""


def _find_phone(row_data: dict[str, Any]) -> str:
    for value in row_data.values():
        phone = normalize_phone(str(value or ""))
        if len(phone) >= 10:
            return phone
    return ""


def _vacancy_score(vacancy: str, position: str) -> float:
    normalized_vacancy = normalize_text(vacancy)
    normalized_position = normalize_text(position)
    score = fuzz.token_set_ratio(normalized_vacancy, normalized_position)
    embedded_terms = {"embedded", "stm32", "esp32", "rtos", "freertos", "linux"}
    if "embedded" in normalized_position and (
        "embedded" in normalized_vacancy or "programmist" in normalized_vacancy or "программист" in vacancy.lower()
    ):
        score = max(score, 100)
    if embedded_terms & set(normalized_vacancy.split()) and embedded_terms & set(normalized_position.split()):
        score = max(score, 90)
    return score


def _recruiter_signal_text(row_data: dict[str, Any], columns: list[str]) -> str:
    comment_aliases = {normalize_text(alias) for alias in COLUMN_ALIASES.get("recruiter_comment", [])}
    parts = []
    for col in columns:
        col_norm = normalize_text(col)
        if col_norm in comment_aliases or "otsenka" in col_norm or "poisk" in col_norm or "коммент" in col.lower():
            parts.append(str(row_data.get(col) or ""))
    return " ".join(parts)


def _company_score(row_data: dict[str, Any], company: str) -> tuple[float, str]:
    if not company:
        return 0, ""
    normalized_company = normalize_text(company)
    company_alias = normalized_company.replace("jsc ", "").replace("ojsc ", "").strip()
    for value in row_data.values():
        normalized_value = normalize_text(str(value or ""))
        if normalized_company and normalized_company in normalized_value:
            return 10, company
        if company_alias and company_alias in normalized_value:
            return 10, company_alias
    return 0, ""
