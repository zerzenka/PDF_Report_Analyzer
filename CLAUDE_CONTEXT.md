# PDF Report Analyzer — project context for AI assistants

## What this project is

An internal HR tool that processes **scanned PDF reports** (employee performance/health
reports) and extracts structured data from them. The pilot was built with FastAPI and
runs as a command-line batch processor. This file describes the **full-scale rewrite**
being built with Django, React, and PostgreSQL.

The original pilot repo: https://github.com/zerzenka/PDF_Report_Analyzer

---

## Pilot app — what exists today

### Tech stack (pilot)
- **Framework:** FastAPI + Uvicorn
- **PDF extraction:** pdfplumber, pdfminer.six, pdf2image, pypdfium2
- **OCR:** pytesseract (slow — ~2 min per PDF, CPU only)
- **ML attempt:** easyocr, torch, torchvision, torchaudio (abandoned — GPU incompatible)
- **Data matching:** rapidfuzz (fuzzy match extracted names to employees)
- **Employee data:** loaded from `employees.xlsx` (openpyxl/pandas)
- **Output:** `batch_results.xlsx` written to disk
- **Entry point:** `run_export_batch.py` calls `app/services/export_batch.py`

### Folder structure (pilot)
```
PDF_Report_Analyzer/
├── app/
│   └── services/
│       └── export_batch.py       # Core logic — reusable in Django
├── batches/
│   └── test_batch_1/             # Sample input PDFs
├── employees.xlsx                # Employee master list
├── batch_results.xlsx            # Output — to be replaced by DB
├── run_export_batch.py           # CLI entry point
├── requirements.txt              # FastAPI + PDF libs
├── requirements-full.txt         # Same + extras
└── requirements-ml.txt           # torch, easyocr, pymupdf, rapidfuzz, pandas, openpyxl
```

### What the pilot does (step by step)
1. Reads a folder of incoming scanned PDF files
2. Converts each PDF page to an image (pdf2image / pypdfium2)
3. Runs OCR on each page image (pytesseract)
4. Extracts structured fields from the OCR text (employee name, scores, period, etc.)
5. Fuzzy-matches the extracted employee name to `employees.xlsx` (rapidfuzz)
6. Writes all results to `batch_results.xlsx`

### Known problems with the pilot
- **~2 minutes per PDF** — pytesseract is single-threaded and CPU-only
- **No GPU support** — RTX 5070 Ti (Blackwell, sm_120) is incompatible with stable
  PyTorch as of May 2026. Stable PyTorch only supports up to sm_90 (Hopper).
  easyocr was tried and abandoned for this reason.
- **No UI** — runs only from the command line
- **No database** — results live in Excel files on a shared network drive
- **No auth** — no user management
- **Hardcoded paths** — `SHARED_ROOT = r"I:\60 - Services\30 - BI\010 - Shared\HP_app"`

---

## Full-scale app — target architecture

### Tech stack
| Layer | Technology |
|---|---|
| Frontend | React (Vite), react-router-dom, axios |
| Backend | Django 5.x + Django REST Framework |
| Database | PostgreSQL |
| Task queue | Celery + Redis |
| Real-time | Django Channels (WebSocket for job progress) |
| OCR | Azure Document Intelligence (replaces pytesseract) |
| Auth | JWT via djangorestframework-simplejwt |
| File storage | Django MEDIA_ROOT (local for dev, S3-compatible for prod) |
| Dev environment | Cursor (VS Code-based), Windows 11 |
| GPU | NVIDIA RTX 5070 Ti 12GB — NOT usable yet with PyTorch stable |

### Why Azure Document Intelligence for OCR
- pytesseract: CPU only, ~2 min/PDF, no GPU support
- easyocr/doctr/surya: all depend on PyTorch, which doesn't support sm_120 (RTX 5070 Ti)
  in stable builds as of May 2026
- Azure Document Intelligence: cloud API, ~2–5 sec/PDF, no GPU required, returns
  structured JSON with field positions, high accuracy on scanned documents
- The OCR layer is intentionally abstracted in a service class so it can be swapped
  to a local GPU model once PyTorch stable supports sm_120

---

