
import logging
import os

from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.http import FileResponse

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PDFDocument
from .serializers import PDFDocumentSerializer, PDFStorageError

from .services.pdf_embedding_jobs import enqueue_pdf_embedding
from .services.pdf_chat_service import ask_pdf_question


logger = logging.getLogger(__name__)


# ==================================================
# SAFE ERROR HANDLING
# ==================================================

def _safe_error_details(error):
    message = str(error) or "No additional error details were provided."

    secrets = (
        getattr(settings, "SECRET_KEY", None),
        getattr(settings, "DATABASE_URL", None),
        getattr(settings, "GROQ_API_KEY", None),
        getattr(settings, "CLOUDINARY_API_KEY", None),
        getattr(settings, "CLOUDINARY_API_SECRET", None),
        os.getenv("CLOUDINARY_URL"),
    )

    for secret in secrets:
        if secret:
            message = message.replace(str(secret), "[REDACTED]")

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


# ==================================================
# HEALTH CHECK
# ==================================================

class HealthCheckView(APIView):

    def get(self, request):
        return Response(
            {"status": "ok"},
            status=status.HTTP_200_OK,
        )


# ==================================================
# DATABASE READINESS CHECK
# ==================================================

class ReadinessCheckView(APIView):

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")

        except DatabaseError:
            logger.exception("Database readiness check failed")

            return Response(
                {
                    "status": "not_ready",
                    "checks": {
                        "database": "unavailable"
                    },
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "status": "ready",
                "checks": {
                    "database": "ok"
                },
            },
            status=status.HTTP_200_OK,
        )


# ==================================================
# PDF DOCUMENT VIEWSET
# ==================================================

class PDFDocumentViewSet(viewsets.ModelViewSet):

    queryset = PDFDocument.objects.all().order_by("-uploaded_at")

    serializer_class = PDFDocumentSerializer

    parser_classes = [
        MultiPartParser,
        FormParser,
    ]

    # ===============================================
    # UPLOAD PDF AND QUEUE EMBEDDING JOB
    # ===============================================

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        try:
            pdf_document = serializer.save()

        except DatabaseError as error:
            logger.exception("PDF database insert failed")

            return _upload_failure(
                "database_insert",
                "PDF_DATABASE_INSERT_FAILED",
                "The PDF could not be recorded in the database.",
                error,
            )

        except PDFStorageError as error:
            logger.exception("Cloudinary PDF upload failed")

            return _upload_failure(
                "cloudinary_upload",
                "CLOUDINARY_UPLOAD_FAILED",
                "The PDF could not be stored in Cloudinary.",
                getattr(error, "cause", error),
            )

        logger.info(
            "PDF uploaded | document_id=%s | title=%s",
            pdf_document.id,
            pdf_document.title,
        )

        # Queue the embedding job
        try:
            enqueue_pdf_embedding(pdf_document.id)

        except Exception as error:
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
    # DELETE PDF AND ITS EMBEDDINGS
    # ===============================================

    def perform_destroy(self, instance):

        document_id = instance.id

        # Preserve the Cloudinary storage reference before deleting
        # the Django database record.
        file_name = instance.pdf_file.name if instance.pdf_file else None
        file_storage = instance.pdf_file.storage if instance.pdf_file else None

        try:
            # Delete embeddings and PDF record in one DB transaction.
            with transaction.atomic():

                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM public.pdf_document_embeddings
                        WHERE document_id = %s
                        """,
                        [document_id],
                    )

                    deleted_count = cursor.rowcount

                logger.info(
                    "Deleted %s embeddings | document_id=%s",
                    deleted_count,
                    document_id,
                )

                instance.delete()

            logger.info(
                "PDF database record deleted | document_id=%s",
                document_id,
            )

        except Exception:
            logger.exception(
                "Failed to delete PDF database record or embeddings | document_id=%s",
                document_id,
            )
            raise

        # Cloudinary deletion is an external operation, so it is performed
        # after the database transaction has committed.
        if file_name and file_storage:
            try:
                file_storage.delete(file_name)

                logger.info(
                    "Cloudinary PDF file deletion requested | document_id=%s",
                    document_id,
                )

            except Exception:
                logger.exception(
                    "PDF database record was deleted, but Cloudinary file deletion failed | document_id=%s",
                    document_id,
                )

    # ===============================================
    # DOWNLOAD PDF
    # ===============================================

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):

        pdf = self.get_object()

        try:
            file_handle = pdf.pdf_file.open("rb")

            return FileResponse(
                file_handle,
                as_attachment=True,
                filename=os.path.basename(pdf.title or "document.pdf"),
                content_type="application/pdf",
            )

        except Exception:
            logger.exception(
                "PDF download failed | document_id=%s",
                pdf.id,
            )

            return Response(
                {
                    "error": "Unable to download this PDF."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ===============================================
    # GET EXTRACTED PDF TEXT
    # ===============================================

    @action(detail=True, methods=["get"])
    def text(self, request, pk=None):

        pdf = self.get_object()

        return Response(
            {
                "id": pdf.id,
                "title": pdf.title,
                "extracted_text": pdf.extracted_text,
            },
            status=status.HTTP_200_OK,
        )


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

        if document_id is None or question is None:

            return Response(
                {
                    "error": "document_id and question are required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        question = str(question).strip()

        if not question:

            return Response(
                {
                    "error": "Question cannot be empty."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ===========================================
        # VALIDATE DOCUMENT ID
        # ===========================================

        try:
            document_id = int(document_id)

            if document_id <= 0:
                raise ValueError("Document ID must be positive.")

        except (TypeError, ValueError):

            return Response(
                {
                    "error": "document_id must be a valid positive integer."
                },
                status=status.HTTP_400_BAD_REQUEST,
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
                    "error": "PDF document not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ===========================================
        # ASK AI
        # ===========================================

        logger.info(
            "PDF chat request | document_id=%s",
            document_id,
        )

        try:
            answer = ask_pdf_question(
                document_id=pdf_document.id,
                question=question,
            )

            return Response(
                {
                    "document_id": pdf_document.id,
                    "question": question,
                    "answer": answer,
                    "status": "success",
                },
                status=status.HTTP_200_OK,
            )

        except Exception:
            logger.exception(
                "PDF chat request failed | document_id=%s",
                document_id,
            )

            return Response(
                {
                    "error": "Failed to generate AI response. Check backend logs for details."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
