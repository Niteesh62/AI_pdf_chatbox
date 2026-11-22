
"""
WSGI config for config project.
"""

import logging
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from config.runtime_diagnostics import RedactingFormatter, log_process_metrics

_startup_handler = logging.StreamHandler()
_startup_handler.setFormatter(
    RedactingFormatter("[{levelname}] {asctime} {name}: {message}", style="{")
)
logging.basicConfig(level=logging.INFO, handlers=[_startup_handler])
logger = logging.getLogger(__name__)

logger.info(
    "django_startup_begin | interface=WSGI | pid=%s | port_configured=%s",
    os.getpid(),
    bool(os.environ.get("PORT")),
)

environment_variables = (
    "SECRET_KEY",
    "DATABASE_URL",
    "GROQ_API_KEY",
    "CLOUDINARY_CLOUD_NAME",
    "CLOUDINARY_API_KEY",
    "CLOUDINARY_API_SECRET",
)
for variable in environment_variables:
    logger.info(
        "environment_configuration | variable=%s | status=%s",
        variable,
        "configured" if os.environ.get(variable) else "missing",
    )

try:
    from django.core.wsgi import get_wsgi_application

    from django.conf import settings
    from django.db import connections

    from config.runtime_diagnostics import log_runtime_stage

    with log_runtime_stage(logger, "django_initialization", interface="WSGI"):
        application = get_wsgi_application()

    logger.info(
        "django_initialization_succeeded | interface=WSGI | root_urlconf=%s",
        settings.ROOT_URLCONF,
    )

    if settings.DEBUG:
        logger.warning("django_debug_enabled | production_should_use_debug_false")

    logger.info(
        "django_root_urlconf_configured | root_urlconf=%s",
        settings.ROOT_URLCONF,
    )

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        logger.exception("startup_database_check_failed | status=unavailable")
    else:
        logger.info("startup_database_check_succeeded | status=connected")

    log_process_metrics(logger, "django_startup_complete")
except Exception:
    logger.exception("django_startup_failed | interface=WSGI")
    raise
