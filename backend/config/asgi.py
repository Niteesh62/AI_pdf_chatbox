"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import logging
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from config.logging_config import configure_logging

configure_logging()
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
