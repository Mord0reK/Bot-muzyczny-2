import os
import tomllib

CONFIG_FILE = "config/config.toml"

CONFIG_TEMPLATE = """\
# =============================================================================
# Bot Muzyczny Discord — Konfiguracja
# =============================================================================
# Wszystkie ustawienia w jednym pliku. Linie zaczynające się od # to komentarze.
# Po zmianach zrestartuj bota.
# Token bota ustaw w pliku .env (DISCORD_TOKEN).
# =============================================================================

[bot]
# Poziom logowania: DEBUG, INFO, WARNING, ERROR
log_level = "INFO"

[voice]
# Domyślna głośność bota (0-200, 100 = oryginalna głośność)
default_volume = 100

# Czas w sekundach, po którym bot opuści kanał głosowy gdy kolejka jest pusta
# Ustaw 0 aby bot nigdy nie opuszczał kanału automatycznie
auto_leave_seconds = 300

[youtube]
# Ścieżka do pliku cookies.txt — wymagana gdy bot działa na VPS/datacenter
# YouTube blokuje zapytania z serwerów, cookies omijają to ograniczenie
# Jak wyeksportować: rozszerzenie "Get cookies.txt LOCALLY" → YouTube → eksport
# cookies_path = "data/cookies.txt"

# Maksymalna dozwolona długość utworu w sekundach (7200 = 2 godziny)
max_duration = 7200

[radio]
# URL API z listą stacji radiowych
api_url = "https://api.radyjko.mordorek.dev/stations"

# Limit czasu zapytań do API radiowego w sekundach
api_timeout = 10

[data]
# Folder na pliki danych (kolejka, ulubione, historia)
folder = "data"
"""

EDITABLE_KEYS = {
    ("bot", "log_level", "Poziom logowania: DEBUG, INFO, WARNING, ERROR"),
    ("voice", "default_volume", "Domyślna głośność bota (0-200)"),
    ("voice", "auto_leave_seconds", "Czas do opuszczenia kanału po opróżnieniu kolejki (0 = nigdy)"),
    ("youtube", "cookies_path", "Ścieżka do pliku cookies.txt dla YouTube"),
    ("youtube", "max_duration", "Maksymalna długość utworu w sekundach"),
    ("radio", "api_url", "URL API stacji radiowych"),
    ("radio", "api_timeout", "Limit czasu zapytań do API radiowego (sekundy)"),
    ("data", "folder", "Folder na pliki danych"),
}


def load_config(path: str = CONFIG_FILE) -> dict:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(CONFIG_TEMPLATE)
        print(f"[config] Utworono {path} z domyślną konfiguracją.")

    with open(path, "rb") as f:
        return tomllib.load(f)


def _parse_raw(path: str = CONFIG_FILE) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return f.readlines()


def _find_value_line(lines: list[str], section: str, key: str) -> int | None:
    in_section = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == f"[{section}]":
            in_section = True
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section:
                return None
            in_section = False
            continue
        if in_section and stripped.startswith(f"{key}"):
            return i
    return None


def _format_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return f'"{value}"'
    if value is None:
        return '""'
    return str(value)


def set_value(section: str, key: str, value, path: str = CONFIG_FILE) -> bool:
    if not any(s == section and k == key for s, k, _ in EDITABLE_KEYS):
        return False

    lines = _parse_raw(path)
    line_idx = _find_value_line(lines, section, key)
    if line_idx is None:
        return False

    indent = ""
    if lines[line_idx][0] in (" ", "\t"):
        indent = lines[line_idx][: len(lines[line_idx]) - len(lines[line_idx].lstrip())]

    lines[line_idx] = f"{indent}{key} = {_format_value(value)}\n"

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return True


def format_config(cfg: dict) -> str:
    parts = []
    for section, values in cfg.items():
        if not isinstance(values, dict):
            continue
        parts.append(f"**[{section}]**")
        for key, val in values.items():
            display = val if val is not None else "*(brak)*"
            parts.append(f"  `{key}` = `{display}`")
        parts.append("")
    return "\n".join(parts)


def get_editable_keys() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for section, key, _ in EDITABLE_KEYS:
        result.setdefault(section, []).append(key)
    return result


def get_key_descriptions() -> dict[str, str]:
    return {f"{section}.{key}": desc for section, key, desc in EDITABLE_KEYS}
