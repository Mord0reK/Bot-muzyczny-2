import os

from config.toml_config import load_config

_cfg = load_config()

LOG_LEVEL = _cfg["bot"]["log_level"]

DEFAULT_VOLUME = _cfg["voice"]["default_volume"]
AUTO_LEAVE_SECONDS = _cfg["voice"]["auto_leave_seconds"]

COOKIES_PATH = _cfg["youtube"].get("cookies_path")
YTDLP_MAX_DURATION = _cfg["youtube"]["max_duration"]

RADIO_API_URL = _cfg["radio"]["api_url"]
RADIO_API_TIMEOUT = _cfg["radio"]["api_timeout"]

DATA_FOLDER = _cfg["data"]["folder"]

SETTINGS_FILE = os.path.join(DATA_FOLDER, "settings.json")
FAVORITES_FILE = os.path.join(DATA_FOLDER, "favorites.json")
HISTORY_FILE = os.path.join(DATA_FOLDER, "history.json")
