# AI PDF Chatbox

AI PDF Chatbox is a full-stack PDF question-answering application.

Users can upload a PDF, wait for the document to be processed, and ask
questions based only on the uploaded document. The application uses
retrieval-augmented generation (RAG):

1. Extract text from the PDF.
2. Split the text into overlapping chunks.
3. Create a 384-dimensional embedding for each chunk with FastEmbed.
4. Store the chunks and embeddings in a PostgreSQL `pgvector` table.
5. Embed the user's question.
6. Find the closest matching chunks for the selected PDF.
7. Send those chunks and the question to Groq.
8. Return a document-based answer in the React chat interface.

## Features

- PDF upload through the React interface
- File validation and Cloudinary storage
- Background PDF ingestion
- PDF text extraction with PyPDF
- Text chunking with LangChain
- FastEmbed/ONNX embeddings
- PostgreSQL vector search with `pgvector`
- Groq chat answers
- Document download and extracted-text endpoints
- Multiple local chat sessions per uploaded document
- Django migration and database diagnostics

## Technology

### Frontend

- React 19
- Vite 8
- Axios
- Lucide React
- Vanilla CSS

### Backend

- Python 3.11
- Django 5.2
- Django REST Framework
- PostgreSQL and `pgvector`
- FastEmbed 0.9.1
- ONNX Runtime
- LangChain
- PyPDF
- Groq through LangChain Groq
- Cloudinary raw-file storage
- Gunicorn for production

## Project Structure

```text
AI_pdf_chatbox/
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── Components/
│   │   ├── App.jsx
│   │   └── main.jsx
│   └── package.json
├── backend/
│   ├── config/                  # Django settings, URLs, logging
│   ├── documents/
│   │   ├── migrations/
│   │   ├── services/
│   │   │   ├── llm_embedding.py
│   │   │   ├── pdf_embedding_service.py
│   │   │   ├── pdf_embedding_jobs.py
│   │   │   └── pdf_chat_service.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── manage.py
│   └── requirements.txt
├── .gitignore
└── README.md
```

## How Processing Works

### PDF upload

The frontend posts `title` and `pdf_file` to `POST /api/pdfs/`.
Django saves the PDF record and stores the file in Cloudinary. Uploading
returns HTTP 202 with the document ID and leaves the embedding status at
`pending`.

### PDF ingestion

A background worker downloads the Cloudinary PDF to temporary storage,
extracts its pages with PyPDF, cleans the text, and creates chunks of
approximately 1,000 characters with 200 characters of overlap.

FastEmbed loads `sentence-transformers/all-MiniLM-L6-v2` and creates
384-dimensional normalized vectors. The vectors are stored in the
`public.pdf_document_embeddings` PostgreSQL table and verified after insertion.

Possible embedding statuses are:

- `pending`
- `processing`
- `completed`
- `failed`

### Asking questions

The frontend sends `document_id` and `question` to `POST /api/chat/`.
The backend embeds the question, searches only embeddings belonging to that
document, retrieves the most relevant chunks, and passes them to
`openai/gpt-oss-20b` through Groq. The model is instructed to answer from the
PDF context and to say when the answer is not present.

## Prerequisites

- Python 3.11
- Node.js 20.19 or newer
- npm
- PostgreSQL with the `pgvector` extension
- Groq API key
- Cloudinary account
- Internet access for the first FastEmbed model download

## Backend Setup

Open a terminal in the repository root:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

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
```

Do not commit `.env`.

Generate a Django secret key:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Enable `pgvector` in PostgreSQL. For Supabase, run this in the SQL editor:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Apply migrations:

```powershell
python manage.py migrate
python manage.py check
python manage.py runserver
```

The backend will run at `http://127.0.0.1:8000`.

## Frontend Setup

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

The frontend API URL is configured in
`frontend/src/api/axiosInstance.js`. For local development, use:

```javascript
baseURL: "http://localhost:8000/api/",
```

For a deployed backend, use:

```javascript
baseURL: "https://your-backend.example.com/api/",
```

