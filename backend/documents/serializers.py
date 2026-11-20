
from django.db import DatabaseError
from rest_framework import serializers
from .models import PDFDocument


class PDFStorageError(Exception):

    def __init__(self, cause):
        self.cause = cause
        super().__init__(str(cause))


class PDFDocumentSerializer(serializers.ModelSerializer):

    class Meta:
        model = PDFDocument
        fields = [
            'id',
            'title',
            'original_filename',
            'pdf_file',
            'file_size',
            'content_type',
            'page_count',
            'extracted_text',
            'uploaded_at',
            'updated_at',
        ]

        read_only_fields = [
            'id',
            'original_filename',
            'file_size',
            'content_type',
            'uploaded_at',
            'updated_at',
        ]

    def create(self, validated_data):

        uploaded_file = validated_data['pdf_file']

        validated_data['original_filename'] = uploaded_file.name

        validated_data['content_type'] = (
            uploaded_file.content_type or 'application/pdf'
        )

        try:
            return PDFDocument.objects.create(**validated_data)
        except DatabaseError:
            raise
        except Exception as error:
            raise PDFStorageError(error) from error
