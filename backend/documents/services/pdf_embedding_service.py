
import os
import uuid

from django.conf import settings

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma


# --------------------------------------------------
# 1. CHROMADB STORAGE PATH
# --------------------------------------------------

VECTOR_DB_PATH = os.path.join(
    settings.BASE_DIR,
    "vectorstore"
)

COLLECTION_NAME = "pdf_documents_groq"


print("\n========== PDF INGESTION SERVICE LOADED ==========")
print("Vector DB Path:", VECTOR_DB_PATH)
print("Collection Name:", COLLECTION_NAME)


# --------------------------------------------------
# 2. HUGGING FACE EMBEDDING MODEL
# --------------------------------------------------

def get_embedding_model():

    print("\n[EMBEDDING] Loading Hugging Face model...")

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )

    print("[EMBEDDING] Model loaded successfully.")

    return embeddings


# --------------------------------------------------
# 3. CONNECT TO CHROMADB
# --------------------------------------------------

def get_vector_store():

    print("\n[CHROMADB] Connecting to ChromaDB...")

    embeddings = get_embedding_model()

    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=VECTOR_DB_PATH
    )

    print("[CHROMADB] Connected successfully.")

    print(
        "[CHROMADB] Existing record count:",
        vector_store._collection.count()
    )

    return vector_store


# --------------------------------------------------
# 4. PDF INGESTION PIPELINE
# --------------------------------------------------

def create_pdf_embeddings(pdf_document):

    print("\n==========================================")
    print("         PDF INGESTION STARTED")
    print("==========================================")

    print("[PDF] Document ID:", pdf_document.id)
    print("[PDF] Document Title:", pdf_document.title)

    # ----------------------------------------------
    # STEP 1: GET PDF FILE PATH
    # ----------------------------------------------

    pdf_path = pdf_document.pdf_file.path

    print("\n[PDF] File Path:", pdf_path)

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(
            f"PDF file does not exist: {pdf_path}"
        )

    print("[PDF] File exists successfully.")

    # ----------------------------------------------
    # STEP 2: LOAD PDF
    # ----------------------------------------------

    print("\n[LOADER] Loading PDF...")

    loader = PyPDFLoader(pdf_path)

    pages = loader.load()

    print("[LOADER] Total pages:", len(pages))

    if not pages:
        raise ValueError("No readable text found in this PDF.")

    # ----------------------------------------------
    # STEP 3: EXTRACT TEXT
    # ----------------------------------------------

    print("\n[TEXT] Extracting PDF text...")

    extracted_text = "\n\n".join(
        page.page_content for page in pages
    )

    print("[TEXT] Total extracted characters:", len(extracted_text))

    print("\n[TEXT] First 300 characters:")
    print(extracted_text[:300])

    if not extracted_text.strip():
        raise ValueError(
            "PDF contains no extractable text. "
            "It may be a scanned PDF requiring OCR."
        )

    # Save extracted text in Django database
    pdf_document.extracted_text = extracted_text

    pdf_document.save(
        update_fields=["extracted_text"]
    )

    print("[MYSQL] Extracted text saved successfully.")

    # ----------------------------------------------
    # STEP 4: SPLIT TEXT INTO CHUNKS
    # ----------------------------------------------

    print("\n[SPLITTER] Splitting PDF text into chunks...")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )

    chunks = splitter.split_documents(pages)

    print("[SPLITTER] Total chunks created:", len(chunks))

    if not chunks:
        raise ValueError("Could not create PDF text chunks.")

    print("\n[SPLITTER] First chunk preview:")
    print(chunks[0].page_content[:300])

    # ----------------------------------------------
    # STEP 5: ADD METADATA
    # ----------------------------------------------

    print("\n[METADATA] Adding document metadata...")

    for index, chunk in enumerate(chunks):

        chunk.metadata["document_id"] = int(pdf_document.id)

        chunk.metadata["document_title"] = str(
            pdf_document.title
        )

        chunk.metadata["chunk_index"] = index

    print("[METADATA] Metadata added successfully.")

    print("[METADATA] First chunk metadata:")
    print(chunks[0].metadata)

    # ----------------------------------------------
    # STEP 6: CONNECT TO CHROMADB
    # ----------------------------------------------

    vector_store = get_vector_store()

    # ----------------------------------------------
    # STEP 7: REMOVE OLD DOCUMENT CHUNKS
    # ----------------------------------------------

    print("\n[CHROMADB] Removing previous document chunks...")

    vector_store.delete(
        where={
            "document_id": int(pdf_document.id)
        }
    )

    print("[CHROMADB] Previous chunks removed.")

    # ----------------------------------------------
    # STEP 8: GENERATE AND STORE EMBEDDINGS
    # ----------------------------------------------

    print("\n[EMBEDDING] Generating embeddings and storing chunks...")

    chunk_ids = [
        str(uuid.uuid4())
        for _ in chunks
    ]

    vector_store.add_documents(
        documents=chunks,
        ids=chunk_ids
    )

    print("[EMBEDDING] Embeddings stored successfully.")

    # ----------------------------------------------
    # STEP 9: VERIFY CHROMADB STORAGE
    # ----------------------------------------------

    print("\n[VERIFY] Checking stored records...")

    stored_data = vector_store.get(
        where={
            "document_id": int(pdf_document.id)
        },
        include=["documents", "metadatas"]
    )

    stored_count = len(stored_data["ids"])

    print("[VERIFY] Expected chunks:", len(chunks))
    print("[VERIFY] Stored chunks:", stored_count)

    if stored_count != len(chunks):
        raise ValueError(
            "Embedding storage verification failed."
        )

    print("\n[VERIFY] First stored record:")

    if stored_count > 0:

        print("ID:", stored_data["ids"][0])

        print(
            "Text:",
            stored_data["documents"][0][:300]
        )

        print(
            "Metadata:",
            stored_data["metadatas"][0]
        )

    # ----------------------------------------------
    # STEP 10: FINAL RESULT
    # ----------------------------------------------

    result = {
        "document_id": pdf_document.id,
        "total_pages": len(pages),
        "total_characters": len(extracted_text),
        "total_chunks": len(chunks),
        "stored_chunks": stored_count,
        "collection_name": COLLECTION_NAME,
        "message": "PDF embeddings created and verified successfully"
    }

    print("\n==========================================")
    print("       PDF INGESTION COMPLETED")
    print("==========================================")

    print(result)

    return result
