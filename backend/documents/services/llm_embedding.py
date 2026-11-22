import logging
import os
import threading

from django.conf import settings

from config.runtime_diagnostics import log_runtime_stage


logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = os.getenv(
    "HF_EMBEDDING_MODEL",
    getattr(
        settings,
        "PDF_EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2",
    ),
)
EXPECTED_VECTOR_SIZE = 384

_embedding_model = None
_embedding_dimension = None
_model_lock = threading.Lock()
_inference_lock = threading.Lock()
_chat_llm = None
_chat_llm_lock = threading.Lock()


def get_embedding_model():
    global _embedding_model, _embedding_dimension

    if _embedding_model is not None:
        return _embedding_model, _embedding_dimension

    with _model_lock:
        if _embedding_model is not None:
            return _embedding_model, _embedding_dimension

        with log_runtime_stage(
            logger,
            "embedding_model_initialization",
            model=EMBEDDING_MODEL_NAME,
            device="cpu",
            low_cpu_mem_usage=True,
            torch_dtype="float16",
        ):
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("MKL_NUM_THREADS", "1")
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

            import torch
            from sentence_transformers import SentenceTransformer

            torch.set_num_threads(1)
            model = SentenceTransformer(
                EMBEDDING_MODEL_NAME,
                device="cpu",
                model_kwargs={
                    "low_cpu_mem_usage": True,
                    "torch_dtype": torch.float16,
                },
            )
            dimension = model.get_embedding_dimension()
            if dimension != EXPECTED_VECTOR_SIZE:
                raise ValueError(
                    f"Embedding model returned {dimension} dimensions; "
                    f"the configured Supabase vector column expects "
                    f"{EXPECTED_VECTOR_SIZE}."
                )

        _embedding_model = model
        _embedding_dimension = int(dimension)
        logger.info(
            "Embedding model ready | model=%s | dimensions=%s | device=cpu",
            EMBEDDING_MODEL_NAME,
            _embedding_dimension,
        )
        return _embedding_model, _embedding_dimension


def encode_texts(texts, *, batch_size, stage, document_id=None):
    if not texts:
        return []

    model, dimension = get_embedding_model()
    effective_batch_size = min(batch_size, len(texts))

    with log_runtime_stage(
        logger,
        stage,
        document_id=document_id,
        model=EMBEDDING_MODEL_NAME,
        chunks=len(texts),
        batch_size=effective_batch_size,
    ):
        with _inference_lock:
            encoded = model.encode(
                texts,
                batch_size=effective_batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )

        vectors = encoded.tolist()
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Embedding model returned {len(vectors)} vectors "
                f"for {len(texts)} texts."
            )
        for index, vector in enumerate(vectors):
            if len(vector) != dimension:
                raise ValueError(
                    f"Embedding {index} has {len(vector)} dimensions; "
                    f"expected {dimension}."
                )

    return vectors


def get_chat_llm():
    global _chat_llm

    if _chat_llm is not None:
        return _chat_llm

    with _chat_llm_lock:
        if _chat_llm is not None:
            return _chat_llm

        api_key = getattr(settings, "GROQ_API_KEY", None)
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing from Django settings.")

        with log_runtime_stage(
            logger,
            "groq_llm_initialization",
            model="openai/gpt-oss-20b",
        ):
            from langchain_groq import ChatGroq

            llm = ChatGroq(
                model="openai/gpt-oss-20b",
                temperature=0,
                api_key=api_key,
                max_retries=2,
                timeout=60,
            )

        _chat_llm = llm
        logger.info("Groq LLM client ready | model=openai/gpt-oss-20b")
        return _chat_llm
