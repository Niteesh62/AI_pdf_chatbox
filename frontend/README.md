# AI PDF Chatbox — Frontend

The frontend is a React single-page application for uploading PDFs and
chatting with uploaded documents.

## Technology

- React 19
- Vite 8
- Axios
- Lucide React
- Vanilla CSS
- Oxlint

## Setup

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

The backend should be running at `http://127.0.0.1:8000`.

## API Configuration

The Axios instance is defined in `src/api/axiosInstance.js`.

For local development:

```javascript
baseURL: "http://localhost:8000/api/",
```

For a deployed backend:

```javascript
baseURL: "https://your-backend.example.com/api/",
```

The backend must allow the frontend origin through
`CORS_ALLOWED_ORIGINS`.

An HTTPS frontend must use an HTTPS backend URL.

## Directory Guide

```text
frontend/
├── src/
│   ├── api/
│   │   └── axiosInstance.js
│   ├── Components/
│   │   ├── ChatWindow/
│   │   ├── Message/
│   │   ├── Pdf_uploader/
│   │   └── Sidebar/
│   ├── App.jsx
│   ├── App.css
│   └── main.jsx
├── package.json
├── vite.config.js
└── README.md
```

## Available Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Start the Vite development server |
| `npm run build` | Create a production build in `dist/` |
| `npm run preview` | Preview the production build |
| `npm run lint` | Run Oxlint |

## Application Flow

1. `Pdf_uplaoder.jsx` collects the PDF and title.
2. The PDF is sent to `POST /api/pdfs/`.
3. The backend returns the uploaded document record.
4. `App.jsx` creates a React chat session for that document.
5. `ChatWindow.jsx` sends questions to `POST /api/chat/`.
6. The answer is stored in the active chat's React state.
7. `Sidebar.jsx` switches or creates chat sessions.

## Upload Validation

The frontend:

- Requires a selected file.
- Accepts PDF files.
- Sends the file as multipart form data.
- Displays backend validation and network errors.

The backend additionally validates the file extension and 10 MB size limit.

## Chat State

Chat sessions and messages are stored in React state only.

There is no local-storage or backend conversation-persistence implementation.
Refreshing the browser clears all chat history. Uploading another PDF creates
a new in-memory chat session.

## Development Checks

```powershell
npm run lint
npm run build
```

Fix lint or build errors before deploying.

## Production Deployment

```powershell
npm run build
```

Deploy the generated `dist/` directory to a static host.

Before deployment:

1. Set the Axios base URL to the deployed HTTPS backend.
2. Set Django `CORS_ALLOWED_ORIGINS` to the exact frontend origin.
3. Build after changing the API URL.
4. Never place Groq or Django secrets in frontend code or browser environment variables.

## Troubleshooting

### Network error

- Confirm Django is running.
- Confirm the Axios base URL is correct.
- Confirm the frontend origin is allowed by CORS.

### 500 upload response

Open the Django terminal. Common causes include missing migrations,
Cloudinary credentials, database connectivity, or a PDF with no extractable
text.

### Chat returns no answer

The PDF embedding job may still be running. Wait for processing to complete
and verify `/api/pdfs/{id}/` returns a completed embedding status.
