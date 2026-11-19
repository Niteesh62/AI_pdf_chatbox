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
GROQ_API_KEY=your_groq_api_key
```

Do not commit this file.

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
- Uploaded PDFs are stored under `media/pdfs/` using Django's file storage.
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
- Keep database credentials and the Groq key outside source control.
- Use persistent storage for MySQL, uploaded PDFs, and ChromaDB.
- Add authentication and authorization before exposing document APIs.
