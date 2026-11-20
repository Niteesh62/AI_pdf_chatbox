import logging

from django.conf import settings

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from .pdf_embedding_service import (
    count_document_embeddings,
    get_vector_store,
)

logger = logging.getLogger(__name__)


def ask_pdf_question(document_id, question):

    # =========================================
    # 1. VALIDATE QUESTION
    # =========================================

    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    question = question.strip()

    # =========================================
    # 2. VALIDATE GROQ API KEY
    # =========================================

    groq_api_key = getattr(settings, "GROQ_API_KEY", None)

    if not groq_api_key:
        raise ValueError(
            "GROQ_API_KEY is missing from Django settings."
        )

    # =========================================
    # 3. CONNECT TO VECTOR DATABASE
    # =========================================

    try:
        vector_store = get_vector_store()

    except Exception as error:
        logger.exception("Failed to connect to vector store")

        raise RuntimeError(
            "Could not connect to the vector database."
        ) from error

    # =========================================
    # 4. CHECK STORED EMBEDDINGS
    # =========================================

    try:

        total_chunks = count_document_embeddings(document_id)

        logger.info(
            "Document ID: %s | Total chunks: %s",
            document_id,
            total_chunks
        )

    except Exception as error:

        logger.exception("Failed to check PDF embeddings")

        raise RuntimeError(
            "Could not check the PDF embeddings."
        ) from error

    if total_chunks == 0:

        return (
            "No embeddings found for this PDF. "
            "Please upload or process the PDF again."
        )

    # =========================================
    # 5. RETRIEVE RELEVANT CHUNKS
    # =========================================

    try:

        relevant_chunks = vector_store.similarity_search(
            query=question,
            k=5,
            filter={
                "document_id": int(document_id)
            }
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

    # =========================================
    # 6. PREPARE PDF CONTEXT
    # =========================================

    context = "\n\n".join(
        chunk.page_content
        for chunk in relevant_chunks
        if chunk.page_content
    )

    if not context.strip():

        return "The retrieved PDF content is empty."

    # =========================================
    # 7. CREATE PROMPT
    # =========================================

    prompt = ChatPromptTemplate.from_messages([

        (
            "system",
            """
You are an intelligent PDF assistant.

Answer questions using the provided PDF context.

Rules:

1. Use the PDF context as your primary source.
2. Do not invent information.
3. If the answer is available in the PDF,
   explain it clearly.
4. If the answer is not available in the PDF,
   say that it is not mentioned in the document.
5. Explain in simple language.
6. Use bullet points when appropriate.
7. If the user greets you, respond politely.
8. If the user asks a question unrelated to the PDF,
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

    # =========================================
    # 8. INITIALIZE GROQ LLM
    # =========================================

    try:

        llm = ChatGroq(
            model="openai/gpt-oss-20b",
            temperature=0,
            api_key=groq_api_key,
            max_retries=2,
            timeout=60
        )

    except Exception as error:

        logger.exception("Failed to initialize Groq LLM")

        raise RuntimeError(
            "Could not initialize the Groq AI model."
        ) from error

    # =========================================
    # 9. CREATE RAG CHAIN
    # =========================================

    rag_chain = (
        prompt
        | llm
        | StrOutputParser()
    )

    # =========================================
    # 10. GENERATE ANSWER
    # =========================================

    try:

        answer = rag_chain.invoke({
            "context": context,
            "question": question
        })

        logger.info(
            "AI response generated successfully "
            "for document ID %s",
            document_id
        )

    except Exception as error:

        logger.exception("Groq answer generation failed")

        raise RuntimeError(
            f"AI answer generation failed: {error}"
        ) from error

    # =========================================
    # 11. RETURN ANSWER
    # =========================================

    if not answer or not answer.strip():

        return "The AI returned an empty response. Please try again."

    return answer.strip()