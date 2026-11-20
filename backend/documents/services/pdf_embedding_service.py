"""PDF text extraction and pgvector ingestion for Django + Supabase PostgreSQL.

This implementation uses the existing table layout:
    id, document_id, content, metadata (jsonb), embedding (vector(384))

It intentionally uses Django's configured PostgreSQL connection instead of
LangChain PGVectorStore, so it does not expect a different set of columns.
"""

import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from typing import Any

from django.conf import settings
from django.db import connection, transaction
from langchain_community.document_loaders import PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

VECTOR_SCHEMA_NAME = "public"
VECTOR_TABLE_NAME = "pdf_document_embeddings"
EMBEDDING_MODEL_NAME = os.getenv(
    "HF_EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)
EXPECTED_VECTOR_SIZE = 384
EMBEDDING_BATCH_SIZE = 64

_embedding_model = None
_embedding_dimension = None
_embedding_lock = threading.Lock()


class PDFIngestionError(Exception):
    """An ingestion failure annotated with the pipeline stage."""

    def __init__(self, stage: str, cause: Exception):
        self.stage = stage
        self.cause = cause
        super().__init__(f"PDF ingestion failed at stage '{stage}': {cause}")


def _log_stage(stage: str, message: str, *, document_id: Any = None, **extra):
    details = {"stage": stage, **extra}
    if document_id is not None:
        details["document_id"] = document_id
    logger.info("%s | %s", message, " | ".join(f"{k}={v}" for k, v in details.items()))


def clean_pdf_text(text: str) -> str:
    """Remove NULL and disallowed control characters before DB storage."""
    if not text:
        return ""

    original_length = len(text)
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F]", "", text)
    cleaned = text.strip()
    removed = original_length - len(cleaned)

    if removed:
        logger.debug(
            "PDF text cleaned | original_chars=%s | cleaned_chars=%s | removed_or_trimmed=%s",
            original_length,
            len(cleaned),
            removed,
        )
    return cleaned


def get_embedding_model():
    """Load the Hugging Face model once per worker process."""
    global _embedding_model, _embedding_dimension

    if _embedding_model is not None:
        return _embedding_model, _embedding_dimension

    with _embedding_lock:
        if _embedding_model is not None:
            return _embedding_model, _embedding_dimension

        started = time.monotonic()
        logger.info("Loading embedding model | model=%s | device=cpu", EMBEDDING_MODEL_NAME)
        try:
            model = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL_NAME,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
            probe = model.embed_query("PDF embedding model dimension check")
            dimension = len(probe)

            if dimension != EXPECTED_VECTOR_SIZE:
                raise ValueError(
                    f"Embedding model returned {dimension} dimensions; "
                    f"the configured Supabase vector column expects {EXPECTED_VECTOR_SIZE}."
                )

            _embedding_model = model
            _embedding_dimension = dimension
            logger.info(
                "Embedding model loaded | model=%s | dimensions=%s | elapsed_seconds=%.2f",
                EMBEDDING_MODEL_NAME,
                dimension,
                time.monotonic() - started,
            )
            return _embedding_model, _embedding_dimension
        except Exception:
            logger.exception("Embedding model initialization failed | model=%s", EMBEDDING_MODEL_NAME)
            raise


def _quoted_table_name() -> str:
    return (
        f"{connection.ops.quote_name(VECTOR_SCHEMA_NAME)}."
        f"{connection.ops.quote_name(VECTOR_TABLE_NAME)}"
    )


def ensure_vector_table(vector_size: int) -> str:
    """Ensure the expected table exists and validate its schema/dimension.

    Existing tables are never silently altered or dropped. An incompatible
    schema raises a clear error so existing user data is not destroyed.
    """
    if connection.vendor != "postgresql":
        raise RuntimeError(
            "Supabase pgvector requires PostgreSQL. Check Django DATABASES settings."
        )

    if int(vector_size) != EXPECTED_VECTOR_SIZE:
        raise ValueError(
            f"Expected {EXPECTED_VECTOR_SIZE}-dimensional embeddings, got {vector_size}."
        )

    schema = connection.ops.quote_name(VECTOR_SCHEMA_NAME)
    table = connection.ops.quote_name(VECTOR_TABLE_NAME)

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT namespace.nspname "
            "FROM pg_extension AS ext "
            "JOIN pg_namespace AS namespace ON namespace.oid = ext.extnamespace "
            "WHERE ext.extname = %s",
            ["vector"],
        )
        extension_row = cursor.fetchone()

        if not extension_row:
            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except Exception as exc:
                raise RuntimeError(
                    "The pgvector extension is not enabled and the database user "
                    "could not create it. Enable vector in Supabase Database > Extensions."
                ) from exc
            cursor.execute(
                "SELECT namespace.nspname "
                "FROM pg_extension AS ext "
                "JOIN pg_namespace AS namespace ON namespace.oid = ext.extnamespace "
                "WHERE ext.extname = %s",
                ["vector"],
            )
            extension_row = cursor.fetchone()

        if not extension_row:
            raise RuntimeError("pgvector extension is unavailable after initialization.")

        extension_schema = extension_row[0]
        vector_type = (
            f"{connection.ops.quote_name(extension_schema)}."
            f"{connection.ops.quote_name('vector')}({EXPECTED_VECTOR_SIZE})"
        )

        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {schema}.{table} (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                document_id BIGINT NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                embedding {vector_type} NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s",
            [VECTOR_SCHEMA_NAME, VECTOR_TABLE_NAME],
        )
        actual_columns = {row[0] for row in cursor.fetchall()}

        required_columns = {"id", "document_id", "content", "metadata", "embedding"}
        missing = required_columns - actual_columns
        if missing:
            raise RuntimeError(
                f"Table {VECTOR_SCHEMA_NAME}.{VECTOR_TABLE_NAME} has an incompatible schema. "
                f"Missing columns: {sorted(missing)}. Existing columns: {sorted(actual_columns)}. "
                "Back up existing data before applying a schema migration."
            )

        cursor.execute(
            "SELECT format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a "
            "JOIN pg_class c ON a.attrelid = c.oid "
            "JOIN pg_namespace n ON c.relnamespace = n.oid "
            "WHERE n.nspname = %s AND c.relname = %s AND a.attname = 'embedding' "
            "AND a.attnum > 0 AND NOT a.attisdropped",
            [VECTOR_SCHEMA_NAME, VECTOR_TABLE_NAME],
        )
        dimension_row = cursor.fetchone()
        actual_vector_type = dimension_row[0] if dimension_row else None

        if actual_vector_type != f"vector({EXPECTED_VECTOR_SIZE})":
            raise RuntimeError(
                f"The embedding column is {actual_vector_type!r}; expected "
                f"vector({EXPECTED_VECTOR_SIZE}). Do not drop a table containing data. "
                "Create a reviewed migration after backing up existing records."
            )

    logger.info(
        "Supabase pgvector table verified | table=%s.%s | vector_type=vector(%s)",
        VECTOR_SCHEMA_NAME,
        VECTOR_TABLE_NAME,
        vector_size,
    )
    return extension_schema


def _vector_literal(values) -> str:
    """Serialize numeric embedding values into pgvector's textual format."""
    if not values:
        raise ValueError("Embedding model returned an empty vector.")
    return "[" + ",".join(format(float(value), ".9g") for value in values) + "]"


def replace_document_embeddings(document_id: int, chunks, vectors) -> int:
    """Atomically replace all chunks for one document in the existing table."""
    if len(chunks) != len(vectors):
        raise ValueError(
            f"Chunk/vector count mismatch: {len(chunks)} chunks, {len(vectors)} vectors."
        )

    schema = connection.ops.quote_name(VECTOR_SCHEMA_NAME)
    table = connection.ops.quote_name(VECTOR_TABLE_NAME)
    extension_schema = ensure_vector_table(EXPECTED_VECTOR_SIZE)
    vector_cast = (
        f"{connection.ops.quote_name(extension_schema)}."
        f"{connection.ops.quote_name('vector')}"
    )

    insert_sql = f"""
        INSERT INTO {schema}.{table}
            (document_id, content, metadata, embedding)
        VALUES (%s, %s, %s::jsonb, %s::{vector_cast})
    """

    rows = []
    for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
        if len(vector) != EXPECTED_VECTOR_SIZE:
            raise ValueError(
                f"Chunk {index} has {len(vector)} vector dimensions; "
                f"expected {EXPECTED_VECTOR_SIZE}."
            )

        metadata = dict(chunk.metadata or {})
        metadata.update(
            {
                "document_id": int(document_id),
                "chunk_index": index,
            }
        )
        rows.append(
            (
                int(document_id),
                chunk.page_content,
                json.dumps(metadata, ensure_ascii=False, default=str),
                _vector_literal(vector),
            )
        )

    # Delete and insert in one transaction: a failed insert restores old rows.
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {schema}.{table} WHERE document_id = %s",
                [int(document_id)],
            )
            deleted_count = cursor.rowcount
            logger.info(
                "Old PDF embeddings removed inside replacement transaction | "
                "document_id=%s | deleted=%s",
                document_id,
                deleted_count,
            )

            if rows:
                cursor.executemany(insert_sql, rows)

            cursor.execute(
                f"SELECT COUNT(*), COUNT(embedding) FROM {schema}.{table} "
                "WHERE document_id = %s",
                [int(document_id)],
            )
            stored_count, non_null_count = cursor.fetchone()

            if stored_count != len(chunks) or non_null_count != len(chunks):
                raise RuntimeError(
                    "pgvector storage verification failed: "
                    f"expected={len(chunks)}, stored={stored_count}, "
                    f"non_null_embeddings={non_null_count}."
                )

    logger.info(
        "PDF embeddings committed and verified | document_id=%s | chunks=%s",
        document_id,
        stored_count,
    )
    return int(stored_count)


