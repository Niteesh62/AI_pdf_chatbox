
from django.db import models
from django.core.validators import FileExtensionValidator
import os


class PDFDocument(models.Model):

    # PDF basic information
    title = models.CharField(max_length=255)

    original_filename = models.CharField(
        max_length=255,
        blank=True
    )

    # Actual PDF file stored in media folder
    pdf_file = models.FileField(
        upload_to='pdfs/%Y/%m/%d/',
        validators=[FileExtensionValidator(['pdf'])]
    )

    # PDF metadata
    file_size = models.PositiveBigIntegerField(default=0)

    content_type = models.CharField(
        max_length=100,
        default='application/pdf'
    )

    page_count = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    # Extracted PDF content
    extracted_text = models.TextField(blank=True)

    # Timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):

        if self.pdf_file:
            self.file_size = self.pdf_file.size

            if not self.original_filename:
                self.original_filename = os.path.basename(
                    self.pdf_file.name
                )

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
