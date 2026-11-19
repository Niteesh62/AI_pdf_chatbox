# AI PDF Chatbox — Backend

The backend is a Django REST Framework application that stores PDF metadata, extracts document text, creates embeddings in ChromaDB, and generates answers through Groq.

## Technology

- Django 5.2 and Django REST Framework
- MySQL for Django records
- LangChain for PDF loading, chunking, retrieval, and prompts
- ChromaDB for persistent vector storage
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

Runtime-generated folders such as `media/`, `vectorstore/`, `venv/`, and `db.sqlite3` are excluded from source control.

## Prerequisites

- Python 3.10 or newer
- MySQL 8 or compatible server
- MySQL build libraries required by `mysqlclient`
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
GROQ_API_KEY=your_groq_api_key
CORS_ALLOWED_ORIGINS=http://localhost:5173
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

Create a Cloudinary account and set its cloud name, API key, and API secret
above. PDF uploads use Cloudinary raw storage; Django reads them from Cloudinary
when processing and downloading. Existing PDFs in local `media/` are not moved
automatically.

At startup, the backend reports whether `DATABASE_URL`, `SECRET_KEY`,
`GROQ_API_KEY`, and the three Cloudinary settings are configured, then checks
the database and Cloudinary API connection. These logs never print credential
values.

Set `CORS_ALLOWED_ORIGINS` to a comma-separated list when allowing additional
frontend origins. If it is unset, the development origin
`http://localhost:5173` is used.

Create the MySQL database:

```sql
CREATE DATABASE pdf_chatbox CHARACTER SET utf8mb4;
```

Review `config/settings.py` and configure the MySQL `NAME`, `USER`, `PASSWORD`, `HOST`, and `PORT` values for the local environment. Move real credentials out of source code before deployment.

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
| `POST` | `/api/pdfs/` | Upload a PDF and build embeddings |
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

Use the returned `document.id` for chat requests.

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
- ChromaDB data is stored under `backend/vectorstore/`.
- Retrieval searches the five most relevant chunks filtered by `document_id`.
- The chat endpoint returns an error for missing fields or unknown document IDs.

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
- **MySQL connection failure:** Verify MySQL is running and the credentials and database name in `config/settings.py` are correct.
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
- Use persistent storage for MySQL, uploaded PDFs, and ChromaDB.
- Add authentication and authorization before exposing document APIs.
