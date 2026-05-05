import re
from pathlib import Path
from typing import Any

import pandas as pd

from app import database


MAIN_SHEET = "реестр"
TERMS_SHEET = "термины"

COLUMN_ALIASES = {
    "full_name": ["фамилия имя", "фамилия, имя", "фио", "кандидат"],
    "vacancy": ["вакансия", "позиция", "должность", "vacancy"],
    "status": ["статус", "текущее состояние взаимодействия с кандидатом", "stage"],
    "last_contact": ["последний контакт"],
    "customer_decision": ["решение заказчика по оценке резюме"],
    "interview_1": ["дата 1 го собесед", "дата 1-го собесед", "дата 1-го собес"],
    "interview_2": ["дата 2 го собесед", "дата 2-го собесед", "дата 2-го собес"],
    "salary_request": ["запрос кандидата указывается р $", "запрос кандидата, указывается р/$", "salary"],
    "recruiter": ["ответственный рекрутер", "recruiter"],
    "recruiter_comment": ["оценка рекрутера", "акт поиск", "отклик", "notes", "reject", "comment"],
}


def normalize_header(value: Any) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    text = re.sub(r"[^а-яa-z0-9$]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def map_columns(columns: list[str]) -> dict[str, str]:
    normalized = {normalize_header(col): col for col in columns}
    mapping: dict[str, str] = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            alias_norm = normalize_header(alias)
            if alias_norm in normalized:
                mapping[field] = normalized[alias_norm]
                break
            for header_norm, original in normalized.items():
                if alias_norm and alias_norm in header_norm:
                    mapping[field] = original
                    break
            if field in mapping:
                break
    return mapping


def read_terms(workbook_path: Path) -> dict[str, set[str]]:
    terms = {"statuses": set(), "recruiters": set()}
    xls = pd.ExcelFile(workbook_path)
    if TERMS_SHEET not in [sheet.lower() for sheet in xls.sheet_names]:
        return terms
    sheet_name = next(sheet for sheet in xls.sheet_names if sheet.lower() == TERMS_SHEET)
    df = pd.read_excel(workbook_path, sheet_name=sheet_name, dtype=str).fillna("")
    for col in df.columns:
        col_norm = normalize_header(col)
        values = {normalize_header(v) for v in df[col].tolist() if str(v).strip()}
        if "статус" in col_norm or "состояние" in col_norm:
            terms["statuses"].update(values)
        if "рекрутер" in col_norm or "ответственный" in col_norm:
            terms["recruiters"].update(values)
    return terms


def find_main_sheet(workbook_path: Path) -> str:
    xls = pd.ExcelFile(workbook_path)
    for sheet in xls.sheet_names:
        if sheet.lower().strip() == MAIN_SHEET:
            return sheet
    raise ValueError('В Excel не найден лист "реестр"')


def make_candidate_id(excel_row_number: int, registry_id: int | None = None) -> str:
    if registry_id is not None:
        return f"REG{registry_id:03d}-CAND-{excel_row_number:06d}"
    return f"CAND-{excel_row_number:06d}"


def import_registry(workbook_path: Path, original_filename: str, file_hash: str | None = None) -> dict[str, Any]:
    if file_hash:
        existing = database.fetch_registry_by_hash(file_hash)
        if existing:
            return {
                "registry_id": existing["id"],
                "sheet_name": find_main_sheet(workbook_path),
                "rows": 0,
                "columns": [],
                "mapping": {},
                "terms": {},
                "source_schema": existing["source_schema"] or "unknown",
                "duplicate": True,
            }

    sheet_name = find_main_sheet(workbook_path)
    df = pd.read_excel(workbook_path, sheet_name=sheet_name, dtype=object)
    df = df.dropna(how="all")
    df = df.where(pd.notna(df), None)
    columns = [str(col) for col in df.columns]
    source_schema = detect_source_schema(columns)
    if source_schema == "technical":
        df = df.iloc[2:]
    mapping = map_columns(columns)
    terms = read_terms(workbook_path)

    registry_id = database.insert_registry(original_filename, workbook_path, file_hash=file_hash, source_schema=source_schema)
    candidates = []
    for index, row in df.iterrows():
        excel_row_number = int(index) + 2
        row_data = {str(col): (None if pd.isna(row[col]) else row[col]) for col in df.columns}
        extracted = extract_candidate_fields(row_data, mapping)
        if not _has_candidate_signal(row_data, mapping, extracted):
            continue
        warnings = validate_candidate_row(row_data, mapping, terms, extracted)
        candidates.append(
            {
                "registry_id": registry_id,
                "excel_row_number": excel_row_number,
                "candidate_id": make_candidate_id(excel_row_number, registry_id),
                "row_data": row_data,
                "full_name": extracted["full_name"],
                "vacancy": extracted["vacancy"],
                "status": extracted["status"],
                "recruiter": extracted["recruiter"],
                "quality_warnings": warnings,
            }
        )
    database.insert_candidates_bulk(candidates)
    return {
        "registry_id": registry_id,
        "sheet_name": sheet_name,
        "rows": len(candidates),
        "columns": columns,
        "mapping": mapping,
        "terms": {key: sorted(value) for key, value in terms.items()},
        "source_schema": source_schema,
        "duplicate": False,
    }


def validate_candidate_row(
    row_data: dict[str, Any],
    mapping: dict[str, str],
    terms: dict[str, set[str]],
    extracted: dict[str, str | None] | None = None,
) -> list[str]:
    warnings: list[str] = []
    extracted = extracted or extract_candidate_fields(row_data, mapping)
    full_name = extracted["full_name"]
    vacancy = extracted["vacancy"]
    status = extracted["status"]
    last_contact = extracted["last_contact"]
    decision = extracted["customer_decision"]
    salary = extracted["salary_request"]
    recruiter = extracted["recruiter"]

    if not full_name:
        warnings.append("missing full name")
    if not vacancy:
        warnings.append("missing vacancy")
    if not status:
        warnings.append("missing status")
    elif terms.get("statuses") and normalize_header(status) not in terms["statuses"]:
        warnings.append("invalid status not found in термины")
    if status and normalize_header(status) == "в работе" and not last_contact:
        warnings.append('status "в работе" without last contact')
    if _has_past_interview(row_data, mapping) and not decision:
        warnings.append("past interview date without current decision")
    if salary and not re.search(r"^\s*\d+(?:[\s.,]?\d+)?(?:\s*[-–]\s*\d+(?:[\s.,]?\d+)?)?\s*(р|руб|₽|\$|byn|usd|rub)\s*$", str(salary).lower()):
        warnings.append("salary request format mismatch")
    if not recruiter:
        warnings.append("missing responsible recruiter")
    return warnings


def detect_source_schema(columns: list[str]) -> str:
    normalized_columns = {normalize_header(col) for col in columns}
    technical_columns = {"first name", "last name", "source", "vacancy", "stage", "recruiter"}
    if technical_columns.issubset(normalized_columns):
        return "technical"
    return "legacy"


def extract_candidate_fields(row_data: dict[str, Any], mapping: dict[str, str]) -> dict[str, str | None]:
    full_name = _value(row_data, mapping.get("full_name")) or _compose_technical_full_name(row_data)
    salary_request = _compose_salary_request(row_data) or _value(row_data, mapping.get("salary_request"))
    recruiter_comment = _value(row_data, mapping.get("recruiter_comment")) or _compose_comment(row_data)
    return {
        "full_name": full_name,
        "vacancy": _value(row_data, mapping.get("vacancy")),
        "status": _value(row_data, mapping.get("status")),
        "last_contact": _value(row_data, mapping.get("last_contact")),
        "customer_decision": _value(row_data, mapping.get("customer_decision")),
        "salary_request": salary_request,
        "recruiter": _value(row_data, mapping.get("recruiter")),
        "recruiter_comment": recruiter_comment,
    }


def _has_past_interview(row_data: dict[str, Any], mapping: dict[str, str]) -> bool:
    for key in ("interview_1", "interview_2"):
        value = _value(row_data, mapping.get(key))
        if value:
            parsed = pd.to_datetime(value, errors="coerce")
            if pd.notna(parsed) and parsed.date() < pd.Timestamp.today().date():
                return True
    return False


def _value(row_data: dict[str, Any], column: str | None) -> str | None:
    if not column:
        return None
    value = row_data.get(column)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _has_candidate_signal(
    row_data: dict[str, Any],
    mapping: dict[str, str],
    extracted: dict[str, str | None] | None = None,
) -> bool:
    extracted = extracted or extract_candidate_fields(row_data, mapping)
    signal_fields = [
        "full_name",
        "vacancy",
        "status",
        "recruiter",
        "recruiter_comment",
        "last_contact",
        "customer_decision",
    ]
    for field in signal_fields:
        value = extracted.get(field)
        if value and value.strip(".-—"):
            return True
    return False


def _compose_technical_full_name(row_data: dict[str, Any]) -> str | None:
    first_name = _value(row_data, "first_name")
    last_name = _value(row_data, "last_name")
    combined = " ".join(part for part in [last_name, first_name] if part)
    return combined or None


def _compose_salary_request(row_data: dict[str, Any]) -> str | None:
    salary = _value(row_data, "salary")
    currency = _value(row_data, "currency")
    if not salary:
        return None
    if not currency:
        return salary
    return f"{salary}{currency}"


def _compose_comment(row_data: dict[str, Any]) -> str | None:
    parts = [_value(row_data, "reject"), _value(row_data, "notes")]
    text = " | ".join(part for part in parts if part)
    return text or None
