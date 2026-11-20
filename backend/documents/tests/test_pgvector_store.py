from unittest.mock import patch

from django.test import SimpleTestCase

from documents.services import pdf_embedding_service


class PGVectorStoreTests(SimpleTestCase):

    def tearDown(self):
        pdf_embedding_service._vector_store = None

    @patch("documents.services.pdf_embedding_service.PGVectorStore.create_sync")
    @patch("documents.services.pdf_embedding_service.PGEngine.from_connection_string")
    @patch("documents.services.pdf_embedding_service.get_embedding_model")
    @patch("documents.services.pdf_embedding_service.connection")
    def test_creates_pgvector_store_from_django_database_settings(
        self,
        database_connection,
        get_embeddings,
        create_engine,
        create_vector_store,
    ):
        database_connection.vendor = "postgresql"
        database_connection.get_connection_params.return_value = {
            "user": "test-user",
            "password": "test-password",
            "host": "db.example.test",
            "port": 5432,
            "dbname": "test-db",
            "sslmode": "require",
            "prepare_threshold": None,
        }
        database_connection.ops.quote_name.side_effect = (
            lambda name: f'"{name}"'
        )
        cursor = database_connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("extensions",)
        embeddings = object()
        get_embeddings.return_value = (embeddings, 384)
        engine = object()
        create_engine.return_value = engine
        vector_store = object()
        create_vector_store.return_value = vector_store

        result = pdf_embedding_service.get_vector_store()

        self.assertIs(result, vector_store)
        create_engine.assert_called_once()
        connection_url = create_engine.call_args.args[0]
        self.assertEqual(connection_url.host, "db.example.test")
        self.assertEqual(connection_url.database, "test-db")
        self.assertEqual(connection_url.query["sslmode"], "require")
        self.assertEqual(
            create_engine.call_args.kwargs["connect_args"],
            {
                "prepare_threshold": None,
                "options": "-c search_path=public,extensions",
            },
        )
        create_vector_store.assert_called_once_with(
            engine=engine,
            embedding_service=embeddings,
            table_name="pdf_document_embeddings",
            schema_name="public",
            content_column="content",
            embedding_column="embedding",
            metadata_columns=["document_id", "document_title", "chunk_index"],
            id_column="langchain_id",
            metadata_json_column="langchain_metadata",
        )
        self.assertEqual(cursor.execute.call_count, 3)
        self.assertIn(
            '"extensions"."vector"(384)',
            cursor.execute.call_args_list[2].args[0],
        )

    @patch("documents.services.pdf_embedding_service.connection")
    def test_rejects_non_postgresql_database(self, database_connection):
        database_connection.vendor = "sqlite"

        with self.assertRaisesRegex(RuntimeError, "pgvector requires PostgreSQL"):
            pdf_embedding_service.get_vector_store()

    @patch("documents.services.pdf_embedding_service.connection")
    def test_reports_missing_vector_extension(self, database_connection):
        database_connection.vendor = "postgresql"
        database_connection.ops.quote_name.side_effect = (
            lambda name: f'"{name}"'
        )
        cursor = database_connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None

        with self.assertRaisesRegex(
            RuntimeError,
            "PostgreSQL vector extension is not available",
        ):
            pdf_embedding_service._ensure_vector_table(384)

    @patch("documents.services.pdf_embedding_service.connection")
    def test_counts_chunks_for_a_document(self, database_connection):
        database_connection.ops.quote_name.side_effect = (
            lambda name: f'"{name}"'
        )
        cursor = database_connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (7,)

        result = pdf_embedding_service.count_document_embeddings("42")

        self.assertEqual(result, 7)
        cursor.execute.assert_called_once()
        self.assertIn('"document_id" = %s', cursor.execute.call_args.args[0])
        self.assertEqual(cursor.execute.call_args.args[1], [42])
