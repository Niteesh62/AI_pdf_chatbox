from django.apps import AppConfig
import logging


logger = logging.getLogger(__name__)


class DocumentsConfig(AppConfig):

    default_auto_field = 'django.db.models.BigAutoField'

    name = 'documents'

    def ready(self):
        from . import signals

        logger.info("django_app_initialized | app=%s", self.name)
