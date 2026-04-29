from rapidfuzz import fuzz

from app.text_utils import name_variants, normalize_text


def test_transliteration_variants_match_belarusian_spelling():
    variants = name_variants("Арбузов Глеб")
    assert "hleb arbuzau" in variants
    assert max(fuzz.token_sort_ratio(v, normalize_text("Hleb Arbuzau")) for v in variants) >= 95


def test_transliteration_variants_match_chachukha():
    variants = name_variants("Чечуха Виталий")
    assert "chachukha vitali" in variants
    assert max(fuzz.token_sort_ratio(v, normalize_text("Vitali Chachukha")) for v in variants) >= 95
