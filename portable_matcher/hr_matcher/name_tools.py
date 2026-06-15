from __future__ import annotations

from itertools import combinations, product
import json
from pathlib import Path
import re
import unicodedata


CYR_TO_LAT_VARIANTS = {
    "а": ["a"],
    "б": ["b"],
    "в": ["v", "w"],
    "г": ["g", "h"],
    "д": ["d"],
    "е": ["e", "ye", "ie"],
    "ё": ["e", "yo"],
    "ж": ["zh"],
    "з": ["z"],
    "и": ["i", "y"],
    "і": ["i"],
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
    "ў": ["u", "w"],
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

BUILTIN_ALIASES = {
    "александр": ["alexandr", "alexander", "aliaksandr"],
    "анастасия": ["anastasia", "nastassia"],
    "андрей": ["andrey", "andrei", "andrej"],
    "артем": ["artem", "artemiy", "artsiom"],
    "виталий": ["vitaly", "vitali", "vitalii"],
    "виктор": ["viktor", "victor"],
    "виктория": ["viktoria", "victoria"],
    "владимир": ["vladimir", "uladzimir"],
    "глеб": ["gleb", "hleb"],
    "дарья": ["darya", "daria"],
    "дмитрий": ["dmitry", "dmitriy", "dzmitry"],
    "евгений": ["evgeny", "evgeniy", "yauhen", "yauheni"],
    "екатерина": ["ekaterina", "katerina", "katsiaryna"],
    "илья": ["ilya", "ilia"],
    "михаил": ["mikhail", "michael"],
    "наталья": ["natalia", "nataliya"],
    "ольга": ["olga", "volha"],
    "павел": ["pavel", "paul"],
    "сергей": ["sergey", "sergei", "siarhei"],
    "юлия": ["yulia", "julia", "iuliya"],
    "громов": ["gromov", "hromov", "gromau", "hromau"],
}

FIRST_NAME_TOKENS = {
    "александр",
    "александра",
    "алена",
    "анастасия",
    "андрей",
    "андреи",
    "анна",
    "артем",
    "виталий",
    "виталии",
    "виктор",
    "виктория",
    "владимир",
    "глеб",
    "дарья",
    "дмитрий",
    "дмитрии",
    "евгений",
    "екатерина",
    "захар",
    "иван",
    "илья",
    "карина",
    "катерина",
    "максим",
    "михаил",
    "наталья",
    "ольга",
    "павел",
    "роман",
    "светлана",
    "сергей",
    "сергеи",
    "татьяна",
    "юлия",
}

FILENAME_STOPWORDS = {
    "cv",
    "resume",
    "rezume",
    "резюме",
    "curriculum",
    "vitae",
    "developer",
    "engineer",
    "programmer",
    "manager",
    "analyst",
    "architect",
    "embedded",
    "software",
    "business",
    "ba",
    "qa",
    "dev",
    "final",
    "new",
    "copy",
    "pdf",
    "doc",
    "docx",
}


def load_aliases(path: Path | None = None) -> dict[str, list[str]]:
    aliases = {
        normalize_token(key): [normalize_token(value) for value in values if normalize_token(value)]
        for key, values in BUILTIN_ALIASES.items()
    }
    if path and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, values in data.items():
            aliases[normalize_token(key)] = [normalize_token(value) for value in values if normalize_token(value)]
    return aliases


def normalize_text(value: object) -> str:
    text = str(value or "").replace("ё", "е").replace("Ё", "Е").lower()
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    text = re.sub(r"[^0-9a-zа-яіїўєґё]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def normalize_token(value: object) -> str:
    return normalize_text(value).replace(" ", "")


def name_tokens(value: object, drop_stopwords: bool = False) -> list[str]:
    tokens = [token for token in normalize_text(value).split() if token and not token.isdigit()]
    if drop_stopwords:
        tokens = [token for token in tokens if token not in FILENAME_STOPWORDS]
    return tokens


def filename_tokens(filename: str) -> list[str]:
    stem = Path(filename).stem
    stem = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem)
    return name_tokens(stem, drop_stopwords=True)


def token_variants(token: str, aliases: dict[str, list[str]] | None = None, limit: int = 80) -> set[str]:
    aliases = aliases or BUILTIN_ALIASES
    token = normalize_token(token)
    if not token:
        return set()
    result = {token}
    result.update(aliases.get(token, []))
    if re.search(r"[а-яіїўєґ]", token):
        letters = [CYR_TO_LAT_VARIANTS.get(ch, [ch]) for ch in token]
        for combo in product(*letters):
            result.add("".join(combo))
            if len(result) >= limit:
                break
        for item in list(result):
            if "che" in item:
                result.add(item.replace("che", "cha"))
        if token.endswith("ов") and len(token) > 3:
            result.add(transliterate_token(token[:-2], aliases) + "au")
        if token.endswith("ев") and len(token) > 3:
            result.add(transliterate_token(token[:-2], aliases) + "eu")
    return {normalize_token(item) for item in result if normalize_token(item)}


def transliterate_token(token: str, aliases: dict[str, list[str]] | None = None) -> str:
    variants = token_variants(token, aliases=aliases, limit=1)
    return sorted(variants)[0] if variants else ""


def name_variants(full_name: object, aliases: dict[str, list[str]] | None = None) -> set[str]:
    aliases = aliases or BUILTIN_ALIASES
    tokens = name_tokens(full_name)
    if not tokens:
        return set()
    per_token = [sorted(token_variants(token, aliases=aliases))[:20] for token in tokens[:4]]
    result: set[str] = set()
    for size in (2, 3):
        if len(per_token) < size:
            continue
        for indexes in combinations(range(len(per_token)), size):
            groups = [per_token[index] for index in indexes]
            for combo in list(product(*groups))[:160]:
                result.add(" ".join(combo))
                result.add(" ".join(reversed(combo)))
    if len(per_token) == 1:
        result.update(per_token[0])
    if len(per_token) >= 2:
        surname_variants = per_token[0]
        first_initials = _initials(per_token[1])
        for surname in surname_variants:
            for first_initial in first_initials:
                result.add(f"{surname} {first_initial}")
                result.add(f"{first_initial} {surname}")
                if len(per_token) >= 3:
                    for patronymic_initial in _initials(per_token[2]):
                        result.add(f"{surname} {first_initial} {patronymic_initial}")
                        result.add(f"{first_initial} {patronymic_initial} {surname}")
    return {normalize_text(item) for item in result if item.strip()}


def _initials(values: list[str]) -> set[str]:
    return {value[0] for value in values if value}


def filename_windows(filename: str) -> set[str]:
    tokens = filename_tokens(filename)
    windows: set[str] = set()
    for size in (2, 3, 4):
        if len(tokens) < size:
            continue
        for start in range(0, len(tokens) - size + 1):
            windows.add(" ".join(tokens[start : start + size]))
    if tokens:
        windows.add(" ".join(tokens))
    return windows


def safe_filename(value: object, fallback: str = "value", max_length: int = 120) -> str:
    cleaned = re.sub(r"[^\wа-яА-ЯёЁіІїЇўЎєЄґҐ$.-]+", "_", str(value or fallback), flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_.")
    cleaned = cleaned or fallback
    return cleaned[:max_length].rstrip("_.") or fallback[:max_length]
