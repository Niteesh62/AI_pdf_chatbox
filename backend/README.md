# AI PDF Chatbox — Backend

The backend is a Django REST Framework API for PDF ingestion, vector
retrieval, and Groq chat answers.

## Technology

- Django 5.2
- Django REST Framework
- PostgreSQL and `pgvector`
- FastEmbed 0.9.1
- ONNX Runtime
- LangChain and LangChain Groq
- PyPDF
- Cloudinary
- Gunicorn

## Directory Guide

```text
backend/
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── middleware.py
│   ├── logging_config.py
│   └── runtime_diagnostics.py
├── documents/
│   ├── migrations/
│   ├── services/
│   │   ├── llm_embedding.py
│   │   ├── pdf_embedding_jobs.py
│   │   ├── pdf_embedding_service.py
│   │   └── pdf_chat_service.py
│   ├── models.py
│   ├── serializers.py
│   ├── urls.py
│   └── views.py
├── manage.py
├── requirements.txt
└── gunicorn.conf.py
```

## Environment Variables

Create `backend/.env`:

```env
SECRET_KEY=replace_with_a_secure_random_key
DEBUG=True
DATABASE_URL=postgresql://username:password@host:5432/database
GROQ_API_KEY=your_groq_api_key
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_cloudinary_api_key
CLOUDINARY_API_SECRET=your_cloudinary_api_secret
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
SECURE_SSL_REDIRECT=False
ALLOWED_HOSTS=localhost,127.0.0.1
```

For production:

- Set `DEBUG=False`.
- Set a unique `SECRET_KEY`.
- Set `DATABASE_URL` to the production PostgreSQL database.
- Set `CORS_ALLOWED_ORIGINS` to the exact frontend origin.
- Set `ALLOWED_HOSTS` to the deployed backend domain and localhost if needed.
- Enable HTTPS and configure `SECURE_SSL_REDIRECT` appropriately.

## Setup

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py runserver
```

The API is available at `http://127.0.0.1:8000/api/`.

## Database Setup

The Django database stores PDF metadata and text. Embeddings are stored in a
separate table named `public.pdf_document_embeddings`.

Enable `pgvector`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

The vector table is created or verified automatically during embedding
ingestion. It requires vectors with 384 dimensions.

Apply migrations whenever models or migrations change:

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations documents
```

## API Routes

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/health/` | Lightweight liveness check |
| `GET` | `/api/ready/` | Database readiness check |
| `GET` | `/api/pdfs/` | List PDFs |
| `POST` | `/api/pdfs/` | Upload a PDF |
| `GET` | `/api/pdfs/{id}/` | Retrieve a PDF |
| `DELETE` | `/api/pdfs/{id}/` | Delete a PDF and its embeddings |
| `GET` | `/api/pdfs/{id}/download/` | Download the PDF |
| `GET` | `/api/pdfs/{id}/text/` | Read extracted text |
| `POST` | `/api/chat/` | Ask a document-specific question |

## Upload and Ingestion

The upload endpoint:

1. Validates the multipart form data.
2. Saves the PDF record and Cloudinary file.
3. Adds a background embedding job.
4. Returns HTTP 202 while processing continues.

The embedding worker:

1. Downloads the PDF from Cloudinary to temporary storage.
2. Checks the `%PDF-` file header.
3. Loads pages with `PyPDFLoader`.
4. Cleans the extracted text.
5. Saves extracted text on the PDF record.
6. Splits text into 1,000-character chunks with 200-character overlap.
7. Loads the FastEmbed model.
8. Generates 384-dimensional vectors in batches of four chunks.
9. Atomically replaces the document's existing embeddings.
10. Verifies the stored row count.

The model is cached once per Django process. Status changes are persisted to
the `embedding_status` field.

## Embedding Configuration

The default model is:

```text
sentence-transformers/all-MiniLM-L6-v2
```

The model name may be changed through `HF_EMBEDDING_MODEL` or Django
`PDF_EMBEDDING_MODEL`, but the replacement must also return exactly
384 dimensions because the database table is configured for that size.

## Chat Retrieval

`POST /api/chat/` requires:

```json
{
  "document_id": 17,
  "question": "Summarize this PDF"
}
```

The chat service:

1. Validates the document ID.
2. Checks that the document exists.
3. Counts stored embeddings.
4. Embeds the question.
5. Searches only the selected document's vectors.
6. Builds a context from the closest chunks.
7. Sends the context to Groq.
8. Returns the answer as JSON.

The chat model is `openai/gpt-oss-20b` with temperature `0`.

## Cloudinary

PDF files use Cloudinary raw storage. Deleting a Django PDF record also:

- Deletes matching vector rows in one database transaction.
- Deletes the Django record.
- Requests deletion of the Cloudinary file after the database transaction.

Cloudinary credential and file-storage failures are handled in the upload and
deletion logs.

## Tests

Run the Django test suite:

```powershell
python manage.py test
```

The tests cover the shared embedding-model cache and PDF embedding job status
transitions.

## Production

Example Gunicorn command:

```text
gunicorn config.wsgi:application --config gunicorn.conf.py
```

Set `WEB_CONCURRENCY=1` on memory-limited hosts. FastEmbed and the Groq client
are cached independently by every Gunicorn worker process.

Recommended environment settings:

```env
DEBUG=False
SECURE_SSL_REDIRECT=True
WEB_CONCURRENCY=1
GUNICORN_TIMEOUT=180
```

## Troubleshooting

### Missing migration column

```powershell
python manage.py showmigrations documents
python manage.py migrate
```

### PyMySQL missing at startup

Install the backend requirements:

```powershell
python -m pip install -r requirements.txt
```

### PDF has no extractable text

This is normally an image-only or scanned PDF. OCR is not implemented.

### No vector rows are stored

Check the Django logs for the following stages:

- `cloudinary_download`
- `pdf_extraction`
- `text_extraction`
- `chunk_creation`
- `embedding_model_load`
- `embedding_batch`
- `supabase_embedding_insert`
- `embedding_verification`

### Chat cannot find the PDF

Confirm the upload response returned a valid `document_id` and the database
record still exists.

## Diagnostics

The application writes structured runtime information to standard output:

- Django startup configuration
- Database connection status
- HTTP method, path, status, and duration
- Cloudinary and PDF processing stages
- Embedding model loading
- Vector storage and verification
- Groq chat requests
- Exceptions with tracebacks

Secrets are redacted from standard diagnostics. Request bodies and
query strings are not logged.
