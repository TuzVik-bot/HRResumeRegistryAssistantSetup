from app.registry import map_columns, validate_candidate_row


def test_data_quality_flags_missing_and_invalid_fields():
    row = {
        "Фамилия, имя": "",
        "вакансия": "",
        "статус": "архив",
        "последний контакт": "",
        "запрос кандидата, указывается р/$": "примерно 3000",
        "ответственный рекрутер": "",
    }
    mapping = map_columns(list(row.keys()))
    warnings = validate_candidate_row(row, mapping, {"statuses": {"в работе"}, "recruiters": set()})
    assert "missing full name" in warnings
    assert "missing vacancy" in warnings
    assert "invalid status not found in термины" in warnings
    assert "salary request format mismatch" in warnings
    assert "missing responsible recruiter" in warnings


def test_data_quality_flags_in_work_without_last_contact():
    row = {
        "Фамилия, имя": "Иванов Иван",
        "вакансия": "Python developer",
        "статус": "в работе",
        "последний контакт": "",
        "ответственный рекрутер": "Анна",
    }
    mapping = map_columns(list(row.keys()))
    warnings = validate_candidate_row(row, mapping, {"statuses": {"в работе"}, "recruiters": {"анна"}})
    assert 'status "в работе" without last contact' in warnings
