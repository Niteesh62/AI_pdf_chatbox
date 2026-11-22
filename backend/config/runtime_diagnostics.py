import logging
import os
import re
import sys
import time
import traceback
from contextlib import contextmanager


_SECRET_ENVIRONMENT_VARIABLES = (
    "SECRET_KEY",
    "DATABASE_URL",
    "GROQ_API_KEY",
    "CLOUDINARY_API_KEY",
    "CLOUDINARY_API_SECRET",
    "CLOUDINARY_URL",
)

_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key)\b(\s*[:=]\s*)"
    r"(['\"]?)[^\s,;'\"]+"
)
_AUTHORIZATION_PATTERN = re.compile(
    r"(?i)\b(authorization|proxy-authorization)\b(\s*:\s*)"
    r"(?:bearer\s+)?[^\s,;]+"
)


def redact_secrets(value):
    """Redact configured secrets and common credential-shaped log values."""
    text = str(value)
    for name in _SECRET_ENVIRONMENT_VARIABLES:
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")

    text = _SECRET_PATTERN.sub(r"\1\2[REDACTED]", text)
    return _AUTHORIZATION_PATTERN.sub(r"\1\2[REDACTED]", text)


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact_secrets(super().format(record))

    def formatException(self, exc_info):
        return redact_secrets(
            "".join(traceback.format_exception(*exc_info))
        )


def process_rss_mb():
    try:
        with open("/proc/self/status", encoding="ascii") as status_file:
            for line in status_file:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        return None
    return None


def log_process_metrics(logger, event, **fields):
    rss_mb = process_rss_mb()
    details = " ".join(
        f"{key}={value}" for key, value in fields.items()
    )
    logger.info(
        "process_metrics | event=%s | pid=%s | rss_mb=%s | cpu_time_seconds=%.3f%s",
        event,
        os.getpid(),
        rss_mb if rss_mb is not None else "unavailable",
        time.process_time(),
        f" | {details}" if details else "",
    )


@contextmanager
def log_runtime_stage(logger, stage, **fields):
    started_at = time.perf_counter()
    cpu_started_at = time.process_time()
    rss_before_mb = process_rss_mb()
    details = " ".join(
        f"{key}={value}" for key, value in fields.items()
    )
    logger.info(
        "runtime_stage_started | stage=%s | pid=%s | rss_mb=%s%s",
        stage,
        os.getpid(),
        rss_before_mb if rss_before_mb is not None else "unavailable",
        f" | {details}" if details else "",
    )

    try:
        yield
    finally:
        elapsed_seconds = time.perf_counter() - started_at
        cpu_seconds = time.process_time() - cpu_started_at
        rss_after_mb = process_rss_mb()
        rss_delta_mb = (
            round(rss_after_mb - rss_before_mb, 1)
            if rss_before_mb is not None and rss_after_mb is not None
            else "unavailable"
        )
        status = "failed" if sys.exc_info()[0] else "completed"
        cpu_percent = (
            round(cpu_seconds / elapsed_seconds * 100, 1)
            if elapsed_seconds > 0
            else 0
        )
        logger.info(
            "runtime_stage_finished | stage=%s | status=%s | elapsed_seconds=%.3f "
            "| cpu_seconds=%.3f | process_cpu_percent=%.1f | "
            "rss_before_mb=%s | rss_after_mb=%s | rss_delta_mb=%s%s",
            stage,
            status,
            elapsed_seconds,
            cpu_seconds,
            cpu_percent,
            rss_before_mb if rss_before_mb is not None else "unavailable",
            rss_after_mb if rss_after_mb is not None else "unavailable",
            rss_delta_mb,
            f" | {details}" if details else "",
        )
