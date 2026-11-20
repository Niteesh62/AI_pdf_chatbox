
import os
import shutil
import tempfile
import uuid
import re
import traceback
import logging
import threading

from django.conf import settings
from django.db import connection

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGEngine, PGVectorStore
from sqlalchemy.engine import URL


# ==================================================
# 1. LOGGING CONFIGURATION
# ==================================================

logger = logging.getLogger(__name__)

VECTOR_SCHEMA_NAME = "public"
VECTOR_TABLE_NAME = "pdf_document_embeddings"
VECTOR_METADATA_COLUMNS = [
    "document_id",
    "document_title",
    "chunk_index",
]
_vector_store = None
_vector_store_lock = threading.Lock()


class PDFIngestionError(Exception):

    def __init__(self, stage, cause):
        self.stage = stage
        self.cause = cause
        super().__init__(str(cause))


print("\n" + "=" * 60)
print("PDF INGESTION SERVICE LOADED")
print("=" * 60)

print("[CONFIG] BASE_DIR:", settings.BASE_DIR)
print("[CONFIG] Vector store: Supabase PostgreSQL pgvector")
print("[CONFIG] Vector table:", f"{VECTOR_SCHEMA_NAME}.{VECTOR_TABLE_NAME}")


# ==================================================
# 2. CLEAN PDF TEXT
# ==================================================

def clean_pdf_text(text):

    if not text:
        return ""

    original_length = len(text)

    # Remove PostgreSQL-incompatible NULL characters
    text = text.replace("\x00", "")

    # Remove unwanted control characters
    text = re.sub(
        r"[\x01-\x08\x0B\x0C\x0E-\x1F]",
        "",
        text
    )

    cleaned_length = len(text)

    removed = original_length - cleaned_length

    if removed > 0:
        print(
            f"[CLEANING] Removed {removed} invalid characters"
        )

    print("[CLEANING] Original length:", original_length)
    print("[CLEANING] Cleaned length:", cleaned_length)
    print("[CLEANING] NULL character exists:", "\x00" in text)

    return text.strip()


# ==================================================
# 3. HUGGING FACE EMBEDDING MODEL
# ==================================================

def get_embedding_model():

    print("\n[EMBEDDING] Loading Hugging Face model...")

    try:

        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True}
        )

        print("[EMBEDDING] Model loaded successfully")

        # Test embedding generation
        test_embedding = embeddings.embed_query(
            "Testing PDF embedding model"
        )

        print("[EMBEDDING] Test successful")
        print("[EMBEDDING] Vector dimensions:", len(test_embedding))

        return embeddings, len(test_embedding)

    except Exception as e:

        print("[EMBEDDING ERROR]", str(e))
        traceback.print_exc()

        raise


# ==================================================
# 4. CONNECT TO POSTGRESQL PGVECTOR
# ==================================================