def count_document_embeddings(document_id: int) -> int:
    table = _quoted_table_name()
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*) FROM {table} WHERE document_id = %s",
            [int(document_id)],
        )
        row = cursor.fetchone()
    return int(row[0]) if row else 0


def create_pdf_embeddings(pdf_document):
    """Extract, split, embed, and store one uploaded PDF."""
    document_id = getattr(pdf_document, "pk", None)
    title = getattr(pdf_document, "title", "")
    stage = "initialization"
    started = time.monotonic()

    logger.info(
        "PDF ingestion started | document_id=%s | title=%s | table=%s.%s",
        document_id,
        title,
        VECTOR_SCHEMA_NAME,
        VECTOR_TABLE_NAME,
    )

    try:
        if not document_id:
            raise ValueError("PDFDocument must be saved before embedding ingestion.")
        if not getattr(pdf_document, "pdf_file", None):
            raise ValueError("PDFDocument does not contain an uploaded pdf_file.")

        # 1. Download/copy the stored PDF to a temporary local file.
        stage = "cloudinary_download"
        logger.info("PDF download started | document_id=%s", document_id)

        with tempfile.TemporaryDirectory(prefix="pdf-ingestion-") as temp_dir:
            pdf_path = os.path.join(temp_dir, "document.pdf")
            with pdf_document.pdf_file.open("rb") as stored_file:
                with open(pdf_path, "wb") as local_file:
                    shutil.copyfileobj(stored_file, local_file)

            file_size = os.path.getsize(pdf_path)
            if file_size < 5:
                raise ValueError(f"Downloaded PDF is empty or too small ({file_size} bytes).")

            with open(pdf_path, "rb") as check_file:
                header = check_file.read(5)
            if header != b"%PDF-":
                raise ValueError(
                    f"Downloaded file is not a valid PDF. Header={header!r}. "
                    "Check Cloudinary resource type and stored file URL."
                )

            logger.info(
                "PDF downloaded to temporary storage | document_id=%s | bytes=%s",
                document_id,
                file_size,
            )

            # 2. Parse PDF.
            stage = "pdf_parse"
            pages = PyPDFLoader(pdf_path).load()
            if not pages:
                raise ValueError("PDF parser returned no pages.")
            logger.info(
                "PDF parsed | document_id=%s | pages=%s",
                document_id,
                len(pages),
            )

            # 3. Clean extracted page text.
            stage = "text_extraction"
            for page_number, page in enumerate(pages, start=1):
                page.page_content = clean_pdf_text(page.page_content)
                logger.debug(
                    "PDF page extracted | document_id=%s | page=%s | chars=%s",
                    document_id,
                    page_number,
                    len(page.page_content),
                )

            extracted_text = clean_pdf_text(
                "\n\n".join(page.page_content for page in pages)
            )
            if not extracted_text:
                raise ValueError(
                    "No extractable text was found. This may be a scanned/image-only PDF; "
                    "OCR is required before embedding it."
                )

            # 4. Save extracted text in the Django document record.
            stage = "database_update"
            pdf_document.extracted_text = extracted_text
            pdf_document.save(update_fields=["extracted_text"])
            logger.info(
                "Extracted PDF text saved | document_id=%s | characters=%s",
                document_id,
                len(extracted_text),
            )

            # 5. Split into chunks.
            stage = "chunking"
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                length_function=len,
            )
            chunks = splitter.split_documents(pages)

            valid_chunks = []
            for chunk in chunks:
                chunk.page_content = clean_pdf_text(chunk.page_content)
                if chunk.page_content:
                    valid_chunks.append(chunk)

            if not valid_chunks:
                raise ValueError("Text splitter produced no non-empty chunks.")

            for index, chunk in enumerate(valid_chunks):
                chunk.metadata = dict(chunk.metadata or {})
                chunk.metadata.update(
                    {
                        "document_id": int(document_id),
                        "document_title": str(title),
                        "chunk_index": index,
                    }
                )

            logger.info(
                "PDF chunking completed | document_id=%s | chunks=%s | chunk_size=1000 | overlap=200",
                document_id,
                len(valid_chunks),
            )

        # 6. Load embedding model and generate vectors in manageable batches.
        stage = "embedding_model"
        embeddings, dimension = get_embedding_model()
        ensure_vector_table(dimension)

        stage = "embedding_generation"
        texts = [chunk.page_content for chunk in valid_chunks]
        vectors = []
        total_batches = (len(texts) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE

        logger.info(
            "Embedding generation started | document_id=%s | chunks=%s | batches=%s | dimensions=%s",
            document_id,
            len(texts),
            total_batches,
            dimension,
        )

        for batch_number, offset in enumerate(
            range(0, len(texts), EMBEDDING_BATCH_SIZE),
            start=1,
        ):
            batch_texts = texts[offset : offset + EMBEDDING_BATCH_SIZE]
            batch_vectors = embeddings.embed_documents(batch_texts)
            if len(batch_vectors) != len(batch_texts):
                raise RuntimeError(
                    f"Embedding batch {batch_number} returned {len(batch_vectors)} vectors "
                    f"for {len(batch_texts)} chunks."
                )
            for vector in batch_vectors:
                if len(vector) != dimension:
                    raise ValueError(
                        f"Embedding dimension mismatch in batch {batch_number}: "
                        f"got {len(vector)}, expected {dimension}."
                    )
            vectors.extend(batch_vectors)
            logger.info(
                "Embedding batch completed | document_id=%s | batch=%s/%s | vectors=%s",
                document_id,
                batch_number,
                total_batches,
                len(batch_vectors),
            )

        # 7. Atomically replace and verify records in Supabase.
        stage = "pgvector_storage"
        stored_count = replace_document_embeddings(
            document_id=document_id,
            chunks=valid_chunks,
            vectors=vectors,
        )

        # 8. Final independent count check.
        stage = "embedding_verification"
        verified_count = count_document_embeddings(document_id)
        if verified_count != len(valid_chunks):
            raise RuntimeError(
                f"Final verification mismatch: expected {len(valid_chunks)}, "
                f"found {verified_count} records for document {document_id}."
            )

        result = {
            "document_id": document_id,
            "total_pages": len(pages),
            "total_characters": len(extracted_text),
            "total_chunks": len(valid_chunks),
            "stored_chunks": stored_count,
            "vector_table": f"{VECTOR_SCHEMA_NAME}.{VECTOR_TABLE_NAME}",
            "embedding_model": EMBEDDING_MODEL_NAME,
            "embedding_dimensions": dimension,
            "status": "success",
            "message": "PDF embeddings created and verified successfully.",
        }

        logger.info(
            "PDF ingestion completed successfully | document_id=%s | pages=%s | "
            "characters=%s | chunks=%s | stored=%s | elapsed_seconds=%.2f",
            document_id,
            len(pages),
            len(extracted_text),
            len(valid_chunks),
            stored_count,
            time.monotonic() - started,
        )
        return result

    except PDFIngestionError:
        # Preserve an already annotated ingestion error without wrapping twice.
        raise
    except Exception as exc:
        logger.exception(
            "PDF ingestion failed | document_id=%s | stage=%s | "
            "exception_type=%s | elapsed_seconds=%.2f",
            document_id,
            stage,
            type(exc).__name__,
            time.monotonic() - started,
        )
        raise PDFIngestionError(stage, exc) from exc
