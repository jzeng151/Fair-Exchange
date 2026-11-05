"""Django settings for the Fair Trade USA Producer Exchange PoC.

A standalone proof-of-concept chat UI (SDD.md). No sign-on. The chat is mocked today and
designed to swap in the real Fair Exchange API later. LLM access, when enabled, goes through
Amazon Bedrock using credentials from .env (never a third-party model API, per the tech-env doc).
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> None:
    """Load `export KEY="value"` lines from .env into os.environ.

    We parse it ourselves instead of python-dotenv: the workshop .env contains an AWS session token
    whose value trips dotenv's parser, which then silently drops every later line (including app
    config). This reader is tolerant and never overrides an already-set environment variable.
    """
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


# .env holds AWS credentials and app config. Loaded but never logged.
_load_env(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "poc-insecure-key-swap-before-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

# Demo PoC: allow any host so it runs behind whatever AWS gives us. Tighten for production.
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o
] or ["https://*.amazonaws.com", "https://*.elb.amazonaws.com"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "django.contrib.sessions",
    "exchange",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "exchange" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Sessions in a signed cookie: no database needed for this PoC (chat history lives client-side too).
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_SAMESITE = "Lax"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Behind the workshop proxy the app is served under a path prefix (e.g. /proxy/8099/).
# FORCE_SCRIPT_NAME makes Django emit URLs (static, api) under that prefix so assets resolve.
FORCE_SCRIPT_NAME = os.environ.get("URL_PREFIX") or None
_PREFIX = (FORCE_SCRIPT_NAME or "").rstrip("/")

STATIC_URL = f"{_PREFIX}/static/" if _PREFIX else "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "exchange" / "static"]
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------ app configuration

# Bedrock model for the (optional) live LLM path.
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-6")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
# When false (default for the PoC), the chat uses the deterministic mock engine, no AWS calls.
USE_BEDROCK = os.environ.get("USE_BEDROCK", "0") == "1"

# S3 bucket for message attachments (browser uploads via presigned PUT URLs). Empty = feature off.
UPLOADS_BUCKET = os.environ.get("UPLOADS_BUCKET", "")

# Live weather via Open-Meteo (no API key). Falls back to the persona's mocked values on any error.
USE_LIVE_WEATHER = os.environ.get("USE_LIVE_WEATHER", "1") == "1"