You can alternatively change this file to read a Vite environment variable
such as `VITE_API_BASE_URL` if you want one frontend build to support multiple
deployment environments.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health/` | Check whether Django is running |
| `GET` | `/api/ready/` | Check database readiness |
| `GET` | `/api/pdfs/` | List uploaded PDFs |
| `POST` | `/api/pdfs/` | Upload a PDF and queue embedding |
| `GET` | `/api/pdfs/{id}/` | Retrieve a PDF record |
| `DELETE` | `/api/pdfs/{id}/` | Delete a PDF, its file, and embeddings |
| `GET` | `/api/pdfs/{id}/download/` | Download the PDF |
| `GET` | `/api/pdfs/{id}/text/` | Get extracted PDF text |
| `POST` | `/api/chat/` | Ask a question about a PDF |

Example chat request:

```json
{
  "document_id": 17,
  "question": "What is this document about?"
}
```

Example chat response:

```json
{
  "document_id": 17,
  "question": "What is this document about?",
  "answer": "The document describes...",
  "status": "success"
}
```

## Frontend Behavior

- Chat conversations are stored in React state for the current browser session.
- Refreshing or closing the page clears conversation history.
- A new chat starts a conversation for a newly uploaded PDF.
- Switching chats restores the document and messages associated with that chat.
- Clearing a chat resets only the messages for the active conversation.
- The sidebar does not persist document history to local storage or a database.

## Upload Requirements

- File size must not exceed 10 MB.
- The file must have a PDF extension or PDF content type.
- Image-only or scanned PDFs require OCR.
- OCR is not currently implemented.
- PDFs with extractable text are required for embedding generation.

## Development Commands

### Backend

```powershell
cd backend
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py test
python manage.py runserver
```

### Frontend

```powershell
cd frontend
npm run dev
npm run build
npm run lint
npm run preview
```

## Deployment

### Django backend

Use a PostgreSQL database that has `pgvector` enabled. Configure these
environment variables:

- `SECRET_KEY`
- `DATABASE_URL`
- `GROQ_API_KEY`
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`
- `CORS_ALLOWED_ORIGINS`
- `DEBUG=False`

Run migrations during deployment:

```powershell
python manage.py migrate
```

Use a production server such as Gunicorn:

```text
gunicorn config.wsgi:application --config gunicorn.conf.py
```

Set `WEB_CONCURRENCY=1` if the hosting plan has limited memory. FastEmbed
loads a model into each Gunicorn worker process.

### React frontend

Build the frontend:

```powershell
cd frontend
npm run build
```

Deploy the generated `frontend/dist/` directory to Vercel, Netlify, or another
static host. Set the Axios API URL to the HTTPS backend URL and configure
`CORS_ALLOWED_ORIGINS` on Django with the exact deployed frontend origin.

## Security and Maintenance

- Never commit `.env`, database credentials, API keys, Cloudinary secrets, or
  private PDF data.
- Use HTTPS for deployed frontend and backend origins.
- Keep Django's production `DEBUG=False`.
- Apply migrations before starting a new application release.
- Use one Gunicorn worker on memory-limited hosts because model loading is
  process-local.
- Monitor `/api/ready/` and hosting-provider memory metrics.
- `/api/health/` is for server liveness; `/api/ready/` checks database readiness.

## Troubleshooting

### Upload returns 500

Check the Django terminal. The most common causes are missing migrations,
missing Cloudinary credentials, database connection failure, or a PDF that
contains no extractable text.

Apply migrations after model changes:

```powershell
python manage.py migrate
```

### Migration reports a missing column

Run `python manage.py showmigrations documents` and
`python manage.py migrate`.

### No embeddings are created

- Confirm the PDF has searchable text.
- Confirm the `public.pdf_document_embeddings` table exists.
- Confirm `pgvector` is installed and enabled.
- Check the Django logs for extraction or model-loading errors.

### Chat says no embeddings were found

Wait for the background embedding job to finish, or upload the PDF again.
Image-only PDFs also cannot generate embeddings without OCR.

### Frontend cannot connect to the backend

- Confirm Django is running on port 8000.
- Confirm the Axios base URL is correct.
- Confirm CORS allows `http://localhost:5173`.
- For HTTPS frontend deployments, use an HTTPS backend URL.

## Component Documentation

- [Backend documentation](backend/README.md)
- [Frontend documentation](frontend/README.md)
