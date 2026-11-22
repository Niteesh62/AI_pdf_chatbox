from django.contrib import admin

from .models import PDFDocument


@admin.register(PDFDocument)
class PDFDocumentAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'title',
        'embedding_status',
        'uploaded_at'
    )

    search_fields = ('title',)

    list_filter = ('embedding_status', 'uploaded_at')