## Django project structure (target)

```
backend/
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── celery.py
│   └── asgi.py                   # Django Channels entry point
├── apps/
│   ├── documents/                # Core app
│   │   ├── models.py             # AnalysisJob, ExtractedField
│   │   ├── serializers.py
│   │   ├── views.py              # DRF API views
│   │   ├── urls.py
│   │   ├── tasks.py              # Celery tasks
│   │   ├── consumers.py          # WebSocket consumers
│   │   └── services/
│   │       ├── ocr_service.py    # Azure Document Intelligence wrapper
│   │       └── extraction.py    # Field extraction logic (ported from pilot)
│   ├── employees/                # Employee management
│   │   ├── models.py             # Employee (replaces employees.xlsx)
│   │   ├── serializers.py
│   │   └── views.py
│   └── reports/                  # Report output
│       ├── models.py             # Report (replaces batch_results.xlsx)
│       ├── serializers.py
│       └── views.py
└── manage.py

frontend/
├── src/
│   ├── components/
│   │   ├── DocumentList.jsx      # Left panel — list with status badges
│   │   ├── DetailPanel.jsx       # Right panel — extracted data view
│   │   ├── UploadButton.jsx
│   │   └── StatusBadge.jsx
│   ├── pages/
│   │   ├── DocumentsPage.jsx     # Main Outlook-style layout
│   │   ├── EmployeesPage.jsx
│   │   └── ReportsPage.jsx
│   ├── hooks/
│   │   └── useJobStatus.js       # WebSocket hook for live progress
│   ├── api/
│   │   └── client.js             # axios instance with JWT interceptor
│   └── App.jsx
└── vite.config.js
```

---

## Database models

### AnalysisJob
Tracks each uploaded PDF through its lifecycle.

```python
class AnalysisJob(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('error', 'Error'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    file = models.FileField(upload_to='uploads/')
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    employee = models.ForeignKey('employees.Employee', null=True, blank=True,
                                  on_delete=models.SET_NULL)
    page_count = models.IntegerField(null=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
```

### Employee
Replaces `employees.xlsx`. Import the existing Excel on first run.

```python
class Employee(models.Model):
    employee_id = models.CharField(max_length=50, unique=True)  # e.g. EMP-0412
    full_name = models.CharField(max_length=255)
    department = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
```

### Report / ExtractedField
Replaces `batch_results.xlsx`. Stores what was pulled out of each PDF.

```python
class Report(models.Model):
    job = models.OneToOneField(AnalysisJob, on_delete=models.CASCADE)
    period = models.CharField(max_length=50)          # e.g. "Q1 2024"
    raw_ocr_text = models.TextField()                 # full OCR dump for debugging
    created_at = models.DateTimeField(auto_now_add=True)

class ExtractedField(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                                related_name='fields')
    label = models.CharField(max_length=100)          # e.g. "Attendance"
    value = models.CharField(max_length=255)          # e.g. "96%"
    confidence = models.FloatField(null=True)         # from Azure API
```

---

## API endpoints (Django REST Framework)

```
POST   /api/documents/upload/          Upload a PDF → creates AnalysisJob, queues Celery task
GET    /api/documents/                 List all jobs (with status, employee, date)
GET    /api/documents/<uuid>/          Job detail + extracted fields
GET    /api/documents/<uuid>/export/   Download results as Excel
POST   /api/documents/<uuid>/rerun/    Re-queue a failed job

GET    /api/employees/                 List employees
POST   /api/employees/import/          Import from Excel

GET    /api/reports/                   List all completed reports

POST   /api/auth/token/                Get JWT token
POST   /api/auth/token/refresh/        Refresh JWT token

WS     /ws/jobs/<uuid>/               WebSocket — real-time job progress updates
```

---

## Celery task flow

When a PDF is uploaded:
1. `POST /api/documents/upload/` → creates `AnalysisJob(status='queued')`, saves file
2. View calls `process_pdf_task.delay(job_id)`
3. Celery worker picks up task:
   - Sets `status='processing'`, sends WebSocket update
   - Calls `ocr_service.analyze(file_path)` → Azure Document Intelligence API
   - Runs `extraction.extract_fields(ocr_result)` → structured dict
   - Fuzzy-matches employee name with rapidfuzz against Employee table
   - Creates `Report` and `ExtractedField` records
   - Sets `status='done'`, sends WebSocket update
