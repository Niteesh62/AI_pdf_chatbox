import sys
import types
from unittest.mock import Mock, call, patch

import numpy
from django.test import SimpleTestCase

from documents.models import PDFDocument
from documents.services import llm_embedding, pdf_embedding_jobs
from documents.services.pdf_embedding_service import PDFIngestionError


class SharedEmbeddingModelTests(SimpleTestCase):
    def test_model_is_loaded_once_and_used_for_normalized_vectors(self):
        model = Mock()
        model.get_embedding_dimension.return_value = 384
        model.encode.side_effect = lambda texts, **kwargs: numpy.zeros(
            (len(texts), 384),
            dtype="float32",
        )
        constructor = Mock(return_value=model)
        sentence_transformers = types.ModuleType("sentence_transformers")
        sentence_transformers.SentenceTransformer = constructor
        torch = types.ModuleType("torch")
        torch.float16 = object()
        torch.set_num_threads = Mock()

        with (
            patch.multiple(
                llm_embedding,
                _embedding_model=None,
                _embedding_dimension=None,
            ),
            patch.dict(
                sys.modules,
                {"sentence_transformers": sentence_transformers, "torch": torch},
            ),
        ):
            cached_model, dimension = llm_embedding.get_embedding_model()
            vectors = llm_embedding.encode_texts(
                ["chunk one", "chunk two"],
                batch_size=8,
                stage="test_embedding",
                document_id=17,
            )
            llm_embedding.get_embedding_model()

        self.assertIs(cached_model, model)
        self.assertEqual(dimension, 384)
        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(vectors[0]), 384)
        constructor.assert_called_once_with(
            llm_embedding.EMBEDDING_MODEL_NAME,
            device="cpu",
            model_kwargs={
                "low_cpu_mem_usage": True,
                "torch_dtype": torch.float16,
            },
        )
        model.encode.assert_called_once_with(
            ["chunk one", "chunk two"],
            batch_size=2,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        torch.set_num_threads.assert_called_once_with(1)

    def test_chat_llm_client_is_cached(self):
        client = Mock()
        constructor = Mock(return_value=client)
        langchain_groq = types.ModuleType("langchain_groq")
        langchain_groq.ChatGroq = constructor

        with (
            patch.object(llm_embedding, "_chat_llm", None),
            patch.object(llm_embedding.settings, "GROQ_API_KEY", "test-key"),
            patch.dict(sys.modules, {"langchain_groq": langchain_groq}),
        ):
            first_client = llm_embedding.get_chat_llm()
            second_client = llm_embedding.get_chat_llm()

        self.assertIs(first_client, client)
        self.assertIs(second_client, client)
        constructor.assert_called_once_with(
            model="openai/gpt-oss-20b",
            temperature=0,
            api_key="test-key",
            max_retries=2,
            timeout=60,
        )


class PdfEmbeddingJobStatusTests(SimpleTestCase):
    def setUp(self):
        self.pdf_document = types.SimpleNamespace(
            pk=17,
            extracted_text="saved extracted text",
        )
        self.get_document = patch.object(
            PDFDocument.objects,
            "get",
            return_value=self.pdf_document,
        )
        self.set_status = patch.object(pdf_embedding_jobs, "_set_embedding_status")
        self.close_old_connections = patch.object(
            pdf_embedding_jobs,
            "close_old_connections",
        )
        self.close_all_connections = patch.object(
            pdf_embedding_jobs.connections,
            "close_all",
        )
        self.get_document.start()
        self.addCleanup(self.get_document.stop)
        self.set_status_mock = self.set_status.start()
        self.addCleanup(self.set_status.stop)
        self.close_old_connections.start()
        self.addCleanup(self.close_old_connections.stop)
        self.close_all_connections.start()
        self.addCleanup(self.close_all_connections.stop)

    def test_job_completes_only_after_all_vectors_are_verified(self):
        result = {
            "status": "success",
            "total_chunks": 2,
            "stored_chunks": 2,
        }
        with patch.object(
            pdf_embedding_jobs,
            "create_pdf_embeddings",
            return_value=result,
        ):
            returned = pdf_embedding_jobs.run_pdf_embedding_job(17)

        self.assertIs(returned, result)
        self.assertEqual(
            self.set_status_mock.call_args_list,
            [
                call(17, PDFDocument.EmbeddingStatus.PROCESSING),
                call(17, PDFDocument.EmbeddingStatus.COMPLETED),
            ],
        )

    def test_failed_job_records_failure_and_preserves_extracted_text(self):
        error = PDFIngestionError("embedding_model", RuntimeError("load failed"))
        with patch.object(
            pdf_embedding_jobs,
            "create_pdf_embeddings",
            side_effect=error,
        ):
            with self.assertRaises(PDFIngestionError):
                pdf_embedding_jobs.run_pdf_embedding_job(17)

        self.assertEqual(
            self.set_status_mock.call_args_list,
            [
                call(17, PDFDocument.EmbeddingStatus.PROCESSING),
                call(17, PDFDocument.EmbeddingStatus.FAILED),
            ],
        )
        self.assertEqual(self.pdf_document.extracted_text, "saved extracted text")

    def test_incomplete_embedding_result_is_not_marked_completed(self):
        result = {
            "status": "success",
            "total_chunks": 2,
            "stored_chunks": 1,
        }
        with patch.object(
            pdf_embedding_jobs,
            "create_pdf_embeddings",
            return_value=result,
        ):
            with self.assertRaises(RuntimeError):
                pdf_embedding_jobs.run_pdf_embedding_job(17)

        self.assertEqual(
            self.set_status_mock.call_args_list,
            [
                call(17, PDFDocument.EmbeddingStatus.PROCESSING),
                call(17, PDFDocument.EmbeddingStatus.FAILED),
            ],
        )
