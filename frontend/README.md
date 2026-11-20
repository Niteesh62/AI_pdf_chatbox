# AI PDF Chatbox — Frontend

The frontend is a React 19 single-page application built with Vite. It provides PDF selection and upload, conversation history, chat messages, and clear/new-chat controls.

## Technology

- React 19
- Vite
- Axios
- Lucide React icons
- Vanilla CSS

## Directory Guide

```text
frontend/chatbox/
├── public/
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
└── README.md
```

## Prerequisites

- Node.js 20.19 or newer
- npm
- The Django backend running at `http://127.0.0.1:8000`

## Setup

From the repository root:

```powershell
cd frontend/chatbox
npm install
npm run dev
```

Open `http://localhost:5173/`.

The API base URL defaults to the local backend and can be overridden with the
Vite environment variable `VITE_API_BASE_URL`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/
```

Set it to the deployed backend URL for production builds. The backend must
allow the frontend's exact origin in `CORS_ALLOWED_ORIGINS`; an HTTPS frontend
must use an HTTPS API.

## Available Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Start the Vite development server |
| `npm run build` | Create a production build in `dist/` |
| `npm run preview` | Preview the production build locally |
| `npm run lint` | Run Oxlint across the project |

## Application Flow

1. `App.jsx` creates a new conversation after a successful upload.
2. `Pdf_uploader.jsx` validates the file and posts it to `/api/pdfs/`.
3. `ChatWindow.jsx` posts questions and the selected document ID to `/api/chat/`.
4. `Sidebar.jsx` lists and switches local chat sessions.
5. The application state is reset on a full page refresh.

## Upload Restrictions

- `.pdf` extension or PDF MIME type
- Maximum file size of 10 MB
- The backend also validates PDF uploads

A scanned or image-only PDF may upload successfully but cannot be queried until text extraction through OCR is available.

## Development Notes

- Keep API requests behind `src/api/axiosInstance.js` so base URL and headers remain consistent.
- Preserve the `document_id` returned by the upload endpoint when changing chat state.
- Handle loading, backend validation, network, and empty-answer states in the relevant components.
- Run lint and a production build before submitting a change:

```powershell
npm run lint
npm run build
```

## Production Configuration

Before deployment:

1. Build the app with `npm run build`.
2. Set the Axios base URL to the deployed API URL.
3. Configure the backend CORS origin to match the deployed frontend domain.
4. Serve the generated `dist/` directory with HTTPS through a static web host or reverse proxy.

Do not store Groq keys or Django credentials in frontend environment variables or browser code.
