import logging
import os

import cloudinary.api
from django.db import connections


logger = logging.getLogger(__name__)


def _redact(value):
    reason = str(value)
    for name in (
        "DATABASE_URL",
        "GROQ_API_KEY",
        "CLOUDINARY_CLOUD_NAME",
        "CLOUDINARY_API_KEY",
        "CLOUDINARY_API_SECRET",
        "CLOUDINARY_URL",
    ):
        value = os.getenv(name)
        if value:
            reason = reason.replace(value, "[REDACTED]")

    return reason


def _safe_error(error):
    return f"{type(error).__name__}: {_redact(error)}"


def check_external_services():
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception as error:
        reason = _safe_error(error)
        print(f"[startup] Database connection FAILED: {reason}", flush=True)
        logger.error("Database connection failed: %s", reason)
    else:
        print("[startup] Database connection OK", flush=True)
        logger.info("Database connection established")

    try:
        result = cloudinary.api.ping(timeout=10)
        if result.get("status") != "ok":
            reason = _redact(
                result.get("error")
                or result.get("message")
                or result.get("status")
                or "unexpected ping response"
            )
            print(
                f"[startup] Cloudinary connection FAILED: {reason}",
                flush=True,
            )
            logger.error("Cloudinary connection failed: %s", reason)
        else:
            print("[startup] Cloudinary connection OK", flush=True)
            logger.info("Cloudinary connection established")
    except Exception as error:
        reason = _safe_error(error)
        print(f"[startup] Cloudinary connection FAILED: {reason}", flush=True)
        logger.error("Cloudinary connection failed: %s", reason)
