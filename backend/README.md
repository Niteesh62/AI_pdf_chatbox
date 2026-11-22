# AI PDF Chatbox — Backend

The backend is a Django REST Framework application that stores PDF metadata in PostgreSQL, extracts document text, stores embeddings in pgvector, and generates answers through Groq.

## Technology

- Django 5.2 and Django REST Framework
- Supabase PostgreSQL for Django records and vector embeddings
- LangChain for PDF loading, chunking, retrieval, and prompts
- pgvector for persistent vector storage
- Hugging Face `sentence-transformers/all-MiniLM-L6-v2` embeddings
- Groq `openai/gpt-oss-20b` chat model
- PyPDF for text extraction

## Directory Guide

```text
backend/
├── config/                  # Django settings, WSGI/ASGI, project URLs
├── documents/
│   ├── migrations/
│   ├── services/
│   │   ├── pdf_embedding_service.py
│   │   └── pdf_chat_service.py
│   ├── models.py
│   ├── serializers.py
│   ├── urls.py
│   └── views.py
├── manage.py
└── README.md
```

Runtime-generated folders such as `media/`, `venv/`, and `db.sqlite3` are excluded from source control.

## Prerequisites

- Python 3.10 or newer
- A PostgreSQL database with the pgvector extension enabled
- A Groq API key
- Internet access on the first embedding-model download

## Setup

From the repository root:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Install the Python dependencies:

```powershell
pip install -r requirements.txt
```

Create `backend/.env`:

```env
SECRET_KEY=generate_a_unique_secret_key
DATABASE_URL=postgresql://your_user:your_password@your_host:5432/your_database
DEBUG=True
SECURE_SSL_REDIRECT=False
GROQ_API_KEY=your_groq_api_key
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

Do not commit this file.

Generate a secret key locally with:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Set the generated value as `SECRET_KEY` in Render's environment variables.
Never use the development fallback as a production secret.
For local development, use `DEBUG=True` and `SECURE_SSL_REDIRECT=False` so
Django's HTTP development server does not redirect API requests to HTTPS. In
Render, use `DEBUG=False` and `SECURE_SSL_REDIRECT=True` (or leave the redirect
setting unset, since it defaults to enabled when `DEBUG=False`).

## Render Web Service

Set the Render service's **Root Directory** to `backend` and configure:

| Setting | Value |
|---|---|
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn config.wsgi:application --config gunicorn.conf.py` |
| Health Check Path | `/api/health/` |
| `DEBUG` environment variable | `False` |
| `WEB_CONCURRENCY` environment variable | `1` |
| `GUNICORN_TIMEOUT` environment variable | `180` |

Configure the health-check path in the Render service settings; there is no
Render Blueprint file in this repository. `/api/health/` is a lightweight
process check and does not query the database or call external APIs.
`/api/ready/` checks PostgreSQL and should only be used when the health check
is intended to require database readiness. Render accepts `2xx` or `3xx`
responses to an HTTP health check within five seconds.

Render supplies `PORT` automatically. Do not hard-code it in the dashboard;
Gunicorn binds to `0.0.0.0:$PORT` (falling back to port `10000` only for local
development). Startup logs identify the selected host, port, and whether the
port came from the environment or the local default. Gunicorn command-line
options take precedence over values in `gunicorn.conf.py`; the startup logs
include both the configured and effective bind plus effective worker and
timeout settings.

The CPU embedding model and Groq client are lazily cached once per Gunicorn
worker in `documents/services/llm_embedding.py`. Keep `WEB_CONCURRENCY=1` on
memory-limited instances: each additional worker has its own model cache.
Embedding batches use four chunks, and model loading uses Accelerate's
low-memory path with CPU float16 weights. New PDFs start with pending status;
existing PDFs migrate as unknown, and processing/completed/failed status is
visible in Django admin. A hard
instance kill cannot run Python failure handlers, so a job interrupted by an
OOM restart can remain marked processing. The 400 MB target must be checked
against Render RSS after deployment; local measurements do not guarantee it.

Gunicorn and Django diagnostics are written to standard output/error, which
Render captures in the service logs. They include startup and worker lifecycle
events, URL and database checks, HTTP method, path, resolved endpoint, status,
duration, and process RSS and CPU measurements around requests and PDF/chat
processing. The Django request middleware is the single access-log source; do
not also enable Gunicorn access logging in the Render start command. RSS is read from
`/proc/self/status` and is reported as unavailable on platforms without that
file. Log output redacts configured secrets and common credential-shaped
values; request bodies and query strings are not logged.

To verify Django's port binding locally from PowerShell on Windows:

```powershell
cd backend
$env:PORT = "10000"
python manage.py runserver "0.0.0.0:$env:PORT"
```

In another terminal, confirm that Django responds on the configured port:

```powershell
Invoke-WebRequest http://127.0.0.1:10000/api/health/
```

Gunicorn is not supported on native Windows. The Render production start
command above is the Gunicorn port-binding test; run it in Render or a Linux
environment (including WSL) to verify Gunicorn hooks.

The logs should show `gunicorn_starting`, `gunicorn_master_ready`,
`django_initialization_succeeded`, `django_root_urlconf_configured`, and
`gunicorn_worker_initialized`. If
`gunicorn_starting` is absent, check the Render start command and build logs.
If it appears without `gunicorn_master_ready`, inspect the Gunicorn bind and
port errors. If the master is ready but Django startup or worker initialization
fails, inspect the corresponding traceback. URL and view import errors appear
with the first failing request's 5xx log and traceback; routes are not eagerly
imported during startup to avoid loading PDF/ML dependencies solely for a
diagnostic check. Render's
memory metrics and OOM
events are authoritative for platform kills; a process killed by the platform
cannot log its own shutdown.

