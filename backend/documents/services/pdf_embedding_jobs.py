import logging
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections

from ..models import PDFDocument
from .pdf_embedding_service import PDFIngestionError, create_pdf_embeddings


logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="pdf-embedding",
)


def run_pdf_embedding_job(document_id):
    close_old_connections()
    stage = "load_document"

    try:
        print(
            f"[EMBEDDING JOB] document_id={document_id} status=started",
            flush=True,
        )
        logger.info(
            "PDF embedding job started | document_id=%s | status=started",
            document_id,
        )
        pdf_document = PDFDocument.objects.get(pk=document_id)
        stage = "embedding"
        result = create_pdf_embeddings(pdf_document)
    except PDFIngestionError as error:
        print(
            f"[EMBEDDING JOB] document_id={document_id} "
            f"status=failed stage={error.stage}",
            flush=True,
        )
        logger.exception(
            "PDF embedding job finished | document_id=%s | status=failed | stage=%s",
            document_id,
            error.stage,
        )
    except Exception:
        print(
            f"[EMBEDDING JOB] document_id={document_id} "
            f"status=failed stage={stage}",
            flush=True,
        )
        logger.exception(
            "PDF embedding job finished | document_id=%s | status=failed | stage=%s",
            document_id,
            stage,
        )
    else:
        print(
            f"[EMBEDDING JOB] document_id={document_id} "
            f"status=completed pages={result.get('total_pages')} "
            f"chunks={result.get('total_chunks')}",
            flush=True,
        )
        logger.info(
            "PDF embedding job finished | document_id=%s | status=completed | pages=%s | chunks=%s",
            document_id,
            result.get("total_pages"),
            result.get("total_chunks"),
        )
    finally:
        close_old_connections()


def enqueue_pdf_embedding(document_id):
    return _executor.submit(run_pdf_embedding_job, document_id)
