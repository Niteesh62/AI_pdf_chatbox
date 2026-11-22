import logging
import os

from config.runtime_diagnostics import log_process_metrics


logger = logging.getLogger("gunicorn.error")
host = "0.0.0.0"
port_value = os.environ.get("PORT")
port_source = "environment"

if not port_value:
    port_value = "10000"
    port_source = "default"

try:
    port = int(port_value)
except ValueError as error:
    raise ValueError("PORT must be a valid integer.") from error

if not 1 <= port <= 65535:
    raise ValueError("PORT must be between 1 and 65535.")

bind = f"{host}:{port}"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "180"))
graceful_timeout = 30
worker_class = "sync"
errorlog = "-"
capture_output = True


def on_starting(_server):
    logger.info(
        "gunicorn_starting | bind_host=%s | bind_port=%s | port_source=%s "
        "| workers=%s | timeout_seconds=%s",
        host,
        port,
        port_source,
        workers,
        timeout,
    )


def when_ready(server):
    logger.info(
        "gunicorn_master_ready | bind=%s | listening_sockets=%s",
        bind,
        len(server.LISTENERS),
    )


def post_fork(_server, worker):
    logger.info(
        "gunicorn_worker_forked | pid=%s | worker=%s",
        worker.pid,
        worker.__class__.__name__,
    )


def post_worker_init(worker):
    logger.info("gunicorn_worker_initialized | pid=%s", worker.pid)
    log_process_metrics(logger, "gunicorn_worker_initialized")


def worker_abort(worker):
    logger.error("gunicorn_worker_abort | pid=%s", worker.pid)


def worker_int(worker):
    logger.warning("gunicorn_worker_interrupt | pid=%s", worker.pid)


def worker_exit(_server, worker):
    logger.warning("gunicorn_worker_exiting | pid=%s", worker.pid)


def child_exit(_server, worker):
    logger.warning(
        "gunicorn_worker_process_exited | pid=%s | exit_code=%s",
        worker.pid,
        getattr(worker, "exitcode", "unavailable"),
    )


def on_reload(_server):
    logger.info("gunicorn_reload_requested")


def on_exit(_server):
    logger.info("gunicorn_master_exiting")
