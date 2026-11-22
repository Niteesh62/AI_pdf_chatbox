import logging
import os
import time

from .runtime_diagnostics import process_rss_mb


logger = logging.getLogger(__name__)


class RequestDiagnosticsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = time.perf_counter()
        cpu_started_at = time.process_time()
        rss_before_mb = process_rss_mb()

        try:
            response = self.get_response(request)
        except Exception:
            logger.exception(
                "http_request_failed | method=%s | path=%s | elapsed_seconds=%.3f",
                request.method,
                request.path_info,
                time.perf_counter() - started_at,
            )
            raise

        elapsed_seconds = time.perf_counter() - started_at
        cpu_seconds = time.process_time() - cpu_started_at
        cpu_percent = (
            round(cpu_seconds / elapsed_seconds * 100, 1)
            if elapsed_seconds > 0
            else 0
        )
        rss_after_mb = process_rss_mb()
        rss_delta_mb = (
            round(rss_after_mb - rss_before_mb, 1)
            if rss_before_mb is not None and rss_after_mb is not None
            else "unavailable"
        )
        status_code = response.status_code
        log_level = (
            logging.ERROR
            if status_code >= 500
            else logging.WARNING
            if status_code >= 400
            else logging.INFO
        )

        logger.log(
            log_level,
            "http_request | method=%s | path=%s | status=%s | "
            "elapsed_seconds=%.3f | cpu_seconds=%.3f | "
            "process_cpu_percent=%.1f | rss_before_mb=%s | "
            "rss_after_mb=%s | rss_delta_mb=%s | pid=%s",
            request.method,
            request.path_info,
            status_code,
            elapsed_seconds,
            cpu_seconds,
            cpu_percent,
            rss_before_mb if rss_before_mb is not None else "unavailable",
            rss_after_mb if rss_after_mb is not None else "unavailable",
            rss_delta_mb,
            os.getpid(),
        )
        return response
