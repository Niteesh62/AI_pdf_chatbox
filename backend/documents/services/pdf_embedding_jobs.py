"""Background-thread launcher for PDF embedding ingestion.

Note: ThreadPoolExecutor jobs are in-process and are not durable across Render
restarts/deploys. Use a dedicated worker/queue for guaranteed production jobs.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections, connections
from django.utils import timezone

from config.runtime_diagnostics import log_runtime_stage

from ..models import PDFDocument
from .pdf_embedding_service import PDFIngestionError, create_pdf_embeddings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="pdf-embedding",
)


def _set_embedding_status(document_id, status):
    updated = PDFDocument.objects.filter(pk=document_id).update(
        embedding_status=status,
        updated_at=timezone.now(),
    )
    if updated != 1:
        raise PDFDocument.DoesNotExist(
            f"PDFDocument {document_id} was not found while updating embedding status."
        )

    logger.info(
        "PDF embedding status updated | document_id=%s | status=%s",
        document_id,
        status,
    )


def _mark_embedding_failed(document_id):
    try:
        _set_embedding_status(
            document_id,
            PDFDocument.EmbeddingStatus.FAILED,
        )
    except Exception:
        logger.exception(
            "Could not persist failed PDF embedding status | document_id=%s",
            document_id,
        )


def run_pdf_embedding_job(document_id):
    """Load a PDF document and run ingestion in a worker thread."""
    close_old_connections()
    stage = "load_document"
    pdf_document = None

    logger.info(
        "PDF embedding job started | document_id=%s | status=started",
        document_id,
    )

    try:
        pdf_document = PDFDocument.objects.get(pk=document_id)
        _set_embedding_status(
            document_id,
            PDFDocument.EmbeddingStatus.PROCESSING,
        )
        logger.info(
            "PDF embedding job loaded document | document_id=%s",
            document_id,
        )

        stage = "ingestion"
        with log_runtime_stage(
            logger,
            "pdf_processing",
            document_id=document_id,
        ):
            result = create_pdf_embeddings(pdf_document)

        total_chunks = result.get("total_chunks")
        stored_chunks = result.get("stored_chunks")
        if (
            result.get("status") != "success"
            or not isinstance(total_chunks, int)
            or total_chunks < 1
            or stored_chunks != total_chunks
        ):
            raise RuntimeError(
                "Embedding ingestion returned without verified vectors: "
                f"status={result.get('status')!r}, "
                f"chunks={total_chunks!r}, stored={stored_chunks!r}."
            )

        _set_embedding_status(
            document_id,
            PDFDocument.EmbeddingStatus.COMPLETED,
        )
        logger.info(
            "PDF embedding job completed | document_id=%s | status=completed | "
            "ingestion_status=%s | "
            "pages=%s | chunks=%s | stored_chunks=%s",
            document_id,
            result.get("status"),
            result.get("total_pages"),
            result.get("total_chunks"),
            result.get("stored_chunks"),
        )
        return result

    except PDFDocument.DoesNotExist:
        logger.exception(
            "PDF embedding job failed | status=failed | reason=document_missing "
            "| document_id=%s | stage=%s",
            document_id,
            stage,
        )
        if pdf_document is not None:
            _mark_embedding_failed(document_id)
        raise

    except PDFIngestionError as exc:
        logger.exception(
            "PDF embedding job failed | status=failed | document_id=%s | stage=%s | "
            "cause_type=%s | cause=%s",
            document_id,
            exc.stage,
            type(exc.cause).__name__,
            exc.cause,
        )
        _mark_embedding_failed(document_id)
        raise

    except Exception:
        logger.exception(
            "PDF embedding job failed unexpectedly | status=failed "
            "| document_id=%s | stage=%s",
            document_id,
            stage,
        )
        if pdf_document is not None:
            _mark_embedding_failed(document_id)
        raise

    finally:
        # Django DB connections are thread-local; close them in this worker.
        connections.close_all()
        logger.info(
            "PDF embedding worker database connections closed | document_id=%s",
            document_id,
        )


def enqueue_pdf_embedding(document_id):
    """Queue a job and return its Future to the caller."""
    try:
        future = _executor.submit(run_pdf_embedding_job, document_id)
        logger.info(
            "PDF embedding job queued | document_id=%s",
            document_id,
        )
        return future
    except Exception:
        logger.exception(
            "Unable to enqueue PDF embedding job | document_id=%s",
            document_id,
        )
        _mark_embedding_failed(document_id)
        raise
