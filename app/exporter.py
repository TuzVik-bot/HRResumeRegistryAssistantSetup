import json
from pathlib import Path

import pandas as pd

from app import database
from app.config import EXPORT_DIR
from app.i18n import reason_label, status_label, warning_label


EXPORT_COLUMNS = [
    "candidate_id",
    "resume_match_status",
    "resume_match_confidence",
    "resume_original_filename",
    "resume_new_filename",
    "resume_file_path",
    "cv_full_name_original",
    "cv_full_name_ru_guess",
    "cv_email",
    "cv_phone",
    "cv_city",
    "cv_current_position",
    "cv_current_company",
    "cv_years_experience",
    "cv_english_level",
    "cv_key_skills",
    "cv_embedded_stack",
    "cv_summary_ru",
    "cv_interview_questions_ru",
    "cv_ai_confidence",
    "match_reason",
    "data_quality_warnings",
    "processing_error",
    "needs_manual_review",
]


def export_enriched_excel() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for row in database.fetch_candidates_with_matches():
        original = json.loads(row["row_data_json"])
        profile = json.loads(row["resume_profile_json"]) if row["resume_profile_json"] else {}
        enriched = {
            **original,
            "candidate_id": row["candidate_id"],
            "resume_match_status": status_label(row["match_status"]),
            "resume_match_confidence": row["score"] or 0,
            "resume_original_filename": row["resume_original_filename"] or "",
            "resume_new_filename": row["new_filename"] or "",
            "resume_file_path": row["output_path"] or "",
            "cv_full_name_original": profile.get("full_name_original", ""),
            "cv_full_name_ru_guess": profile.get("full_name_ru_guess", ""),
            "cv_email": profile.get("email", ""),
            "cv_phone": profile.get("phone", ""),
            "cv_city": profile.get("city", ""),
            "cv_current_position": profile.get("current_position", ""),
            "cv_current_company": profile.get("current_company", ""),
            "cv_years_experience": profile.get("years_experience", ""),
            "cv_english_level": profile.get("english_level", ""),
            "cv_key_skills": ", ".join(profile.get("key_skills", [])),
            "cv_embedded_stack": ", ".join(profile.get("embedded_stack", [])),
            "cv_summary_ru": profile.get("summary_ru") or build_summary(profile),
            "cv_interview_questions_ru": "; ".join(profile.get("interview_questions_ru", [])),
            "cv_ai_confidence": profile.get("ai_confidence", ""),
            "match_reason": reason_label(row["match_reason"]),
            "data_quality_warnings": "; ".join(warning_label(item) for item in json.loads(row["quality_warnings_json"])),
            "processing_error": row["resume_processing_error"] or "",
            "needs_manual_review": bool(row["needs_manual_review"]) if row["needs_manual_review"] is not None else True,
        }
        rows.append(enriched)
    output_path = EXPORT_DIR / "enriched_registry.xlsx"
    pd.DataFrame(rows).to_excel(output_path, index=False)
    return output_path


def build_summary(profile: dict[str, object]) -> str:
    if not profile:
        return ""
    parts = [
        str(profile.get("current_position") or "").strip(),
        str(profile.get("current_company") or "").strip(),
        f"опыт {profile.get('years_experience')} лет" if profile.get("years_experience") else "",
        f"English {profile.get('english_level')}" if profile.get("english_level") else "",
    ]
    skills = profile.get("key_skills") or []
    if skills:
        parts.append("навыки: " + ", ".join(skills[:12]))
    return "; ".join(part for part in parts if part)
