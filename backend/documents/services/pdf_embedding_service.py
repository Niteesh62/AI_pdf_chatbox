
import os
import shutil
import tempfile
import uuid
import re
import traceback
import logging

from django.conf import settings

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma


# ==================================================
# 1. LOGGING CONFIGURATION
# ==================================================

logger = logging.getLogger(__name__)

VECTOR_DB_PATH = os.path.join(
    settings.BASE_DIR,
    "vectorstore"
)

COLLECTION_NAME = "pdf_documents_groq"


class PDFIngestionError(Exception):

    def __init__(self, stage, cause):
        self.stage = stage
        self.cause = cause
        super().__init__(str(cause))


print("\n" + "=" * 60)
print("PDF INGESTION SERVICE LOADED")
print("=" * 60)

print("[CONFIG] BASE_DIR:", settings.BASE_DIR)
print("[CONFIG] Vector DB Path:", VECTOR_DB_PATH)
print("[CONFIG] Collection:", COLLECTION_NAME)
print("[CONFIG] Vector DB exists:", os.path.exists(VECTOR_DB_PATH))


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

        return embeddings

    except Exception as e:

        print("[EMBEDDING ERROR]", str(e))
        traceback.print_exc()

        raise


# ==================================================
# 4. CONNECT TO CHROMADB
# ==================================================

def get_vector_store():

    print("\n[CHROMADB] Connecting to ChromaDB...")

    try:

        os.makedirs(
            VECTOR_DB_PATH,
            exist_ok=True
        )

        print("[CHROMADB] Storage directory:", VECTOR_DB_PATH)
        print("[CHROMADB] Directory writable:",
              os.access(VECTOR_DB_PATH, os.W_OK))

        embeddings = get_embedding_model()

        vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=VECTOR_DB_PATH
        )

        print("[CHROMADB] Connected successfully")

        count = vector_store._collection.count()

        print("[CHROMADB] Existing records:", count)

        return vector_store

    except Exception as e:

        print("[CHROMADB ERROR]", str(e))
        traceback.print_exc()

        raise


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
        print("\n[STEP 7] Connecting ChromaDB...")

        vector_store = get_vector_store()

        # ------------------------------------------
        # STEP 8: DELETE OLD DOCUMENT CHUNKS
        # ------------------------------------------

        stage = "old_embedding_cleanup"
        print("\n[STEP 8] Removing old document chunks...")

        vector_store.delete(
            where={
                "document_id": int(pdf_document.id)
            }
        )

        print("[CHROMADB] Old chunks deleted")

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
        print("\n[STEP 10] Verifying ChromaDB records...")

        stored_data = vector_store.get(
            where={
                "document_id": int(pdf_document.id)
            },
            include=["documents", "metadatas"]
        )

        stored_count = len(stored_data["ids"])

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
            "collection_name": COLLECTION_NAME,
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
