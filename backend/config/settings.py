import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Load a local .env for development if one exists. Real environment variables
# (e.g. those set in the Render dashboard) always win — this only fills gaps,
# and it's a no-op if python-dotenv isn't installed.
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-secret")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "core",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600
    )
}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

CORS_ALLOW_ALL_ORIGINS = os.environ.get("FRONTEND_ORIGIN") is None
if not CORS_ALLOW_ALL_ORIGINS:
    CORS_ALLOWED_ORIGINS = [os.environ["FRONTEND_ORIGIN"]]

CSRF_TRUSTED_ORIGINS = ["https://*.onrender.com"]

# Email notifications (optional — set SMTP env vars to enable)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "OgaBoss <onboarding@resend.dev>")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")

# Send real email once an SMTP host is configured; otherwise print to the
# server logs so the app never crashes when email isn't set up yet.
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST
    else "django.core.mail.backends.console.EmailBackend"
)

# Public URL of the frontend, used to build links inside emails (password reset).
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://ogaboss-app.onrender.com").rstrip("/")

# Engine config — the app can run on Anthropic (Claude) or OpenAI (GPT).
# The live provider is a runtime switch persisted in the DB (ProviderConfig);
# LLM_PROVIDER only sets the default used the very first time, before anyone
# has flipped the switch. Both providers' keys/models come from the env below.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")  # first-run default only

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ENGINE_MODEL = os.environ.get("ENGINE_MODEL", "claude-sonnet-4-6")
ENGINE_MODEL_FAST = os.environ.get("ENGINE_MODEL_FAST", "claude-haiku-4-5-20251001")

# The "OpenAI" slot speaks the OpenAI Chat Completions format, so it also works
# with any OpenAI-compatible provider (Groq, OpenRouter, Gemini's compat
# endpoint, …) by pointing OPENAI_BASE_URL at them. Base URL + model are also
# overridable from the settings UI (ProviderConfig).
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
OPENAI_MODEL_FAST = os.environ.get("OPENAI_MODEL_FAST", "gpt-4o-mini")

# Who may switch the live AI provider. This is the app operator/owner, not the
# org's CEO — by default only Geoffrey. Override with a comma-separated list of
# usernames (case-insensitive). Django superusers can always switch.
PROVIDER_ADMINS = [
    u.strip().lower()
    for u in os.environ.get("PROVIDER_ADMINS", "geoffrey").split(",")
    if u.strip()
]