Create a Cloudinary account and set its cloud name, API key, and API secret
above. PDF uploads use Cloudinary raw storage; Django reads them from Cloudinary
when processing and downloading. Existing PDFs in local `media/` are not moved
automatically.

At startup, the backend reports whether `DATABASE_URL`, `SECRET_KEY`,
`GROQ_API_KEY`, and the three Cloudinary settings are configured without
printing their values, then checks the database connection. ASGI startup also
checks the Cloudinary API connection.

Set `CORS_ALLOWED_ORIGINS` to a comma-separated list when allowing additional
frontend origins. If it is unset, `http://localhost:5173` and
`http://127.0.0.1:5173` are allowed for development. The deployed frontend
origin `https://ai-pdf-chatbox.vercel.app` is also allowed.

Upload failures return a JSON `stage`, `code`, and `details` so you can
distinguish Cloudinary storage failures from database, PDF parsing, and
embedding/vector-store failures. When the browser receives no HTTP response,
check the API URL, backend availability, HTTPS configuration, and whether the
frontend origin is included in `CORS_ALLOWED_ORIGINS`.

Configure `DATABASE_URL` for your PostgreSQL database and enable pgvector in
Supabase. The embedding service creates the `public.pdf_document_embeddings`
table on first use; the database role must be allowed to create the table and
the vector extension must already be enabled or creatable by that role.

Existing local ChromaDB vectors are not migrated automatically. Reprocess the
PDFs to populate pgvector.

Apply migrations:

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py check
```

Start the API:

```powershell
python manage.py runserver
```

The API is available at `http://127.0.0.1:8000/api/`.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health/` | Check whether the API server is responding |
| `GET` | `/api/ready/` | Check whether the API and database are ready |
| `GET` | `/api/pdfs/` | List uploaded PDFs |
| `POST` | `/api/pdfs/` | Store a PDF and queue background embedding |
| `GET` | `/api/pdfs/{id}/` | Retrieve one PDF |
| `PUT`/`PATCH` | `/api/pdfs/{id}/` | Update PDF fields |
| `DELETE` | `/api/pdfs/{id}/` | Remove the PDF and matching vectors |
| `GET` | `/api/pdfs/{id}/download/` | Download the original file |
| `GET` | `/api/pdfs/{id}/text/` | Read extracted text |
| `POST` | `/api/chat/` | Retrieve document context and answer a question |

### Upload Example

```powershell
curl -X POST "http://127.0.0.1:8000/api/pdfs/" `
  -F "title=Example document" `
  -F "pdf_file=@C:/path/to/document.pdf"
```

The upload returns `202 Accepted` with the stored `document` while embeddings
run in the background. Use the returned `document.id` for chat requests after
the backend log reports `status=completed`.

### Chat Example

```powershell
curl -X POST "http://127.0.0.1:8000/api/chat/" `
  -H "Content-Type: application/json" `
  -d '{"document_id":1,"question":"What is this PDF about?"}'
```

## Processing Behavior

- The maximum request payload is 10 MB.
- Uploaded PDFs are stored in Cloudinary under `pdfs/`.
- PDF text extraction temporarily downloads a copy for processing; the stored
  original remains in Cloudinary.
- PDF text is split into chunks of 1,000 characters with 200-character overlap.
- Embeddings are stored in the `public.pdf_document_embeddings` PostgreSQL
  table, so they persist with the Supabase database.
- Retrieval searches the five most relevant chunks filtered by `document_id`.
- The chat endpoint returns an error for missing fields or unknown document IDs.
- Embedding jobs run in a single in-process worker. A process restart can stop
  queued or running work; use a durable task queue if restart-safe processing is
  required.
- Runtime logs measure memory and CPU around the request and processing stages.
  Use the last `runtime_stage_started` entry plus Render's memory graph to
  identify a stage interrupted by an OOM restart.

Scanned PDFs and image-only documents require OCR before text can be indexed; OCR is not implemented by this backend.

## Useful Django Commands

```powershell
python manage.py runserver
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py check
```

## Troubleshooting

- **Missing API key:** Add `GROQ_API_KEY` to `backend/.env`, then restart Django.
- **PostgreSQL/pgvector failure:** Verify `DATABASE_URL`, confirm the Supabase `vector` extension is enabled, and check that the database role can access the `public` schema.
- **PDF upload failure:** Confirm the file is a PDF and is no larger than 10 MB.
- **No embeddings found:** Upload/process the PDF again and inspect the Django terminal for ingestion errors.
- **CORS error:** The backend allows `http://localhost:5173` in development.
- **Model download or startup failure:** Check internet access and available disk space.

## Production Checklist

- Replace the Django secret key and enable environment-based configuration.
- Set `DEBUG = False` and restrict `ALLOWED_HOSTS`.
- Restrict CORS and configure HTTPS and upload storage.
- Keep database credentials, Cloudinary credentials, and the Groq key outside
  source control.
- Use Supabase PostgreSQL with pgvector for persistent records and embeddings, and Cloudinary for uploaded PDFs.
- Add authentication and authorization before exposing document APIs.
