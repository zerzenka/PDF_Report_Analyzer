# HP Briefing Analyzer — project context for AI assistants

## What this project is

An internal tool for **Sohar Aluminium** that processes scanned **Human Performance
Pre-Job Briefing** forms. Each form is filled out by a team leader before a job,
listing 1–N team members with their handwritten names and SA ID numbers. The app
extracts those names/IDs, matches them to the employee/contractor database, and
produces monthly reports showing how many HP briefings each person participated in,
per department.

The original pilot repo: https://github.com/zerzenka/PDF_Report_Analyzer

---

## The document — what it looks like

- Form: "Human Performance Pre-Job Briefing" (Sohar Aluminium)
- Each PDF is a scanned paper form — handwritten content
- The team member table is in the bottom-right of the form
- Each row has: handwritten NAME + handwritten SA ID + signature
- There are typically 1–7 rows but can vary — no fixed number
- Sometimes team members write names OUTSIDE the table (below it)
  → reviewer must be able to add extra rows manually during review
- Date field exists on the form but is often unclear/unreadable
  → month is determined by the FOLDER the PDF is uploaded into, not the document

---

## The document — SA ID format rules

SA IDs are always 6 digits. Two types:
- **Employees**: start with 1 → 100xxx, 101xxx, 102xxx (growing over time)
- **Contractors**: start with 9 → 9xxxxx

Prefix rules:
- Sometimes written as "SA100857" — strip "SA" prefix before matching
- Sometimes written as "SA929400" (contractor) — strip "SA", becomes "929400"
- The number in the database is always 6 digits, no prefix
- Use first digit after stripping to decide which DB to search:
  - Starts with 1 → Employee database
  - Starts with 9 → Contractor database

---

## The full workflow (step by step)

1. **Focal point** (department data entry person) logs in
2. Selects or creates a **month batch** (e.g. "05-2026" for May 2026)
3. **Uploads one or more PDFs** into that month batch
4. For each PDF, a **Celery task** runs:
   a. Azure Document Intelligence OCR reads the full page
   b. The team member table is detected and each row is cropped:
      - One image crop for the NAME cell
      - One image crop for the ID cell
   c. OCR text is extracted from each crop separately
   d. SA prefix is stripped from ID; first digit used to select Employee or Contractor DB
   e. Each row is scored: `total = (name_score x 0.65) + (id_score x 0.35)`
   f. High confidence (>= 85%) → auto_resolved
   g. Low confidence (< 85%) → needs_review
5. Document status:
   - All rows auto-resolved → still goes to needs_review (reviewer always confirms)
   - Any rows need review → needs_review
   - OCR failed → error
6. **Reviewer opens the document** in the detail panel:
   - Left side: PDF viewer (full document visible)
   - Right side: each detected row shown with:
     - Name crop image
     - ID crop image
     - OCR text extracted
     - Top 5 candidate matches with scores
     - Final Name field (editable)
     - Final ID field (searchable — type digits to filter dropdown)
     - Dropdown shows ID + Name from Employee/Contractor table
   - Reviewer can add extra rows for names written outside the table
   - Even auto-resolved rows can be changed by the reviewer
7. Reviewer clicks Resolve on each row, then Submit on the document
8. Document status → resolved
9. For each resolved row → one **HPRecord** is created in the database
   - Links employee/contractor to this document and month
   - If same person appears on multiple documents in same month → count increases
10. **Document can be deleted** even after resolved (by focal point or admin)
11. **Monthly reports** are generated per department:
    - Total HP briefings done that month
    - Number of participations per person
    - Breakdown by employee vs contractor

---

## Users and access control

### Roles
- **Admin**: sees all departments, manages users, manages employee/contractor list,
  can delete any document, can export any report
- **Focal Point** (Reviewer): sees ONLY their own department's documents and reports,
  uploads PDFs, does manual review, can delete their own department's documents

### Department assignment
- Each user's department is predefined by admin when the account is created
- Users cannot change their own department
- Department is stored on the User profile, not chosen at login
- JWT token includes: role, department_id, department_name

### Data isolation
- Focal point queries are always filtered by department
- Enforced at API level (DRF permission classes + queryset filtering), not just UI

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React (Vite), react-router-dom, axios, react-pdf |
| Backend | Django 5.x + Django REST Framework |
| Database | PostgreSQL |
| Task queue | Celery + Redis |
| Real-time | Django Channels (WebSocket for job progress) |
| OCR | Azure Document Intelligence (replaces pytesseract) |
| Auth | JWT via djangorestframework-simplejwt |
| File storage | Django MEDIA_ROOT (local for dev) |
| Dev environment | Cursor (VS Code-based), Windows 11 |
| GPU | NVIDIA RTX 5070 Ti 12GB — NOT usable with PyTorch stable (sm_120) |

---

## Django project structure

```
backend/
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── celery.py
│   └── asgi.py
├── apps/
│   ├── authentication/
│   │   ├── serializers.py        # CustomTokenObtainPairSerializer (role + dept in token)
│   │   └── urls.py
│   ├── documents/
│   │   ├── models.py             # MonthBatch, AnalysisJob, DocumentRow, HPRecord
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── tasks.py              # process_pdf_task (Celery)
│   │   ├── consumers.py          # WebSocket job progress
│   │   └── services/
│   │       ├── ocr_service.py    # Azure Document Intelligence wrapper
│   │       ├── table_detector.py # Detect and crop team member table rows
│   │       └── matcher.py        # ID stripping + fuzzy matching logic
│   ├── employees/
│   │   ├── models.py             # Employee (employees + contractors in one table)
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── management/commands/
│   │       └── import_employees.py  # Seeds from employees.xlsx (dev only)
│   └── reports/
│       ├── models.py
│       ├── serializers.py
│       └── views.py
└── manage.py

frontend/
├── src/
│   ├── components/
│   │   ├── DocumentList.jsx      # Left panel — month groups + document items
│   │   ├── ReviewPanel.jsx       # Right panel — PDF viewer + row review UI
│   │   ├── RowReviewCard.jsx     # One row: name crop, ID crop, search dropdown
│   │   ├── StatusBadge.jsx
│   │   └── MonthSelector.jsx
│   ├── pages/
│   │   ├── DocumentsPage.jsx     # Main Outlook-style layout
│   │   ├── ReportsPage.jsx       # Monthly reports
│   │   └── EmployeesPage.jsx     # Admin only
│   ├── hooks/
│   │   └── useJobStatus.js       # WebSocket hook
│   ├── api/
│   │   └── client.js             # axios + JWT interceptor
│   └── App.jsx
└── vite.config.js
```

---

## Database models

### Department
```python
class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)  # e.g. "Reduction"
    code = models.CharField(max_length=20, unique=True)   # e.g. "RED"
```

### UserProfile (extends Django User)
```python
class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, null=True, on_delete=models.SET_NULL)
    # role derived: superuser or Admin group = admin, otherwise = focal_point
```

### Employee
```python
class Employee(models.Model):
    TYPE_CHOICES = [('employee', 'Employee'), ('contractor', 'Contractor')]
    employee_id = models.CharField(max_length=10, unique=True)  # 6-digit, no prefix
    full_name = models.CharField(max_length=255)
    department = models.ForeignKey(Department, null=True, on_delete=models.SET_NULL)
    email = models.EmailField(blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    is_active = models.BooleanField(default=True)
    last_synced = models.DateTimeField(null=True)
```

### MonthBatch
Groups documents by month. Month comes from upload selection, not document content.
```python
class MonthBatch(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    month_label = models.CharField(max_length=7)   # e.g. "05-2026"
    month_date = models.DateField()                 # first day: 2026-05-01
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('department', 'month_label')
```

### AnalysisJob
One PDF document.
```python
class AnalysisJob(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('processing', 'Processing'),
        ('needs_review', 'Needs Review'),
        ('resolved', 'Resolved'),
        ('error', 'Error'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    batch = models.ForeignKey(MonthBatch, on_delete=models.CASCADE,
                               related_name='documents')
    file = models.FileField(upload_to='uploads/')
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    page_count = models.IntegerField(null=True)
    error_message = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True)
    deleted = models.BooleanField(default=False)   # soft delete
```

### DocumentRow
One person detected in a PDF.
```python
class DocumentRow(models.Model):
    STATUS_CHOICES = [
        ('auto_resolved', 'Auto Resolved'),
        ('needs_review', 'Needs Review'),
        ('resolved', 'Resolved'),
    ]
    job = models.ForeignKey(AnalysisJob, on_delete=models.CASCADE, related_name='rows')
    row_index = models.IntegerField()

    # OCR raw output
    ocr_name_raw = models.CharField(max_length=255, blank=True)
    ocr_id_raw = models.CharField(max_length=50, blank=True)
    ocr_id_clean = models.CharField(max_length=10, blank=True)  # stripped of SA prefix

    # Crop images
    name_crop = models.ImageField(upload_to='crops/', null=True)
    id_crop = models.ImageField(upload_to='crops/', null=True)

    # Matching
    top_candidates = models.JSONField(default=list)  # top 5 with scores
    confidence = models.FloatField(default=0.0)
    match_method = models.CharField(max_length=50, blank=True)

    # Resolution
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='needs_review')
    resolved_employee = models.ForeignKey('employees.Employee', null=True, blank=True,
                                          on_delete=models.SET_NULL)
    resolved_manually = models.BooleanField(default=False)
    added_manually = models.BooleanField(default=False)  # added outside table
    resolved_at = models.DateTimeField(null=True)
```

### HPRecord
Created when a DocumentRow is resolved. Source of truth for monthly counts.
```python
class HPRecord(models.Model):
    employee = models.ForeignKey('employees.Employee', on_delete=models.CASCADE,
                                  related_name='hp_records')
    document_row = models.OneToOneField(DocumentRow, on_delete=models.CASCADE)
    job = models.ForeignKey(AnalysisJob, on_delete=models.CASCADE)
    department = models.ForeignKey('employees.Department', on_delete=models.CASCADE)
    month_batch = models.ForeignKey(MonthBatch, on_delete=models.CASCADE)
    month_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Same person on 3 documents in one month = 3 HPRecords = count of 3 (correct)
        indexes = [
            models.Index(fields=['employee', 'month_date']),
            models.Index(fields=['department', 'month_date']),
        ]
```

---

## Matching logic (matcher.py)

```python
def clean_id(raw_id: str) -> str:
    """Strip SA prefix, return 6-digit string or empty."""
    cleaned = raw_id.strip().upper().lstrip('SA').strip()
    return cleaned if cleaned.isdigit() and len(cleaned) == 6 else ''

def get_employee_type(clean_id: str) -> str:
    """Determine employee or contractor from first digit."""
    if not clean_id:
        return 'unknown'
    return 'employee' if clean_id.startswith('1') else 'contractor'

def match_row(ocr_name: str, ocr_id_raw: str) -> dict:
    """
    Score formula:
      name_score  = rapidfuzz.fuzz.token_sort_ratio(ocr_name, candidate_name)
      id_score    = rapidfuzz.fuzz.ratio(clean_id, candidate_id)
      total_score = (name_score * 0.65) + (id_score * 0.35)

    Resolution:
      total_score >= 85  → auto_resolved
      total_score < 85   → ambiguous_manual_review
      id exact match but name_score < 60 → number_only_name_mismatch (flag for review)

    Returns top 5 candidates + recommended resolution.
    """
```

---

## API endpoints

```
# Auth
POST   /api/auth/token/                       Get JWT (role + department in response)
POST   /api/auth/token/refresh/

# Month batches
GET    /api/batches/                          List batches for user's department
POST   /api/batches/                          Create new batch {month_label: "05-2026"}
GET    /api/batches/<id>/                     Batch detail + document list

# Documents
POST   /api/documents/upload/                 Upload PDFs → AnalysisJob per file
GET    /api/documents/                        List (filtered by dept automatically)
GET    /api/documents/<uuid>/                 Detail + all rows
DELETE /api/documents/<uuid>/                 Soft delete (focal point or admin)
POST   /api/documents/<uuid>/rerun/           Re-queue failed document
POST   /api/documents/<uuid>/submit/          Mark resolved, create HPRecords

# Document rows (review)
GET    /api/documents/<uuid>/rows/            List all rows
PATCH  /api/documents/<uuid>/rows/<id>/resolve/  Resolve a row
POST   /api/documents/<uuid>/rows/add/        Add manual row (name outside table)
DELETE /api/documents/<uuid>/rows/<id>/       Delete manually added row

# Employee search (for review dropdown)
GET    /api/employees/search/?q=digits        Search by ID digits

# Employees (admin only)
GET    /api/employees/
POST   /api/employees/import/                 From Excel (dev only)
POST   /api/employees/sync/                   Trigger sync from source DBs

# Reports
GET    /api/reports/monthly/                  Monthly report for dept + month
GET    /api/reports/monthly/export/           Download as Excel

# WebSocket
WS     /ws/jobs/<uuid>/                       Real-time processing progress
```

---

## UI design — Outlook-style layout

```
[ icon sidebar ] [ document list ] [ detail panel                          ]
     36px             240px        [ PDF viewer (left) | Review (right)   ]
```

### Document list
- Grouped by MonthBatch ("May 2026", "April 2026")
- Each item: filename, rows resolved/total, status badge
- Badges: Queued (gray), Processing (amber), Needs Review (orange), Resolved (green), Error (red)

### Detail panel — Needs Review
- Left half: react-pdf PDF viewer showing full document
- Right half: review panel with one RowReviewCard per detected row:
  - Name crop image + ID crop image
  - OCR raw text shown
  - Editable Name field
  - ID search field — type digits to filter dropdown
  - Dropdown: "100299 — Mohammed Al Washahi"
  - Confidence badge (green/amber/red)
  - [Resolve] button per row
- [+ Add row] button for names outside the table
- [Submit document] button — only enabled when all rows resolved

### Detail panel — Resolved
- Summary of all resolved rows (name + ID + type)
- [Delete document] button with confirmation dialog
- [Re-open for editing] button

### Match confidence display
- >= 85% → green — auto-resolved
- 70–84% → amber — "Low confidence — please verify"
- < 70% → red — "Could not auto-match"
- All rows have an edit button regardless of confidence

---

## Monthly report structure

```
May 2026 — Reduction Department
Total HP Briefings:   23 documents
Total participations: 147

By person:
  Ahmed Al-Farsi      (EMP 100412)   12 participations
  Sara Al-Balushi     (EMP 100198)    9 participations
  Khalid Al-Sinani    (CON 101569)    6 participations

[Download Excel]
```

Same person on multiple documents in same month = multiple HPRecords = count > 1.
This is correct — each briefing participation is counted separately.

---

## OCR service abstraction

```python
class OCRService:
    def analyze_page(self, file_path: str) -> dict:
        return self._azure_analyze(file_path)

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
        # TODO: implement once PyTorch stable supports sm_120 (RTX 5070 Ti / Blackwell)
        # Monitor: https://github.com/pytorch/pytorch/issues/164342
        raise NotImplementedError
```

---

## OCR accuracy notes

- Documents have handwritten names and IDs (pen on paper, scanned)
- pytesseract on handwriting: very poor (30–50% usable matches)
- Azure Document Intelligence on handwriting: significantly better (70–85%)
- Handwriting will never be 100% — manual review UI is not optional, it is the core feature
- Use rapidfuzz token_sort_ratio (not simple ratio) — better for Arabic names
  where word order varies ("Ahmed Al Farsi" vs "Al Farsi Ahmed")

---

## Employee data sources

Two internal custom SQL databases (direct connection, read-only):
- Employee DB: full-time employees (IDs start with 1)
- Contractor DB: contractors (IDs start with 9)

Weekly sync via Celery Beat every Monday.
During development: seed from employees.xlsx using management command.
In production: fill in .env DB credentials — zero code changes.

---

## Key decisions log

| Decision | Reason |
|---|---|
| Month from upload selection, not document | Date field on form is often handwritten and unclear |
| Soft delete for documents | Resolved documents may need deletion but HPRecords should remain |
| Separate DocumentRow model | Each person resolved and counted independently |
| HPRecord per resolved row | Same person on 3 docs = 3 HPRecords = count of 3 (correct) |
| Focal point sees only own dept | Data isolation — HR data is sensitive |
| Department predefined by admin | Users cannot self-assign |
| Always go to needs_review | Even high-confidence matches need human confirmation for HR data |
| Edit button on all rows | Reviewer must always be able to override matching |
| Delete allowed after resolved | Operational requirement — mistakes happen |
| Azure OCR | pytesseract: 2min/PDF, poor handwriting. Azure: 5sec, much better |
| ID first digit determines DB | Reliable rule: 1xxxxx = employee, 9xxxxx = contractor |

---

## Environment variables (.env)

```env
DJANGO_DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
CELERY_TASK_ALWAYS_EAGER=True

# Azure Document Intelligence
AZURE_DI_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_DI_KEY=

# Redis / Celery (disable ALWAYS_EAGER and fill these for production)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# JWT
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=60
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7

# Source databases (read-only, provided by IT — leave blank during dev)
EMPLOYEE_DB_NAME=
EMPLOYEE_DB_USER=
EMPLOYEE_DB_PASSWORD=
EMPLOYEE_DB_HOST=
CONTRACTOR_DB_NAME=
CONTRACTOR_DB_USER=
CONTRACTOR_DB_PASSWORD=
CONTRACTOR_DB_HOST=
```

---

## GPU / PyTorch status

- GPU: NVIDIA RTX 5070 Ti, 12GB, Blackwell (sm_120)
- PyTorch stable (May 2026): supports only up to sm_90 — cannot use GPU
- Using Azure cloud OCR — no GPU required
- Track PyTorch sm_120: https://github.com/pytorch/pytorch/issues/164342

---

## Running locally

```bash
# Terminal 1 — Django
cd backend && pip install -r requirements.txt
python manage.py migrate
python manage.py import_employees
python manage.py runserver

# Terminal 2 — Celery (or set CELERY_TASK_ALWAYS_EAGER=True to skip)
celery -A config worker --loglevel=info

# Terminal 3 — Redis (skip if using ALWAYS_EAGER)
docker run -p 6379:6379 redis:alpine

# Terminal 4 — React
cd frontend && npm install && npm run dev
```

---

## In scope

- Batch upload into month batches
- PDF viewer (react-pdf) in review panel
- Manual review UI — name/ID crops, searchable dropdown, add extra rows
- Edit any row including auto-resolved ones
- Soft delete of documents after resolution
- Role-based access: Admin and Focal Point
- Department-based data isolation
- Monthly reports (total + per person) with Excel export
- Weekly sync from source employee/contractor databases

## Not in scope yet

- Multi-tenant / multi-company
- CI/CD pipeline
- Mobile layout
