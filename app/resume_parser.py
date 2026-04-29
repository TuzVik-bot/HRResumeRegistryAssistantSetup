import re
from pathlib import Path

import fitz
from docx import Document

from app.skills import extract_skills, flatten_skills
from app.text_utils import normalize_phone


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?\d[\s()\-]*){9,16}")


def extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(file_path)
    if suffix == ".docx":
        return _extract_docx(file_path)
    if suffix == ".txt":
        return file_path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"Unsupported resume format: {suffix}")


def parse_resume_profile(text: str, filename: str = "") -> dict[str, object]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    skills = extract_skills(text)
    email = _first_match(EMAIL_RE, text)
    phone_raw = _first_match(PHONE_RE, text)
    full_name = _guess_full_name(lines, filename)
    return {
        "full_name_original": full_name,
        "email": email,
        "phone": normalize_phone(phone_raw),
        "city": _field_after_label(text, ["city", "город", "location"]),
        "current_position": _guess_position(lines),
        "current_company": _field_after_label(text, ["company", "компания", "работодатель"]),
        "years_experience": _guess_years_experience(text),
        "education": _field_after_label(text, ["education", "образование"]),
        "english_level": _guess_english_level(text),
        "programming_languages": skills["programming_languages"],
        "embedded_stack": skills["embedded_stack"],
        "protocols": skills["protocols"],
        "tools": skills["tools"],
        "key_skills": flatten_skills(skills),
    }


def _extract_pdf(file_path: Path) -> str:
    parts = []
    with fitz.open(file_path) as doc:
        for page in doc:
            parts.append(page.get_text())
    return "\n".join(parts)


def _extract_docx(file_path: Path) -> str:
    document = Document(file_path)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _first_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(0).strip() if match else ""


def _guess_full_name(lines: list[str], filename: str) -> str:
    for line in lines[:8]:
        cleaned = re.sub(r"\s+", " ", line).strip()
        words = cleaned.split()
        if 2 <= len(words) <= 4 and not EMAIL_RE.search(cleaned) and not PHONE_RE.search(cleaned):
            if not re.search(r"(resume|cv|резюме|engineer|developer|manager)", cleaned, re.IGNORECASE):
                return cleaned
    return Path(filename).stem.replace("_", " ").replace("-", " ")


def _guess_position(lines: list[str]) -> str:
    patterns = ["engineer", "developer", "manager", "architect", "разработчик", "инженер", "руководитель"]
    for line in lines[:20]:
        if any(pattern in line.lower() for pattern in patterns):
            return line[:160]
    return ""


def _field_after_label(text: str, labels: list[str]) -> str:
    for label in labels:
        match = re.search(rf"{label}\s*[:\-]\s*(.+)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:160]
    return ""


def _guess_years_experience(text: str) -> str:
    patterns = [
        r"(\d{1,2})\+?\s*(?:years|yrs|лет|года)\s+(?:experience|опыта)",
        r"(?:experience|опыт)\D{0,20}(\d{1,2})\+?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _guess_english_level(text: str) -> str:
    match = re.search(r"\b(A1|A2|B1|B2|C1|C2|Intermediate|Upper Intermediate|Advanced|Fluent)\b", text, re.IGNORECASE)
    return match.group(0) if match else ""
