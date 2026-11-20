
import logging
import json

from django.conf import settings
from django.db import connection

from sentence_transformers import SentenceTransformer

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)

# Must be the SAME model used when creating PDF embeddings.
EMBEDDING_MODEL_NAME = getattr(
    settings,
    "PDF_EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)

TOP_K = 5

_embedding_model = None


def get_embedding_model():
    """
    Load the embedding model once and reuse it.
    """

    global _embedding_model

    if _embedding_model is None:
        logger.info(
            "Loading embedding model: %s",
            EMBEDDING_MODEL_NAME
        )

        _embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_NAME
        )

    return _embedding_model


def embed_question(question):
    """
    Convert the question into a 384-dimensional vector.
    """

    model = get_embedding_model()

    embedding = model.encode(
        question,
        normalize_embeddings=True
    )

    if len(embedding) != 384:
        raise ValueError(
            f"Expected 384 dimensions, got {len(embedding)}."
        )

    return embedding.tolist()


def count_document_embeddings(document_id):
    """
    Count stored chunks for one PDF.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM public.pdf_document_embeddings
            WHERE document_id = %s
            """,
            [int(document_id)]
        )

        result = cursor.fetchone()

    return result[0] if result else 0


def retrieve_relevant_chunks(document_id, question, limit=TOP_K):
    """
    Retrieve relevant PDF chunks using pgvector cosine distance.
    """

    query_embedding = embed_question(question)

    # pgvector accepts a vector literal such as [0.1,0.2,...].
    embedding_literal = (
        "[" + ",".join(str(value) for value in query_embedding) + "]"
    )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                content,
                metadata,
                embedding <=> %s::vector AS distance
            FROM public.pdf_document_embeddings
            WHERE document_id = %s
              AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            [
                embedding_literal,
                int(document_id),
                embedding_literal,
                int(limit),
            ]
        )

        rows = cursor.fetchall()

    chunks = []

    for content, metadata, distance in rows:
        if not content:
            continue

        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (TypeError, ValueError):
                metadata = {}

        chunks.append({
            "content": content,
            "metadata": metadata or {},
            "distance": float(distance) if distance is not None else None,
        })

    return chunks


def ask_pdf_question(document_id, question):
    """
    Answer a question using the selected PDF and Groq.
    """

    # 1. Validate question.
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    question = question.strip()

    # 2. Validate document ID.
    try:
        document_id = int(document_id)
    except (TypeError, ValueError):
        raise ValueError("Invalid PDF document ID.")

    # 3. Validate Groq API key.
    groq_api_key = getattr(settings, "GROQ_API_KEY", None)

    if not groq_api_key:
        raise ValueError(
            "GROQ_API_KEY is missing from Django settings."
        )

    # 4. Check stored embeddings.
    try:
        total_chunks = count_document_embeddings(document_id)

        logger.info(
            "Document ID: %s | Total chunks: %s",
            document_id,
            total_chunks
        )

    except Exception as error:
        logger.exception("Failed to count PDF embeddings")

        raise RuntimeError(
            "Could not check the PDF embeddings."
        ) from error

    if total_chunks == 0:
        return (
            "No embeddings found for this PDF. "
            "Please wait for PDF processing to finish or upload it again."
        )

    # 5. Retrieve relevant chunks.
    try:
        relevant_chunks = retrieve_relevant_chunks(
            document_id=document_id,
            question=question,
            limit=TOP_K,
        )

        logger.info(
            "Document ID: %s | Retrieved chunks: %s",
            document_id,
            len(relevant_chunks)
        )

    except Exception as error:
        logger.exception("PDF similarity search failed")

        raise RuntimeError(
            "Failed to retrieve relevant PDF content."
        ) from error

    if not relevant_chunks:
        return (
            "I couldn't find relevant information "
            "in this PDF for your question."
        )

    # 6. Prepare context.
    context_parts = []

    for chunk in relevant_chunks:
        metadata = chunk["metadata"]
        page = metadata.get("page", metadata.get("page_number"))

        page_info = (
            f"Page: {page}\n"
            if page is not None
            else ""
        )

        context_parts.append(
            page_info + chunk["content"]
        )

    context = "\n\n".join(context_parts)

    if not context.strip():
        return "The retrieved PDF content is empty."

    # 7. Create prompt.
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
You are an intelligent PDF assistant.

Answer questions using the provided PDF context.

Rules:
1. Use the PDF context as your primary source.
2. Do not invent information.
3. If the answer is available in the PDF, explain it clearly.
4. If the answer is not available in the PDF,
   say that it is not mentioned in the document.
5. Explain in simple language.
6. Use bullet points when appropriate.
7. If the user greets you, respond politely.
8. If the user asks an unrelated question,
   politely explain that you are a PDF assistant.
"""
        ),
        (
            "human",
            """
PDF CONTEXT:

{context}

USER QUESTION:

{question}

Answer based on the PDF context above.
"""
        )
    ])

    # 8. Initialize Groq.
    try:
        llm = ChatGroq(
            model="openai/gpt-oss-20b",
            temperature=0,
            api_key=groq_api_key,
            max_retries=2,
            timeout=60,
        )

    except Exception as error:
        logger.exception("Failed to initialize Groq LLM")

        raise RuntimeError(
            "Could not initialize the Groq AI model."
        ) from error

    # 9. Create RAG chain.
    rag_chain = prompt | llm | StrOutputParser()

    # 10. Generate answer.
    try:
        answer = rag_chain.invoke({
            "context": context,
            "question": question,
        })

        logger.info(
            "AI response generated successfully for document ID %s",
            document_id
        )

    except Exception as error:
        logger.exception("Groq answer generation failed")

        raise RuntimeError(
            "AI answer generation failed."
        ) from error

    # 11. Return answer.
    if not answer or not answer.strip():
        return "The AI returned an empty response. Please try again."

    return answer.strip()
