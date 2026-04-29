STATUS_LABELS = {
    "matched": "совпадение подтверждено",
    "review": "нужна ручная проверка",
    "unmatched": "совпадение не найдено",
    "not_run": "сопоставление не запускалось",
}

WARNING_LABELS = {
    "missing full name": "не заполнено ФИО",
    "missing vacancy": "не заполнена вакансия",
    "missing status": "не заполнен статус",
    "invalid status not found in термины": "статус не найден на листе «термины»",
    'status "в работе" without last contact': "статус «в работе» без даты последнего контакта",
    "past interview date without current decision": "прошедшая дата интервью без решения заказчика",
    "salary request format mismatch": "запрос кандидата не соответствует формату зарплаты",
    "missing responsible recruiter": "не заполнен ответственный рекрутер",
}

REASON_REPLACEMENTS = {
    "transliteration": "транслитерация",
    "embedded vacancy": "embedded-вакансия",
    "overlapping skills": "пересечение навыков",
    "second best score": "второй лучший результат",
    "точное совпадение email": "точное совпадение email",
    "точное совпадение телефона": "точное совпадение телефона",
    "сходство имени файла": "сходство имени файла",
    "совпадение компании": "совпадение компании",
    "AI уточнил профиль": "ИИ уточнил профиль",
    "processing_error": "ошибка обработки",
    "no strong signals": "нет сильных сигналов",
    "резюме не загружены": "резюме не загружены",
}


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(status or "not_run", status or "сопоставление не запускалось")


def warning_label(warning: str) -> str:
    return WARNING_LABELS.get(warning, warning)


def reason_label(reason: str | None) -> str:
    text = str(reason or "")
    for source, target in REASON_REPLACEMENTS.items():
        text = text.replace(source, target)
    return text
