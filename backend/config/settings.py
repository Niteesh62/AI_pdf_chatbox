
"""
Django settings for config project.
Local development: Django + Supabase PostgreSQL + Cloudinary
Production: Render + Supabase PostgreSQL + Cloudinary
"""

import os
from pathlib import Path

import cloudinary
import dj_database_url
from dotenv import load_dotenv


# ==================================================
# 1. BASE CONFIGURATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_FILE = BASE_DIR / ".env"

# Load local environment variables
load_dotenv(ENV_FILE, override=True)


def get_env(name, default=""):
    """Read environment variables safely."""
    return os.getenv(name, default).strip()


DEBUG = get_env("DEBUG", "False").lower() == "true"

SECRET_KEY = get_env(
    "SECRET_KEY",
    "django-insecure-local-development-key"
)

if not DEBUG and (
    not SECRET_KEY
    or SECRET_KEY == "django-insecure-local-development-key"
):
    raise ValueError(
        "Set a secure SECRET_KEY in production environment variables."
    )


# ==================================================
# 2. ENVIRONMENT VARIABLE CHECK
# ==================================================

REQUIRED_ENVIRONMENT_VARIABLES = [
    "SECRET_KEY",
    "GROQ_API_KEY",
    "CLOUDINARY_CLOUD_NAME",
    "CLOUDINARY_API_KEY",
    "CLOUDINARY_API_SECRET",
]

print("\n========== ENVIRONMENT CHECK ==========")

for variable in REQUIRED_ENVIRONMENT_VARIABLES:
    value = get_env(variable)
    print(
        f"[CONFIG] {variable}: "
        f"{'CONFIGURED' if value else 'MISSING'}",
        flush=True
    )

print("=======================================\n")


# ==================================================
# 3. ALLOWED HOSTS
# ==================================================

ALLOWED_HOSTS = [
    host.strip()
    for host in get_env(
        "ALLOWED_HOSTS",
        "localhost,127.0.0.1,.onrender.com"
    ).split(",")
    if host.strip()
]


# ==================================================
# 4. CORS AND CSRF
# ==================================================

CORS_ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in get_env(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in get_env(
        "CSRF_TRUSTED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,https://ai-pdf-chatbox-mxdw.onrender.com"
    ).split(",")
    if origin.strip()
]

CORS_URLS_REGEX = r"^/api/.*$"

CORS_ALLOW_CREDENTIALS = False


# ==================================================
# 5. INSTALLED APPS
# ==================================================

INSTALLED_APPS = [

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",
    "corsheaders",

    "cloudinary",
    "cloudinary_storage",

    "documents.apps.DocumentsConfig",
]


# ==================================================
# 6. MIDDLEWARE
# ==================================================

MIDDLEWARE = [

    "corsheaders.middleware.CorsMiddleware",

    "django.middleware.security.SecurityMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",

    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ==================================================
# 7. URL CONFIGURATION
# ==================================================

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"


# ==================================================
# 8. TEMPLATES
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
# 9. DATABASE CONFIGURATION
# ==================================================

DATABASE_URL = get_env("DATABASE_URL")

if DATABASE_URL:

    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True,
        )
    }

elif DEBUG:

    # Local fallback when DATABASE_URL is not configured
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

else:

    raise ValueError(
        "DATABASE_URL is required in production."
    )


# ==================================================
# 10. PASSWORD VALIDATION
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
# 11. INTERNATIONALIZATION
# ==================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# ==================================================
# 12. STATIC FILES
# ==================================================

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"


# ==================================================
# 13. MEDIA FILES
# ==================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024


# ==================================================
# 14. CLOUDINARY CONFIGURATION
# ==================================================

CLOUDINARY_CLOUD_NAME = get_env("CLOUDINARY_CLOUD_NAME")

CLOUDINARY_API_KEY = get_env("CLOUDINARY_API_KEY")

CLOUDINARY_API_SECRET = get_env("CLOUDINARY_API_SECRET")


# Validate Cloudinary credentials

if not all([
    CLOUDINARY_CLOUD_NAME,
    CLOUDINARY_API_KEY,
    CLOUDINARY_API_SECRET,
]):

    raise ValueError(
        "Cloudinary credentials are missing. "
        "Check your backend .env file."
    )


# Explicitly initialize Cloudinary SDK

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True,
)


# Django Cloudinary Storage Configuration

CLOUDINARY_STORAGE = {

    "CLOUD_NAME": CLOUDINARY_CLOUD_NAME,

    "API_KEY": CLOUDINARY_API_KEY,

    "API_SECRET": CLOUDINARY_API_SECRET,

    "FOLDER": "ai_pdf_chatbox",

}


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
# 15. DEFAULT PRIMARY KEY
# ==================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ==================================================
# 16. GROQ AI CONFIGURATION
# ==================================================

GROQ_API_KEY = get_env("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("[WARNING] GROQ_API_KEY is missing.")


# ==================================================
# 17. RENDER HTTPS CONFIGURATION
# ==================================================

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

SECURE_SSL_REDIRECT = get_env(
    "SECURE_SSL_REDIRECT",
    str(not DEBUG),
).lower() == "true"


# ==================================================
# 18. LOGGING CONFIGURATION
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
# 19. FINAL CONFIGURATION INFORMATION
# ==================================================

print("\n========== DJANGO SETTINGS LOADED ==========")

print("[CONFIG] DEBUG:", DEBUG)

print("[CONFIG] DATABASE:", "PostgreSQL" if DATABASE_URL else "SQLite")

print("[CONFIG] Cloudinary Cloud:", CLOUDINARY_CLOUD_NAME)

print(
    "[CONFIG] Cloudinary API Key Last 4:",
    CLOUDINARY_API_KEY[-4:]
)

print("[CONFIG] Cloudinary SDK initialized:", True)

print("[CONFIG] Default Storage: Cloudinary Raw Media")

print("[CONFIG] HTTPS Redirect:", SECURE_SSL_REDIRECT)

print("========== SETTINGS READY ==========\n")
