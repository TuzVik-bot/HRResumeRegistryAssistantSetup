from rapidfuzz import fuzz

from app.text_utils import name_variants, normalize_text, safe_filename


def test_transliteration_variants_match_belarusian_spelling():
    variants = name_variants("Арбузов Глеб")
    assert "hleb arbuzau" in variants
    assert max(fuzz.token_sort_ratio(v, normalize_text("Hleb Arbuzau")) for v in variants) >= 95


def test_transliteration_variants_match_chachukha():
    variants = name_variants("Чечуха Виталий")
    assert "chachukha vitali" in variants
    assert max(fuzz.token_sort_ratio(v, normalize_text("Vitali Chachukha")) for v in variants) >= 95


def test_three_token_russian_name_permutation():
    variants = name_variants("Иванов Иван Иванович")
    assert max(fuzz.token_sort_ratio(v, normalize_text("Ivan Ivanovich Ivanov")) for v in variants) >= 95


def test_safe_filename_truncates_under_max_path():
    value = "REG001-CAND-000001__" + ("ОченьДлинноеИмя" * 40)
    result = safe_filename(value, max_length=180)
    assert len(result) <= 180
    assert result.startswith("REG001-CAND-000001")
