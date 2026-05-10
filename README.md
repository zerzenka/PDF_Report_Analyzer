# PDF Report Analyzer

Internal HR tool for **scanned employee performance/health PDFs**. Uploads are analyzed with OCR, fields are extracted and matched to employees, and results are stored for review and export—replacing the older CLI batch flow that wrote Excel files only.

## Tech stack (full-scale app)

| Layer | Stack |
|--------|--------|
| Frontend | React (Vite), react-router-dom, axios *(UI scaffold per project plan)* |
| Backend | Django 5.x, Django REST Framework |
| Database | PostgreSQL *(recommended)*; SQLite used locally if `DATABASE_URL` is unset |
| Jobs | Celery + Redis *(optional in dev—see below)* |
| Real-time | Django Channels (WebSockets for job progress) |
| OCR | Azure Document Intelligence *(credentials via env)* |
| Auth | JWT (`djangorestframework-simplejwt`) |

Detailed architecture, APIs, and decisions: [`CLAUDE_CONTEXT.md`](CLAUDE_CONTEXT.md).

## Prerequisites

- Python 3.11+ (recommended)
- Node.js 18+ *(when the `frontend/` app is present)*
- PostgreSQL *(production-like local setup)* or omit `DATABASE_URL` for SQLite
- Redis *(only if you run Celery with a real broker instead of eager/in-process tasks)*

## Environment variables

Create a `.env` in `backend/` (or export in your shell). Never commit secrets.

```env
# Django
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database — omit for local SQLite
DATABASE_URL=postgresql://user:pass@localhost:5432/pdf_analyzer

# Azure Document Intelligence (OCR)
AZURE_DI_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_DI_KEY=

# Celery / Redis (when using async workers)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

JWT lifetimes are configured in Django settings unless you extend them via code.

## Run locally

**Backend**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows — on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

API defaults to `http://127.0.0.1:8000/` (adjust if you use another host/port).

**Celery + Redis** *(when async processing and a live broker are enabled—see `config/settings.py`)*

```bash
docker run -p 6379:6379 redis:alpine
```

```bash
cd backend
celery -A config worker --loglevel=info
```

**Frontend** *(once `frontend/` exists)*

```bash
cd frontend
npm install
npm run dev
```

## Active development

This repository is **under active development**: APIs, OCR wiring, Channels, and the React UI may be incomplete or change. Treat [`CLAUDE_CONTEXT.md`](CLAUDE_CONTEXT.md) as the target architecture; the legacy FastAPI/CLI pilot remains in the repo for reference.
