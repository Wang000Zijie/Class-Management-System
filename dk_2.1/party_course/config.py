import os
import json
import secrets


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
SETTINGS_FILE = os.path.join(INSTANCE_DIR, "app_settings.json")
DEFAULT_DB_PATH = os.path.join(INSTANCE_DIR, "party_course.db")


def _str_to_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


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


def _write_local_settings(settings: dict) -> None:
    try:
        os.makedirs(INSTANCE_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        # Keep startup resilient even if settings file is temporarily unwritable.
        pass


def _resolve_secret_key(local_settings: dict) -> str:
    env_key = (os.environ.get("SECRET_KEY") or "").strip()
    if len(env_key) >= 24:
        return env_key

    local_key = str(local_settings.get("SECRET_KEY") or "").strip()
    if len(local_key) >= 24:
        return local_key

    generated = secrets.token_urlsafe(32)
    local_settings["SECRET_KEY"] = generated
    _write_local_settings(local_settings)
    return generated


LOCAL_SETTINGS = _load_local_settings()
os.makedirs(INSTANCE_DIR, exist_ok=True)
SECRET_KEY = _resolve_secret_key(LOCAL_SETTINGS)
SESSION_COOKIE_SECURE = _str_to_bool(
    os.environ.get("SESSION_COOKIE_SECURE", LOCAL_SETTINGS.get("SESSION_COOKIE_SECURE")),
    default=False,
)
DEBUG = _str_to_bool(
    os.environ.get("DEBUG", LOCAL_SETTINGS.get("DEBUG")),
    default=False,
)


class Config:
    SECRET_KEY = SECRET_KEY
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("SQLALCHEMY_DATABASE_URI")
        or LOCAL_SETTINGS.get("SQLALCHEMY_DATABASE_URI")
        or _sqlite_uri(DEFAULT_DB_PATH)
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEBUG = DEBUG
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    WTF_CSRF_TIME_LIMIT = 7200
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY") or LOCAL_SETTINGS.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL") or LOCAL_SETTINGS.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL") or LOCAL_SETTINGS.get("DEEPSEEK_MODEL", "deepseek-chat")