"""Local application settings."""

import json
import os
from pathlib import Path

from wep.localization import AVAILABLE_LANGUAGES, DEFAULT_LANGUAGE

DEFAULT_THEME = "dark"
AVAILABLE_THEMES = frozenset({"dark", "light"})


def settings_path() -> Path:
    """Return a per-user settings path outside the source tree."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "WEP" / "settings.json"
    return Path.home() / "AppData" / "Local" / "WEP" / "settings.json"


def _load_settings(config_path: Path) -> dict[str, object]:
    try:
        with config_path.open("r", encoding="utf-8") as settings_file:
            settings = json.load(settings_file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return settings if isinstance(settings, dict) else {}


def _save_settings(settings: dict[str, object], config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as settings_file:
        json.dump(settings, settings_file, ensure_ascii=False, indent=2)
        settings_file.write("\n")


def load_theme(path: str | Path | None = None) -> str:
    """Load a valid saved theme, falling back if settings are missing or invalid."""
    config_path = Path(path) if path is not None else settings_path()
    theme = _load_settings(config_path).get("theme")
    return theme if isinstance(theme, str) and theme in AVAILABLE_THEMES else DEFAULT_THEME


def save_theme(theme: str, path: str | Path | None = None) -> None:
    """Persist a validated theme selection."""
    if theme not in AVAILABLE_THEMES:
        raise ValueError(f"Unsupported theme: {theme!r}")

    config_path = Path(path) if path is not None else settings_path()
    settings = _load_settings(config_path)
    settings["theme"] = theme
    _save_settings(settings, config_path)


def load_language(path: str | Path | None = None) -> str:
    """Load a saved interface language, defaulting to English."""
    config_path = Path(path) if path is not None else settings_path()
    language = _load_settings(config_path).get("language")
    return (
        language
        if isinstance(language, str) and language in AVAILABLE_LANGUAGES
        else DEFAULT_LANGUAGE
    )


def save_language(language: str, path: str | Path | None = None) -> None:
    """Persist a validated interface language without changing other settings."""
    if language not in AVAILABLE_LANGUAGES:
        raise ValueError(f"Unsupported language: {language!r}")

    config_path = Path(path) if path is not None else settings_path()
    settings = _load_settings(config_path)
    settings["language"] = language
    _save_settings(settings, config_path)
