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

def _secret(arn_var: str) -> str:
    """A Secrets Manager value named by the env var `arn_var` (set by deploy/template.yaml on Lambda), else ""."""
    arn = os.environ.get(arn_var, "")
    if not arn:
        return ""
    import boto3
    return boto3.client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"].strip()


ON_LAMBDA = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))  # deployed by deploy/deploy.sh

SECRET_KEY = (_secret("DJANGO_SECRET_KEY_SECRET_ARN") or os.environ.get("DJANGO_SECRET_KEY")
              or "poc-insecure-key-swap-before-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

# Demo PoC: allow any host so it runs behind whatever AWS gives us. Tighten for production.
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o
] or [
    "https://*.amazonaws.com", "https://*.elb.amazonaws.com",
    "https://*.on.aws",           # Lambda function URLs (deploy/deploy.sh)
    "https://*.cloudfront.net",   # workshop path proxies behind CloudFront, e.g. https://<id>.cloudfront.net/proxy/8000/
    "https://*.sagemaker.aws",    # SageMaker Studio / code editor proxies
]
# Path proxies forward to the app under a different Host; trust the original host when they pass it on.
USE_X_FORWARDED_HOST = True

if ON_LAMBDA:
    # The function URL terminates HTTPS and forwards the scheme in X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "django.contrib.sessions",
    "exchange",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "exchange.middleware.RelativeScriptPrefixMiddleware",  # links work behind any path proxy (e.g. /proxy/8000/)
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

# Behind a path proxy (e.g. /proxy/8000/) links are made relative per request (exchange/middleware.py), so no
# setting is needed. URL_PREFIX, if set, makes Django emit absolute URLs under that prefix instead.
FORCE_SCRIPT_NAME = os.environ.get("URL_PREFIX") or None
_PREFIX = (FORCE_SCRIPT_NAME or "").rstrip("/")

STATIC_URL = f"{_PREFIX}/static/" if _PREFIX else "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "exchange" / "static"]
STORAGES = {
    # WhiteNoise's compressed manifest storage, with URLs relative to the page (exchange/storage.py)
    "staticfiles": {"BACKEND": "exchange.storage.RelativeStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------ app configuration

# Bedrock model for the (optional) live LLM path.
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-6")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
# When false (default for the PoC), the chat uses the deterministic mock engine, no AWS calls.
USE_BEDROCK = os.environ.get("USE_BEDROCK", "0") == "1"
# Claude on Bedrock reads attached photos and documents (aws_tools.read_attachment).
VISION_MODEL_ID = os.environ.get("VISION_MODEL_ID", "us.anthropic.claude-haiku-5-5")

# S3 bucket for message attachments (browser uploads via presigned PUT URLs). Empty = feature off.
UPLOADS_BUCKET = os.environ.get("UPLOADS_BUCKET", "")

# Live weather via Open-Meteo (no API key). Falls back to the persona's mocked values on any error.
USE_LIVE_WEATHER = os.environ.get("USE_LIVE_WEATHER", "1") == "1"

# Data source for the chat (see docs/REAL-API.md). "mock" answers from exchange/engine.py; "live" talks to the
# real FEX agent through the Fair Exchange chat API at FEX_API_URL. The chat header can switch per session.
DATA_SOURCE = os.environ.get("DATA_SOURCE", "mock")
DATA_SOURCE = DATA_SOURCE if DATA_SOURCE in ("mock", "live") else "mock"
FEX_API_URL = os.environ.get("FEX_API_URL", "")            # local chain: http://127.0.0.1:3000; deployed: ApiUrl output
FEX_DEMO_PASSCODE = (os.environ.get("FEX_DEMO_PASSCODE", "")  # deployed API only (DemoPasscodeSecretArn)
                     or _secret("FEX_DEMO_PASSCODE_SECRET_ARN"))
FEX_API_TIMEOUT = int(os.environ.get("FEX_API_TIMEOUT", "300"))  # seconds; a real answer turn can take a while
