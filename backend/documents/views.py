import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser

from django.http import FileResponse

from .models import PDFDocument
from .serializers import PDFDocumentSerializer

from .services.pdf_embedding_service import (
    create_pdf_embeddings,
    get_vector_store
)

from .services.pdf_chat_service import ask_pdf_question


logger = logging.getLogger(__name__)


# ==================================================
# PDF DOCUMENT VIEWSET
# ==================================================

class PDFDocumentViewSet(viewsets.ModelViewSet):

    queryset = PDFDocument.objects.all().order_by("-uploaded_at")

    serializer_class = PDFDocumentSerializer

    parser_classes = [MultiPartParser, FormParser]

    # ===============================================
    # UPLOAD PDF + CREATE EMBEDDINGS
    # ===============================================

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        pdf_document = serializer.save()

        logger.info(
            "PDF uploaded | ID: %s | Title: %s",
            pdf_document.id,
            pdf_document.title
        )

        try:

            result = create_pdf_embeddings(pdf_document)

            logger.info(
                "PDF embeddings created | ID: %s",
                pdf_document.id
            )

            return Response(
                {
                    "message": "PDF uploaded and embeddings created successfully",
                    "status": "completed",
                    "document": PDFDocumentSerializer(
                        pdf_document
                    ).data,
                    "embedding_details": result
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as error:

            logger.exception(
                "PDF embedding creation failed"
            )

            return Response(
                {
                    "message": "PDF uploaded, but embedding creation failed",
                    "status": "failed",
                    "document_id": pdf_document.id,
                    "error": str(error)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # ===============================================
    # DELETE PDF + EMBEDDINGS
    # ===============================================

    def perform_destroy(self, instance):

        try:

            vector_store = get_vector_store()

            vector_store.delete(
                where={
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