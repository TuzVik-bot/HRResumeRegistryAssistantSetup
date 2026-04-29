import re

from app.text_utils import normalize_text


SKILL_KEYWORDS = {
    "programming_languages": [
        "python",
        "c",
        "c++",
        "cpp",
        "c#",
        "java",
        "javascript",
        "typescript",
        "go",
        "rust",
        "matlab",
    ],
    "embedded_stack": [
        "embedded",
        "rtos",
        "freertos",
        "stm32",
        "esp32",
        "arm",
        "cortex",
        "embedded linux",
        "bsp",
        "linux kernel",
        "yocto",
        "yocto project",
        "u-boot",
        "uboot",
        "drivers",
        "device drivers",
        "board bring-up",
        "board bring up",
        "bare metal",
        "микроконтроллер",
        "плис",
        "fpga",
    ],
    "protocols": [
        "can",
        "fdcan",
        "canopen",
        "uart",
        "spi",
        "i2c",
        "ethernet",
        "modbus",
        "mqtt",
        "tcp",
        "udp",
        "usb",
        "bluetooth",
    ],
    "tools": [
        "git",
        "docker",
        "jira",
        "linux",
        "cmake",
        "gcc",
        "gdb",
        "oscilloscope",
        "keil",
        "iar",
        "jenkins",
    ],
}


def extract_skills(text: str | None) -> dict[str, list[str]]:
    raw_text = str(text or "").lower()
    normalized = f" {normalize_text(text)} "
    result: dict[str, list[str]] = {}
    for group, keywords in SKILL_KEYWORDS.items():
        found = []
        for keyword in keywords:
            if _has_skill(raw_text, normalized, keyword):
                found.append(keyword)
        result[group] = sorted(set(found), key=str.lower)
    return result


def flatten_skills(skills: dict[str, list[str]]) -> list[str]:
    values: list[str] = []
    for items in skills.values():
        values.extend(items)
    return sorted(set(values), key=str.lower)


def _has_skill(raw_text: str, normalized_text: str, keyword: str) -> bool:
    if keyword == "c++":
        return bool(re.search(r"(?<![a-z0-9+#])c\+\+(?![a-z0-9+#])", raw_text))
    if keyword == "c#":
        return bool(re.search(r"(?<![a-z0-9+#])c#(?![a-z0-9+#])", raw_text))
    if keyword == "c":
        return bool(re.search(r"(?<![a-z0-9+#])c(?![a-z0-9+#])", raw_text))
    key = normalize_text(keyword)
    return f" {key} " in normalized_text or key in normalized_text
