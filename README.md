# AI PDF Chatbox

AI PDF Chatbox is a full-stack application that lets a user upload a PDF, indexes the document text, and asks questions about that document using retrieval-augmented generation (RAG).

- **Frontend:** React 19, Vite, Axios, and Lucide React
- **Backend:** Django REST Framework
- **Data:** MySQL for document metadata and ChromaDB for vector embeddings
- **AI:** Hugging Face `all-MiniLM-L6-v2` embeddings and a Groq chat model

> The first PDF upload may take longer while the embedding model is downloaded and initialized.

## How It Works

1. The frontend sends a PDF and title to the Django API.
2. Django stores the file and extracts its text with PyPDF.
3. The text is split into overlapping chunks and stored with document metadata in ChromaDB.
4. A question is matched against chunks belonging to the selected document.
5. The relevant context is sent to Groq, which generates a document-based answer.

## Repository Layout

```text
AI_pdf_chatbox/
├── backend/                 # Django REST API
│   ├── config/              # Django project settings and URLs
│   ├── documents/           # PDF models, APIs, and RAG services
│   ├── manage.py
│   └── README.md
├── frontend/chatbox/        # React user interface
│   ├── src/
│   └── README.md
├── .gitignore
└── README.md
```

Component-specific setup and commands are documented in:

- [Backend README](backend/README.md)
- [Frontend README](frontend/chatbox/README.md)

## Prerequisites

- Windows PowerShell or a compatible terminal
- Python 3.10+ (Python 3.11 is used by the checked-in virtual environment)
- Node.js 20.19+ and npm
- MySQL 8 or a compatible MySQL server
- A Groq API key
- Internet access for initial model downloads

## Quick Start

Run the backend and frontend in separate terminals.

### 1. Configure and start the backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install django djangorestframework django-cors-headers mysqlclient python-dotenv
pip install langchain langchain-community langchain-core langchain-huggingface langchain-chroma langchain-groq
pip install pypdf chromadb sentence-transformers
```

Create `backend/.env`:

```env
GROQ_API_KEY=your_groq_api_key
```

Create the database in MySQL, update `backend/config/settings.py` with local database credentials, and run migrations:

```sql
CREATE DATABASE pdf_chatbox;
```

```powershell
python manage.py migrate
python manage.py runserver
```

The API starts at `http://127.0.0.1:8000/api/`.

### 2. Start the frontend

```powershell
cd frontend/chatbox
npm install
npm run dev
```

Open `http://localhost:5173/`.

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health/` | Check whether the API server is responding |
| `GET` | `/api/ready/` | Check whether the API and database are ready |
| `GET` | `/api/pdfs/` | List uploaded PDFs |
| `POST` | `/api/pdfs/` | Upload a PDF and create embeddings |
| `GET` | `/api/pdfs/{id}/` | Get one PDF record |
| `DELETE` | `/api/pdfs/{id}/` | Delete a PDF and its embeddings |
| `GET` | `/api/pdfs/{id}/download/` | Download the uploaded PDF |
| `GET` | `/api/pdfs/{id}/text/` | Read extracted PDF text |
| `POST` | `/api/chat/` | Ask a question about a PDF |

Example chat request:

```json
{
  "document_id": 1,
  "question": "What is this document about?"
}
```

Example chat response:

```json
{
  "document_id": 1,
  "question": "What is this document about?",
  "answer": "The document discusses...",
  "status": "success"
}
```

## Using the Application

1. Open the frontend and choose a PDF.
2. PDFs must be searchable text documents and cannot exceed 10 MB.
3. Select **Upload and Start Chat**.
4. Ask questions in the chat window.
5. Use the sidebar to switch conversations or start a new chat.

Conversation history is kept in browser component state for the current session. It is not persisted after a page refresh unless persistence is added.

## Development Commands

From the repository root:

```powershell
# Backend
cd backend
python manage.py runserver

# Frontend
cd frontend/chatbox
npm run dev
npm run build
npm run lint
```

For Django operations, use:

```powershell
cd backend
python manage.py makemigrations
python manage.py migrate
python manage.py check
```

## Configuration and Security

- Never commit API keys, database passwords, Django secrets, uploaded PDFs, or vector database files.
- `.env`, virtual environments, `media/`, `vectorstore/`, database files, and `node_modules/` are excluded through `.gitignore`.
- Replace hard-coded development credentials and the Django `SECRET_KEY` before deployment.
- Set appropriate `ALLOWED_HOSTS`, CORS origins, database environment variables, HTTPS settings, and file-storage limits for production.
- Scanned PDFs may require OCR because text extraction does not currently run OCR.