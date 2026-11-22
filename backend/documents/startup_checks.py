import logging

import cloudinary
import cloudinary.api
from django.conf import settings
from django.db import connections


logger = logging.getLogger(__name__)


def check_external_services():
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        logger.exception("startup_database_check_failed | status=unavailable")
    else:
        logger.info("startup_database_check_succeeded | status=connected")

    try:
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )
        result = cloudinary.api.ping(timeout=10)
        if result.get("status") != "ok":
            logger.error(
                "startup_cloudinary_check_failed | status=%s",
                result.get("status", "unexpected"),
            )
        else:
            logger.info("Cloudinary connection established")
    except Exception:
        logger.exception("startup_cloudinary_check_failed | status=unavailable")
