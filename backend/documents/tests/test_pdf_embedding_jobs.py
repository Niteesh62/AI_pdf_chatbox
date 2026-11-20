from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from documents.services.pdf_embedding_jobs import run_pdf_embedding_job
from documents.services.pdf_embedding_service import PDFIngestionError
from documents.views import PDFDocumentViewSet


class PDFEmbeddingJobTests(SimpleTestCase):

    @patch("documents.views.enqueue_pdf_embedding")
    @patch("documents.views.PDFDocumentSerializer")
    def test_upload_returns_accepted_after_queueing(
        self,
        serialized_document,
        enqueue_job,
    ):
        view = PDFDocumentViewSet()
        serializer = SimpleNamespace(
            is_valid=lambda **kwargs: None,
            save=lambda: SimpleNamespace(id=42, title="sample.pdf"),
        )
        view.get_serializer = lambda **kwargs: serializer
        serialized_document.return_value.data = {"id": 42}

        request = SimpleNamespace(data={})
        output = StringIO()
        with redirect_stdout(output):
            response = view.create(request)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["embedding_status"], "queued")
        self.assertEqual(response.data["document"], {"id": 42})
        enqueue_job.assert_called_once_with(42)
        self.assertIn("status=queued", output.getvalue())

    @patch("documents.services.pdf_embedding_jobs.close_old_connections")
    @patch("documents.services.pdf_embedding_jobs.PDFDocument.objects.get")
    @patch("documents.services.pdf_embedding_jobs.create_pdf_embeddings")
    def test_logs_completed_job(
        self,
        create_embeddings,
        get_document,
        close_connections,
    ):
        get_document.return_value = SimpleNamespace(id=42)
        create_embeddings.return_value = {
            "total_pages": 3,
            "total_chunks": 8,
        }

        output = StringIO()
        with self.assertLogs(
            "documents.services.pdf_embedding_jobs",
            level="INFO",
        ) as captured, redirect_stdout(output):
            run_pdf_embedding_job(42)

        messages = "\n".join(captured.output)
        self.assertIn("status=started", messages)
        self.assertIn("status=completed", messages)
        self.assertIn("document_id=42", messages)
        self.assertIn("status=started", output.getvalue())
        self.assertIn("status=completed", output.getvalue())
        self.assertEqual(close_connections.call_count, 2)

    @patch("documents.services.pdf_embedding_jobs.close_old_connections")
    @patch("documents.services.pdf_embedding_jobs.PDFDocument.objects.get")
    @patch("documents.services.pdf_embedding_jobs.create_pdf_embeddings")
    def test_logs_failed_job_stage(
        self,
        create_embeddings,
        get_document,
        close_connections,
    ):
        get_document.return_value = SimpleNamespace(id=42)
        create_embeddings.side_effect = PDFIngestionError(
            "embedding_generation_and_storage",
            ValueError("embedding service unavailable"),
        )

        output = StringIO()
        with self.assertLogs(
            "documents.services.pdf_embedding_jobs",
            level="ERROR",
        ) as captured, redirect_stdout(output):
            run_pdf_embedding_job(42)

        self.assertIn("status=failed", "\n".join(captured.output))
        self.assertIn(
            "stage=embedding_generation_and_storage",
            "\n".join(captured.output),
        )
        self.assertIn("status=failed", output.getvalue())
        self.assertIn(
            "stage=embedding_generation_and_storage",
            output.getvalue(),
        )
        self.assertEqual(close_connections.call_count, 2)