def _ensure_vector_table(vector_size):

    if connection.vendor != "postgresql":
        raise RuntimeError(
            "pgvector requires PostgreSQL. Configure DATABASE_URL "
            "with a PostgreSQL connection string."
        )

    vector_size = int(vector_size)
    if vector_size <= 0:
        raise ValueError("The embedding model returned an invalid vector size.")

    schema = connection.ops.quote_name(VECTOR_SCHEMA_NAME)
    table = connection.ops.quote_name(VECTOR_TABLE_NAME)

    with connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute(
            """
            SELECT namespace.nspname
            FROM pg_extension AS extension
            JOIN pg_namespace AS namespace
              ON namespace.oid = extension.extnamespace
            WHERE extension.extname = %s
            """,
            ["vector"],
        )
        extension_schema_row = cursor.fetchone()
        if not extension_schema_row:
            raise RuntimeError(
                "The PostgreSQL vector extension is not available."
            )

        extension_schema = extension_schema_row[0]
        vector_type = (
            f"{connection.ops.quote_name(extension_schema)}."
            f"{connection.ops.quote_name('vector')}({vector_size})"
        )
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {schema}.{table} (
                "langchain_id" UUID PRIMARY KEY,
                "content" TEXT NOT NULL,
                "embedding" {vector_type} NOT NULL,
                "document_id" BIGINT NOT NULL,
                "document_title" TEXT,
                "chunk_index" BIGINT,
                "langchain_metadata" JSON
            )
            """
        )
    return extension_schema


def get_vector_store():

    global _vector_store

    if _vector_store is not None:
        return _vector_store

    with _vector_store_lock:
        if _vector_store is not None:
            return _vector_store

        print("\n[PGVECTOR] Connecting to Supabase PostgreSQL...")

        try:
            if connection.vendor != "postgresql":
                raise RuntimeError(
                    "pgvector requires PostgreSQL. Configure DATABASE_URL "
                    "with a PostgreSQL connection string."
                )

            embeddings, vector_size = get_embedding_model()
            extension_schema = _ensure_vector_table(vector_size)

            params = connection.get_connection_params()
            query = {}
            if params.get("sslmode"):
                query["sslmode"] = params["sslmode"]

            database_url = URL.create(
                "postgresql+psycopg",
                username=params.get("user") or None,
                password=params.get("password") or None,
                host=params.get("host") or None,
                port=int(params["port"]) if params.get("port") else None,
                database=params.get("dbname") or None,
                query=query,
            )
            engine = PGEngine.from_connection_string(
                database_url,
                connect_args={
                    "prepare_threshold": params.get("prepare_threshold"),
                    "options": (
                        f"-c search_path={VECTOR_SCHEMA_NAME},{extension_schema}"
                    ),
                },
            )

            _vector_store = PGVectorStore.create_sync(
                engine=engine,
                embedding_service=embeddings,
                table_name=VECTOR_TABLE_NAME,
                schema_name=VECTOR_SCHEMA_NAME,
                content_column="content",
                embedding_column="embedding",
                metadata_columns=VECTOR_METADATA_COLUMNS,
                id_column="langchain_id",
                metadata_json_column="langchain_metadata",
            )

            print(
                f"[PGVECTOR] Connected table="
                f"{VECTOR_SCHEMA_NAME}.{VECTOR_TABLE_NAME}",
                flush=True,
            )
            return _vector_store

        except Exception as error:
            print(
                f"[PGVECTOR ERROR] {type(error).__name__}: {error}",
                flush=True,
            )
            traceback.print_exc()
            logger.exception("Could not initialize the PostgreSQL vector store")
            raise


def count_document_embeddings(document_id):

    schema = connection.ops.quote_name(VECTOR_SCHEMA_NAME)
    table = connection.ops.quote_name(VECTOR_TABLE_NAME)
    document_id_column = connection.ops.quote_name("document_id")

    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*) FROM {schema}.{table} "
            f"WHERE {document_id_column} = %s",
            [int(document_id)],
        )
        result = cursor.fetchone()

    return int(result[0]) if result else 0


# ==================================================
# 5. MAIN PDF INGESTION PIPELINE
# ==================================================

def create_pdf_embeddings(pdf_document):

    print("\n" + "=" * 60)
    print("PDF INGESTION STARTED")
    print("=" * 60)

    print("[DOCUMENT] ID:", pdf_document.id)
    print("[DOCUMENT] Title:", pdf_document.title)
    print("[DOCUMENT] File:", pdf_document.pdf_file.name)

    stage = "cloudinary_download"

    try:

        # ------------------------------------------
        # STEP 1: COPY PDF TO TEMPORARY FILE
        # ------------------------------------------

        print("\n[STEP 1] Reading uploaded PDF...")

        with tempfile.TemporaryDirectory() as temporary_directory:

            pdf_path = os.path.join(
                temporary_directory,
                "document.pdf"
            )

            with pdf_document.pdf_file.open("rb") as stored_file:

                with open(pdf_path, "wb") as temporary_file:

                    shutil.copyfileobj(
                        stored_file,
                        temporary_file
                    )

            print("[PDF] Temporary path:", pdf_path)
            print("[PDF] File exists:", os.path.exists(pdf_path))

            file_size = os.path.getsize(pdf_path)

            print("[PDF] File size:", file_size, "bytes")

            if file_size == 0:
                raise ValueError("Uploaded PDF is empty.")

            if file_size < 5:
                raise ValueError("Invalid PDF file.")

            with open(pdf_path, "rb") as check_file:
                file_header = check_file.read(5)

            print("[PDF] File header:", file_header)

            if file_header != b"%PDF-":
                raise ValueError(
                    "Uploaded file does not have a valid PDF header."
                )

            # --------------------------------------
            # STEP 2: LOAD PDF
            # --------------------------------------

            stage = "pdf_parse"
            print("\n[STEP 2] Loading PDF with PyPDFLoader...")

            loader = PyPDFLoader(pdf_path)

            pages = loader.load()

            print("[LOADER] Total pages:", len(pages))

            if not pages:
                raise ValueError("No pages found in PDF.")

            for index, page in enumerate(pages):

                print(
                    f"[PAGE {index + 1}] "
                    f"Characters: {len(page.page_content)}"
                )

                print(
                    f"[PAGE {index + 1}] "
                    f"Metadata: {page.metadata}"
                )

        # ------------------------------------------
        # STEP 3: CLEAN EXTRACTED TEXT
        # ------------------------------------------

        stage = "text_extraction"
        print("\n[STEP 3] Extracting and cleaning PDF text...")

        for index, page in enumerate(pages):

            original_text = page.page_content

            print(
                f"[TEXT] Page {index + 1} original length:",
                len(original_text)
            )

            page.page_content = clean_pdf_text(
                original_text
            )

            print(
                f"[TEXT] Page {index + 1} cleaned length:",
                len(page.page_content)
            )

        extracted_text = "\n\n".join(
            page.page_content for page in pages
        )

        print("[TEXT] Total characters:", len(extracted_text))
        print("[TEXT] Empty:", not extracted_text.strip())
        print("[TEXT] Contains NULL:", "\x00" in extracted_text)

        if not extracted_text.strip():

            raise ValueError(
                "No extractable text found. "
                "This PDF may require OCR."
            )

        # ------------------------------------------
        # STEP 4: SAVE CLEAN TEXT TO DATABASE
        # ------------------------------------------

        stage = "database_update"
        print("\n[STEP 4] Saving extracted text to database...")

        # Clean once more before database save
        extracted_text = clean_pdf_text(extracted_text)

        pdf_document.extracted_text = extracted_text

        pdf_document.save(
            update_fields=["extracted_text"]
        )

        print("[DATABASE] Extracted text saved successfully")

        # ------------------------------------------
        # STEP 5: SPLIT INTO CHUNKS
        # ------------------------------------------

        stage = "chunking"
        print("\n[STEP 5] Splitting PDF into chunks...")

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )

        chunks = splitter.split_documents(pages)

        print("[SPLITTER] Total chunks:", len(chunks))

        if not chunks:
            raise ValueError("No chunks created.")

        for index, chunk in enumerate(chunks):

            # Final cleaning before vector storage
            chunk.page_content = clean_pdf_text(
                chunk.page_content
            )

            if not chunk.page_content.strip():
                print(
                    f"[WARNING] Empty chunk detected: {index}"
                )

        # Remove empty chunks
        chunks = [
            chunk for chunk in chunks
            if chunk.page_content.strip()
        ]

        print("[SPLITTER] Valid chunks:", len(chunks))

        if not chunks:
            raise ValueError("All extracted chunks are empty.")

        # ------------------------------------------
        # STEP 6: ADD METADATA
        # ------------------------------------------

        print("\n[STEP 6] Adding metadata...")

        for index, chunk in enumerate(chunks):

            chunk.metadata["document_id"] = int(
                pdf_document.id
            )

            chunk.metadata["document_title"] = str(
                pdf_document.title
            )

            chunk.metadata["chunk_index"] = index

        print("[METADATA] Metadata added successfully")
        print("[METADATA] Sample:", chunks[0].metadata)

        # ------------------------------------------
        # STEP 7: CONNECT VECTOR STORE
        # ------------------------------------------

        stage = "vector_store_connect"
        print("\n[STEP 7] Connecting to Supabase pgvector...")

        vector_store = get_vector_store()

        # ------------------------------------------
        # STEP 8: DELETE OLD DOCUMENT CHUNKS
        # ------------------------------------------

        stage = "old_embedding_cleanup"
        print("\n[STEP 8] Removing old document chunks...")

        vector_store.delete(
            filter={
                "document_id": int(pdf_document.id)
            }
        )

        print("[PGVECTOR] Old chunks deleted")

        # ------------------------------------------
        # STEP 9: GENERATE EMBEDDINGS
        # ------------------------------------------

        stage = "embedding_generation_and_storage"
        print("\n[STEP 9] Generating and storing embeddings...")

        chunk_ids = [
            str(uuid.uuid4())
            for _ in chunks
        ]

        print("[EMBEDDING] Chunks to process:", len(chunks))
        print("[EMBEDDING] Starting vector storage...")

        vector_store.add_documents(
            documents=chunks,
            ids=chunk_ids
        )

        print("[EMBEDDING] Storage completed successfully")

        # ------------------------------------------
        # STEP 10: VERIFY STORAGE
        # ------------------------------------------

        stage = "embedding_verification"
        print("\n[STEP 10] Verifying pgvector records...")

        stored_count = count_document_embeddings(pdf_document.id)

        print("[VERIFY] Expected:", len(chunks))
        print("[VERIFY] Stored:", stored_count)

        if stored_count != len(chunks):

            raise ValueError(
                f"Storage verification failed. "
                f"Expected {len(chunks)}, got {stored_count}"
            )

        print("[VERIFY] Vector storage verified")

        # ------------------------------------------
        # STEP 11: FINAL RESULT
        # ------------------------------------------

        result = {
            "document_id": pdf_document.id,
            "total_pages": len(pages),
            "total_characters": len(extracted_text),
            "total_chunks": len(chunks),
            "stored_chunks": stored_count,
            "vector_table": f"{VECTOR_SCHEMA_NAME}.{VECTOR_TABLE_NAME}",
            "status": "success",
            "message": "PDF embeddings created and verified successfully"
        }

        print("\n" + "=" * 60)
        print("PDF INGESTION COMPLETED SUCCESSFULLY")
        print("=" * 60)

        print("[RESULT]", result)

        return result

    except Exception as e:

        print("\n" + "=" * 60)
        print("PDF INGESTION FAILED")
        print("=" * 60)

        print("[ERROR TYPE]", type(e).__name__)
        print("[ERROR MESSAGE]", str(e))

        traceback.print_exc()

        logger.exception(
            "PDF ingestion failed for document ID %s",
            pdf_document.id
        )

        raise PDFIngestionError(stage, e) from e