4. Frontend receives WebSocket update, refreshes detail panel

---

## OCR service — abstraction layer

The OCR backend is behind an interface so it can be swapped later:

```python
# app/services/ocr_service.py

class OCRService:
    """Swap the backend here when PyTorch sm_120 support lands."""

    def analyze(self, file_path: str) -> dict:
        return self._azure_analyze(file_path)
        # Future: return self._local_gpu_analyze(file_path)

    def _azure_analyze(self, file_path: str) -> dict:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential
        client = DocumentIntelligenceClient(
            endpoint=settings.AZURE_DI_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_DI_KEY)
        )
        with open(file_path, 'rb') as f:
            poller = client.begin_analyze_document('prebuilt-read', f)
        return poller.result().as_dict()

    def _local_gpu_analyze(self, file_path: str) -> dict:
        # TODO: implement with surya or doctr once PyTorch supports sm_120 (RTX 5070 Ti)
        # RTX 5070 Ti = Blackwell architecture = sm_120
        # PyTorch stable supports only up to sm_90 as of May 2026
        # Monitor: https://github.com/pytorch/pytorch/issues/164342
        raise NotImplementedError("Local GPU OCR not yet available for sm_120")
```

---

## UI design — Outlook-style layout

The app uses a three-column Outlook-style layout:

```
[ icon sidebar ] [ document list ] [ detail panel ]
     36px             240px            flex: 1
```

- Icon sidebar: Documents, Employees, Reports, Settings icons
- Document list: scrollable list of `AnalysisJob` items with name, employee,
  date, and status badge (Done / Processing / Queued / Error)
- Detail panel: changes based on selected document status:
  - `done` → extracted fields grid + data table + Export Excel / Re-run buttons
  - `processing` → progress bar + "Page X of Y" message
  - `queued` → waiting state
  - `error` → error message + Re-run button

Status badge colours follow semantic conventions:
- Done → green (`success`)
- Processing → amber (`warning`)
- Queued → gray
- Error → red (`danger`)

---

## Key decisions log

| Decision | Choice | Reason |
|---|---|---|
| OCR backend | Azure Document Intelligence | RTX 5070 Ti (sm_120) incompatible with PyTorch stable; cloud API is faster and more accurate than pytesseract |
| Task queue | Celery + Redis | Async processing so UI stays responsive during 5–30s OCR |
| Real-time updates | Django Channels (WebSocket) | Job progress visible live without polling |
| Employee data | Django model (DB) | Replaces brittle employees.xlsx on network share |
| Results storage | PostgreSQL (ExtractedField) | Replaces batch_results.xlsx, enables filtering/reporting |
| Auth | JWT (simplejwt) | Stateless, works well with React SPA |
| Frontend scaffold | Vite + React | Faster dev server than CRA |
| Editor | Cursor (VS Code-based) | AI-assisted coding; use `cursor .` from inside WSL if GPU libs needed |

---

## OCR accuracy — why Azure beats pytesseract for this project

### The problem with pytesseract
pytesseract is a general-purpose OCR engine designed for clean, typed text. The HR
reports in this project are scanned structured forms, which pytesseract handles poorly:
- Names in table cells or form fields get garbled (e.g. "Ahmed Al-Farsi" → "Ahned A1-Farsi")
- Numbers are misread — `1` confused with `l`, `0` with `O`, decimals dropped
- Table structure is ignored — values get separated from their labels
- Typical accuracy on this document type: ~85–90%

### What Azure Document Intelligence does differently
- Understands document layout — knows a value belongs to the label next to it
- Trained on millions of structured HR/business forms
- Returns named fields with confidence scores, not just raw text
- Handles Arabic names and mixed-script documents reliably
- Typical accuracy on structured scanned forms: ~97–99%
- Especially strong on: names, numeric scores, percentages, dates, table data

