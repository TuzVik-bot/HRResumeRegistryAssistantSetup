from itertools import product
import re
from unidecode import unidecode


CYR_TO_LAT_VARIANTS = {
    "а": ["a"],
    "б": ["b"],
    "в": ["v", "w"],
    "г": ["g", "h"],
    "д": ["d"],
    "е": ["e", "ye"],
    "ё": ["e", "yo"],
    "ж": ["zh"],
    "з": ["z"],
    "и": ["i", "y"],
    "й": ["i", "y"],
    "к": ["k", "c"],
    "л": ["l"],
    "м": ["m"],
    "н": ["n"],
    "о": ["o", "a"],
    "п": ["p"],
    "р": ["r"],
    "с": ["s"],
    "т": ["t"],
    "у": ["u"],
    "ф": ["f"],
    "х": ["kh", "h", "ch"],
    "ц": ["ts", "c"],
    "ч": ["ch"],
    "ш": ["sh"],
    "щ": ["shch", "sch"],
    "ы": ["y", "i"],
    "э": ["e"],
    "ю": ["yu", "iu"],
    "я": ["ya", "ia"],
    "ь": [""],
    "ъ": [""],
}

SPECIAL_NAME_VARIANTS = {
    "глеб": ["gleb", "hleb"],
    "виталий": ["vitaly", "vitali", "vitalii"],
    "чечуха": ["chechukha", "chachukha"],
    "арбузов": ["arbuzov", "arbuzau"],
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = str(value).lower().replace("ё", "е")
    value = unidecode(value)
    value = re.sub(r"[^a-z0-9а-яё$рруб]+", " ", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip()


def normalize_phone(value: str | None) -> str:
    if not value:
        return ""
    digits = re.sub(r"\D+", "", str(value))
    if len(digits) == 11 and digits.startswith(("7", "8")):
        return "7" + digits[1:]
    return digits


def transliterate_ru(value: str | None) -> str:
    if not value:
        return ""
    return normalize_text(unidecode(str(value)))


def name_variants(full_name: str | None) -> set[str]:
    if not full_name:
        return set()
    tokens = [t for t in re.split(r"\s+", str(full_name).lower().replace("ё", "е")) if t]
    variants: list[list[str]] = []
    for token in tokens:
        token_clean = re.sub(r"[^а-яa-z-]+", "", token)
        if not token_clean:
            continue
        if re.search(r"[а-я]", token_clean):
            base = transliterate_ru(token_clean)
            token_variants = {base, *SPECIAL_NAME_VARIANTS.get(token_clean, [])}
        else:
            token_variants = {normalize_text(token_clean)}
        variants.append(sorted(token_variants))
    if not variants:
        return set()
    primary_tokens = [items[0] for items in variants]
    result = {" ".join(primary_tokens), " ".join(reversed(primary_tokens))}
    if len(variants) >= 2:
        first_three = variants[:3]
        token_combinations = list(product(*first_three))[:50]
        orders = [(0, 1), (1, 0)]
        if len(first_three) >= 3:
            orders.extend([(0, 1, 2), (1, 2, 0), (0, 2, 1), (2, 1, 0)])
        for combo in token_combinations:
            for order in orders:
                if max(order) < len(combo):
                    result.add(" ".join(combo[index] for index in order))
    return {normalize_text(v) for v in result if v.strip()}


def safe_filename(value: str | None, fallback: str = "value", max_length: int = 180) -> str:
    cleaned = re.sub(r"[^\wа-яА-ЯёЁ$.-]+", "_", str(value or fallback), flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_.")
    cleaned = cleaned or fallback
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[:max_length].rstrip("_.") or fallback[:max_length]
