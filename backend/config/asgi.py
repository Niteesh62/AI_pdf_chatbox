"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from config.runtime_diagnostics import RedactingFormatter

_startup_handler = logging.StreamHandler()
_startup_handler.setFormatter(
    RedactingFormatter("[{levelname}] {asctime} {name}: {message}", style="{")
)
logging.basicConfig(level=logging.INFO, handlers=[_startup_handler])
logger = logging.getLogger(__name__)
logger.info("django_startup_begin | interface=ASGI | port_configured=%s", bool(os.environ.get("PORT")))

from django.core.asgi import get_asgi_application


try:
    application = get_asgi_application()
except Exception:
    logger.exception("django_startup_failed | interface=ASGI")
    raise

logger.info("django_initialization_succeeded | interface=ASGI")


def _check_startup_services():
    from documents.startup_checks import check_external_services

    check_external_services()


_check_startup_services()