### rapidfuzz still matters
Even with near-perfect OCR, keep the rapidfuzz employee name matching from the pilot.
Azure may return "Ahmed Al-Farsi" correctly while the DB has "Ahmed Alfarsi" (no hyphen)
or a different romanization. Fuzzy matching bridges that gap. With better OCR input,
rapidfuzz confidence scores will be much higher, reducing "could not match" errors
significantly.

### Azure subscription handover — zero extra development
The Azure Document Intelligence API is identical regardless of which Azure account pays
for it. When the company takes over billing:
- Zero code changes required
- Only change: swap `AZURE_DI_ENDPOINT` and `AZURE_DI_KEY` in the `.env` file
- Credentials must NEVER be hardcoded — always read from environment variables
- `.env` must be in `.gitignore` — credentials should never appear in git history
- Free tier: 500 pages/month at no cost — may cover entire development period

---

## Environment variables (.env)

```env
# Django
DJANGO_SECRET_KEY=
DJANGO_DEBUG=True
DATABASE_URL=postgresql://user:pass@localhost:5432/pdf_analyzer

# Azure Document Intelligence
# To hand over to company: only these two values need to change — zero code changes
AZURE_DI_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_DI_KEY=

# Celery / Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# JWT
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=60
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7
```

---

## GPU / PyTorch status (important)

- GPU: NVIDIA GeForce RTX 5070 Ti, 12GB VRAM, Blackwell architecture, `sm_120`
- PyTorch stable (as of May 2026): supports only up to `sm_90` — RTX 5070 Ti **cannot
  be used** with stable PyTorch builds on Windows
- Workaround options:
  1. PyTorch nightly + CUDA 12.8/12.9 inside **WSL2** (works, but unstable)
  2. Use cloud OCR (Azure/Google) — chosen approach for this project
- Track PyTorch sm_120 support: https://github.com/pytorch/pytorch/issues/164342
- When sm_120 lands in stable PyTorch, swap `OCRService._azure_analyze` for
  `_local_gpu_analyze` using surya or doctr

---

## Pilot code to migrate / reuse

| Pilot file | Migration target |
|---|---|
| `app/services/export_batch.py` | `backend/apps/documents/services/extraction.py` |
| `employees.xlsx` | `Employee` model + management command to import |
| `batch_results.xlsx` | `Report` + `ExtractedField` models |
| `run_export_batch.py` | `process_pdf_task` Celery task |
| pytesseract calls | `OCRService._azure_analyze()` |
| rapidfuzz matching | Keep as-is, query `Employee.objects.all()` instead of Excel |

---

## Running locally (target setup)

```bash
# Backend
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

# Celery worker (separate terminal)
celery -A config worker --loglevel=info

# Redis (Docker)
docker run -p 6379:6379 redis:alpine

# Frontend
cd frontend
npm install
npm run dev
```

---

## What IS in scope

### Batch upload
- Multi-file dropzone in React — user selects or drops multiple PDFs at once
- Each PDF becomes its own `AnalysisJob` record
- All jobs fired to Celery simultaneously — processed in parallel
- Document list shows all jobs with individual status badges
- The pilot already did this (`build_export_package` processes a whole folder) — the
  full app must not go backwards on this

### PDF preview in browser
- When a completed job is selected in the detail panel, show the original scan
  alongside the extracted data
- Use `react-pdf` library (renders PDF pages as canvas in browser)
- Layout: extracted fields on the right, PDF viewer on the left (or toggled)
- Critical for usability: lets HR reviewers spot OCR errors by comparing
  extracted values against the original document without leaving the app

### Role-based permissions
- HR data is sensitive — "everyone sees everything" is not acceptable even for demo
- Two roles minimum, implemented via Django Groups:
  - **Admin**: manages employees, deletes jobs, sees all documents, exports
  - **Reviewer**: uploads PDFs, views results, downloads reports — cannot manage employees
- Enforced at API level with DRF permission classes, not just in the frontend
- JWT token payload includes the user's role so React can show/hide UI elements

---

## What is NOT in scope (yet)

- Multi-tenant / multi-company support — one company, one instance for now
- Deployment / CI-CD pipeline — a `docker-compose.yml` for local/demo is enough;
  proper deployment is a post-demo concern
