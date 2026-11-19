
"""
Django settings for config project.
Production: Render + Supabase PostgreSQL + Cloudinary
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv


# ==================================================
# 1. BASE CONFIGURATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent

# Load local .env file.
# Render environment variables are read directly from os.environ.
load_dotenv(BASE_DIR / ".env")

REQUIRED_ENVIRONMENT_VARIABLES = (
    "DATABASE_URL",
    "SECRET_KEY",
    "GROQ_API_KEY",
    "CLOUDINARY_CLOUD_NAME",
    "CLOUDINARY_API_KEY",
    "CLOUDINARY_API_SECRET",
)

print("[startup] Checking required environment variables:")
for variable in REQUIRED_ENVIRONMENT_VARIABLES:
    configured = bool(os.getenv(variable, "").strip())
    state = "configured" if configured else "MISSING"
    print(f"[startup] {variable}: {state}", flush=True)

DEBUG = os.getenv("DEBUG", "False").lower() == "true"

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "django-insecure-development-only-change-this"
)

if not DEBUG and (
    not SECRET_KEY
    or SECRET_KEY == "django-insecure-development-only-change-this"
):
    raise ValueError("Set a secure SECRET_KEY in Render Environment Variables.")


# ==================================================
# 2. ALLOWED HOSTS
# ==================================================

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "ALLOWED_HOSTS",
        "localhost,127.0.0.1,.onrender.com"
    ).split(",")
    if host.strip()
]


# ==================================================
# 3. CORS AND CSRF CONFIGURATION
# ==================================================

CORS_ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CSRF_TRUSTED_ORIGINS",
        "https://ai-pdf-chatbox-mxdw.onrender.com"
    ).split(",")
    if origin.strip()
]

# Apply CORS to API endpoints.
CORS_URLS_REGEX = r"^/api/.*$"

# Enable this only if your frontend uses cross-origin cookies.
CORS_ALLOW_CREDENTIALS = False


# ==================================================
# 4. APPLICATION DEFINITION
# ==================================================

INSTALLED_APPS = [

    # Django built-in apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party apps
    "rest_framework",
    "corsheaders",

    # Cloudinary
    "cloudinary",
    "cloudinary_storage",

    # Local apps
    "documents.apps.DocumentsConfig",
]


# ==================================================
# 5. MIDDLEWARE
# ==================================================

MIDDLEWARE = [

    "django.middleware.security.SecurityMiddleware",

    # CORS must be before CommonMiddleware
    "corsheaders.middleware.CorsMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",

    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ==================================================
# 6. URL AND WSGI CONFIGURATION
# ==================================================

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"


# ==================================================
# 7. TEMPLATES
# ==================================================

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
            ],
        },
    },
]


# ==================================================
# 8. SUPABASE POSTGRESQL DATABASE
# ==================================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL is missing from environment variables!"
    )

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=True,
    )
}


# ==================================================
# 9. PASSWORD VALIDATION
# ==================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ==================================================
# 10. INTERNATIONALIZATION
# ==================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# ==================================================
# 11. STATIC FILES
# ==================================================

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"


# ==================================================
# 12. MEDIA FILES
# ==================================================

MEDIA_URL = "/media/"

# Local fallback directory.
# The configured default storage below uses Cloudinary.
MEDIA_ROOT = BASE_DIR / "media"

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024


# ==================================================
# 13. CLOUDINARY CONFIGURATION
# ==================================================

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")

CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")

CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")


CLOUDINARY_STORAGE = {
    "CLOUD_NAME": CLOUDINARY_CLOUD_NAME,
    "API_KEY": CLOUDINARY_API_KEY,
    "API_SECRET": CLOUDINARY_API_SECRET,

    # Organize uploaded PDFs in Cloudinary
    "FOLDER": "ai_pdf_chatbox",
}


# Validate Cloudinary credentials
if not all([
    CLOUDINARY_CLOUD_NAME,
    CLOUDINARY_API_KEY,
    CLOUDINARY_API_SECRET,
]):
    raise ValueError(
        "Cloudinary credentials are missing. "
        "Check CLOUDINARY_CLOUD_NAME, "
        "CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET."
    )


# Django 5.2 storage configuration
STORAGES = {

    "default": {
        "BACKEND": "cloudinary_storage.storage.RawMediaCloudinaryStorage",
    },

    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },

}


# ==================================================
# 14. DEFAULT PRIMARY KEY
# ==================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ==================================================
# 15. GROQ AI CONFIGURATION
# ==================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("[WARNING] GROQ_API_KEY is missing.")


# ==================================================
# 16. RENDER HTTPS CONFIGURATION
# ==================================================

# Render runs behind a reverse proxy.
SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

# Redirect HTTP requests to HTTPS in production.
SECURE_SSL_REDIRECT = not DEBUG


# ==================================================
# 17. LOGGING CONFIGURATION
# ==================================================

LOGGING = {

    "version": 1,

    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": (
                "[{levelname}] "
                "{asctime} "
                "{name}: "
                "{message}"
            ),
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },

    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },

    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


# ==================================================
# 18. FINAL SETTINGS DEBUG INFORMATION
# ==================================================

print("\n========== DJANGO SETTINGS LOADED ==========")

print("[CONFIG] DEBUG:", DEBUG)

print("[CONFIG] ALLOWED_HOSTS:", ALLOWED_HOSTS)

print("[CONFIG] CORS ORIGINS:", CORS_ALLOWED_ORIGINS)

print("[CONFIG] Database configured:", bool(DATABASE_URL))

print("[CONFIG] Cloudinary configured:", bool(CLOUDINARY_CLOUD_NAME))

print("[CONFIG] Default storage: Cloudinary Raw Media")

print("[CONFIG] HTTPS redirect:", SECURE_SSL_REDIRECT)

print("========== SETTINGS READY ==========\n")
