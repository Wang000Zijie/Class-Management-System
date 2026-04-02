import os
import json


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
SETTINGS_FILE = os.path.join(INSTANCE_DIR, "app_settings.json")
DEFAULT_DB_PATH = os.path.join(INSTANCE_DIR, "party_course.db")


def _sqlite_uri(path: str) -> str:
    return "sqlite:///" + os.path.abspath(path).replace("\\", "/")


def _load_local_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


LOCAL_SETTINGS = _load_local_settings()
os.makedirs(INSTANCE_DIR, exist_ok=True)


class Config:
    SECRET_KEY = "change-this-in-production"
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("SQLALCHEMY_DATABASE_URI")
        or LOCAL_SETTINGS.get("SQLALCHEMY_DATABASE_URI")
        or _sqlite_uri(DEFAULT_DB_PATH)
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEBUG = True
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY") or LOCAL_SETTINGS.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL") or LOCAL_SETTINGS.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL") or LOCAL_SETTINGS.get("DEEPSEEK_MODEL", "deepseek-chat")