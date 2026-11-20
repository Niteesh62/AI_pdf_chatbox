import logging
import os

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser

from django.db import DatabaseError, connection
from django.conf import settings
from django.http import FileResponse

from .models import PDFDocument
from .serializers import PDFDocumentSerializer, PDFStorageError

from .services.pdf_embedding_service import (
    get_vector_store
)
from .services.pdf_embedding_jobs import enqueue_pdf_embedding

from .services.pdf_chat_service import ask_pdf_question


logger = logging.getLogger(__name__)


def _safe_error_details(error):
    message = str(error) or "No additional error details were provided."
    secrets = (
        settings.SECRET_KEY,
        settings.DATABASE_URL,
        settings.GROQ_API_KEY,
        settings.CLOUDINARY_API_KEY,
        settings.CLOUDINARY_API_SECRET,
        os.getenv("CLOUDINARY_URL"),
    )

    for secret in secrets:
        if secret:
            message = message.replace(secret, "[REDACTED]")

    return {
        "type": type(error).__name__,
        "message": message,
    }


def _upload_failure(stage, code, message, error):
    return Response(
        {
            "status": "failed",
            "stage": stage,
            "code": code,
            "message": message,
            "details": _safe_error_details(error),
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


class HealthCheckView(APIView):

    def get(self, request):
        return Response(
            {"status": "ok"},
            status=status.HTTP_200_OK,
        )


class ReadinessCheckView(APIView):

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except DatabaseError as error:
            logger.exception(
                "Database readiness check failed | alias=%s | reason=%s",
                connection.alias,
                error,
            )
            return Response(
                {
                    "status": "not_ready",
                    "checks": {"database": "unavailable"},
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "status": "ready",
                "checks": {"database": "ok"},
            },
            status=status.HTTP_200_OK,
        )


# ==================================================
# PDF DOCUMENT VIEWSET
# ==================================================

class PDFDocumentViewSet(viewsets.ModelViewSet):

    queryset = PDFDocument.objects.all().order_by("-uploaded_at")

    serializer_class = PDFDocumentSerializer

    parser_classes = [MultiPartParser, FormParser]

    # ===============================================
    # UPLOAD PDF + QUEUE EMBEDDING JOB
    # ===============================================

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        try:
            pdf_document = serializer.save()
        except DatabaseError as error:
            logger.exception("PDF document database insert failed")
            return _upload_failure(
                "database_insert",
                "PDF_DATABASE_INSERT_FAILED",
                "The PDF could not be recorded in the database.",
                error,
            )
        except PDFStorageError as error:
            logger.exception("PDF file storage upload failed")
            return _upload_failure(
                "cloudinary_upload",
                "CLOUDINARY_UPLOAD_FAILED",
                "The PDF could not be stored by the configured Cloudinary storage.",
                error.cause,
            )

        logger.info(
            "PDF uploaded | ID: %s | Title: %s",
            pdf_document.id,
            pdf_document.title
        )

        try:
            enqueue_pdf_embedding(pdf_document.id)
        except RuntimeError as error:
            print(
                f"[EMBEDDING JOB] document_id={pdf_document.id} "
                "status=failed stage=queue",
                flush=True,
            )
            logger.exception(
                "Could not queue PDF embedding job | document_id=%s",
                pdf_document.id,
            )
            response = _upload_failure(
                "embedding_queue",
                "PDF_EMBEDDING_QUEUE_FAILED",
                "The PDF was stored, but its embedding job could not be queued.",
                error,
            )
            response.data["document_id"] = pdf_document.id
            return response

        print(
            f"[EMBEDDING JOB] document_id={pdf_document.id} status=queued",
            flush=True,
        )
        logger.info(
            "PDF upload accepted | document_id=%s | embedding_status=queued",
            pdf_document.id,
        )

        return Response(
            {
                "message": "PDF uploaded. Embedding is queued in the background.",
                "status": "processing",
                "embedding_status": "queued",
                "document": PDFDocumentSerializer(pdf_document).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    # ===============================================
    # DELETE PDF + EMBEDDINGS
    # ===============================================

    def perform_destroy(self, instance):

        try:

            vector_store = get_vector_store()

            vector_store.delete(
                filter={
                    "document_id": int(instance.id)
                }
            )

            logger.info(
                "Embeddings deleted for document %s",
                instance.id
            )

        except Exception as error:

            logger.exception(
                "Failed to delete embeddings"
            )

            raise error

        # Delete actual PDF file
        instance.pdf_file.delete(save=False)

        # Delete database record
        instance.delete()

    # ===============================================
    # DOWNLOAD PDF
    # ===============================================

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):

        pdf = self.get_object()

        return FileResponse(
            pdf.pdf_file.open("rb"),
            as_attachment=True,
            filename=pdf.title
        )

    # ===============================================
    # GET EXTRACTED PDF TEXT
    # ===============================================

    @action(detail=True, methods=["get"])
    def text(self, request, pk=None):

        pdf = self.get_object()

        return Response({
            "id": pdf.id,
            "title": pdf.title,
            "extracted_text": pdf.extracted_text
        })


# ==================================================
# PDF CHAT VIEW
# ==================================================

class PDFChatView(APIView):

    def post(self, request):

        document_id = request.data.get("document_id")

        question = request.data.get("question")

        # ===========================================
        # VALIDATE INPUT
        # ===========================================

        if document_id is None or not question:

            return Response(
                {
                    "error": "document_id and question are required"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        question = str(question).strip()

        if not question:

            return Response(
                {
                    "error": "Question cannot be empty"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate document ID
        try:

            document_id = int(document_id)

        except (TypeError, ValueError):

            return Response(
                {
                    "error": "document_id must be a valid integer"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ===========================================
        # FIND PDF DOCUMENT
        # ===========================================

        try:

            pdf_document = PDFDocument.objects.get(
                id=document_id
            )

        except PDFDocument.DoesNotExist:

            return Response(
                {
                    "error": "PDF document not found"
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ===========================================
        # ASK AI
        # ===========================================

        logger.info(
            "PDF chat request | Document: %s | Question: %s",
            document_id,
            question
        )

        try:

            answer = ask_pdf_question(
                document_id=pdf_document.id,
                question=question
            )

            return Response(
                {
                    "document_id": pdf_document.id,
                    "question": question,
                    "answer": answer,
                    "status": "success"
                },
                status=status.HTTP_200_OK
            )

        except Exception as error:

            logger.exception(
                "PDF chat request failed | Document ID: %s",
                document_id
            )

            return Response(
                {
                    "error": "Failed to generate AI response",
                    "details": str(error)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )