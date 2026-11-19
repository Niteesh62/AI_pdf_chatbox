
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    PDFDocumentViewSet,
    PDFChatView,
)

# Create router
router = DefaultRouter()

# Register PDF APIs
router.register(
    "pdfs",
    PDFDocumentViewSet,
    basename="pdf"
)

# API URL patterns
urlpatterns = [
    # PDF upload, list, retrieve, update and delete
    path("", include(router.urls)),

    # Chat with uploaded PDF
    path(
        "chat/",
        PDFChatView.as_view(),
        name="pdf-chat"
    ),
]
