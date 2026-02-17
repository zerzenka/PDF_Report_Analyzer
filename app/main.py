from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.services.pdf_extractor import extract_fields_from_pdf
from app.services.batch_processor import process_pdf_batch
from app.services.employee_db import EmployeeDB
from app.services.id_suggest import suggest_ids

# NEW (Excel writing)
import openpyxl


app = FastAPI(title="PDF Report Analyzer")

# --------------------------------------------------
# Paths (adjust ONLY this)
# --------------------------------------------------
SHARED_ROOT = Path(r"I:\60 - Services\30 - BI\010 - Shared\HP_app")

INPUT_DIR = SHARED_ROOT / "input_pdfs"
EXPORTS_ROOT = SHARED_ROOT / "exports"

UPLOAD_DIR = Path("uploaded_pdfs")  # local uploads (optional)
UPLOAD_DIR.mkdir(exist_ok=True)

# --------------------------------------------------
# Templates (UI)
# --------------------------------------------------
templates = Jinja2Templates(directory="app/templates")

# --------------------------------------------------
# Database (for suggestions)
# --------------------------------------------------
DB = EmployeeDB(str(EXPORTS_ROOT / "employees.xlsx"))  # keep in exports as you do


# ==================================================
# Helpers
# ==================================================
def _load_manifest(export_dir: Path) -> Dict[str, Any]:
    manifest_path = export_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"manifest.json not found: {manifest_path}")

    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read manifest.json: {e}")


def _docs_root(export_dir: Path) -> Path:
    p = export_dir / "docs"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"docs folder not found: {p}")
    return p


def _safe_export_folder(export_name: str) -> Path:
    if any(x in export_name for x in ("/", "\\", "..")):
        raise HTTPException(status_code=400, detail="Invalid export_name")

    export_dir = EXPORTS_ROOT / export_name
    if not export_dir.exists() or not export_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Export folder not found: {export_dir}")
    return export_dir


def _safe_doc_folder(docs_root: Path, doc_name: str) -> Path:
    if any(x in doc_name for x in ("/", "\\", "..")):
        raise HTTPException(status_code=400, detail="Invalid doc_name")

    doc_dir = docs_root / doc_name
    if not doc_dir.exists() or not doc_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Document folder not found: {doc_dir}")
    return doc_dir


def _coerce_doc_to_name(d: Any) -> str:
    if isinstance(d, str):
        return d
    if isinstance(d, dict):
        for key in ("doc_name", "name", "folder_name", "id", "filename"):
            val = d.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return str(d)


def _list_docs_from_manifest(manifest: Dict[str, Any], docs_root: Path) -> List[str]:
    docs: List[str] = []

    if isinstance(manifest.get("documents"), list):
        for item in manifest["documents"]:
            name = _coerce_doc_to_name(item)
            if name and name != "[object Object]":
                docs.append(name)

    elif isinstance(manifest.get("docs"), list):
        for item in manifest["docs"]:
            name = _coerce_doc_to_name(item)
            if name and name != "[object Object]":
                docs.append(name)

    elif isinstance(manifest.get("items"), list):
        for item in manifest["items"]:
            name = _coerce_doc_to_name(item)
            if name and name != "[object Object]":
                docs.append(name)

    if not docs:
        docs = sorted([p.name for p in docs_root.iterdir() if p.is_dir()])

    # de-dup preserve order
    seen = set()
    out: List[str] = []
    for x in docs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ==================================================
# Static mount: serve ALL exports
# ==================================================
if not EXPORTS_ROOT.exists():
    print(f"[WARN] EXPORTS_ROOT does not exist yet: {EXPORTS_ROOT}")
else:
    app.mount("/static", StaticFiles(directory=str(EXPORTS_ROOT)), name="static")
    print(f"[STATIC] Mounted /static -> {EXPORTS_ROOT}")


# ==================================================
# Health
# ==================================================
@app.get("/health")
def health_check():
    return {"status": "ok"}


# ==================================================
# Review UI
# ==================================================
@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    return templates.TemplateResponse("review.html", {"request": request})


# ==================================================
# API: list batches
# ==================================================
@app.get("/api/batches")
def api_batches():
    if not EXPORTS_ROOT.exists():
        return JSONResponse({"batches": []})

    batches = sorted(
        [p for p in EXPORTS_ROOT.iterdir() if p.is_dir() and p.name.startswith("export_")],
        key=lambda p: p.name,
        reverse=True,
    )

    return JSONResponse({"batches": [{"id": b.name, "title": b.name} for b in batches]})


# ==================================================
# API: list docs in batch
# ==================================================
@app.get("/api/batches/{export_name}/docs")
def api_batch_docs(export_name: str):
    export_dir = _safe_export_folder(export_name)
    manifest = _load_manifest(export_dir)
    docs_root = _docs_root(export_dir)

    docs = _list_docs_from_manifest(manifest, docs_root)

    return JSONResponse({"export": export_dir.name, "documents": docs})


# ==================================================
# API: read one doc results.json in batch
# ==================================================
@app.get("/api/batches/{export_name}/docs/{doc_name}")
def api_batch_doc_detail(export_name: str, doc_name: str):
    export_dir = _safe_export_folder(export_name)
    docs_root = _docs_root(export_dir)
    doc_dir = _safe_doc_folder(docs_root, doc_name)

    results_path = doc_dir / "results.json"
    if not results_path.exists():
        raise HTTPException(status_code=404, detail=f"results.json not found: {results_path}")

    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed reading results.json: {e}")

    data["_export"] = export_dir.name
    data["_doc_name"] = doc_name
    data["_static_base"] = f"/static/{export_dir.name}/docs/{doc_name}"

    return JSONResponse(data)


# ==================================================
# Suggest IDs (returns id + name + score)
# ==================================================
@app.get("/suggest-ids")
async def suggest_ids_endpoint(q: str, department: str = "CASTHOUSE", limit: int = 10):
    dept_records = DB.get_records_for_department(department)

    valid_ids: List[str] = []
    id_to_name: Dict[str, str] = {}

    for rec in dept_records:
        if isinstance(rec, tuple):
            emp_id = rec[0]
            emp_name = rec[1] if len(rec) > 1 else ""
        else:
            emp_id = rec.get("emp_id")
            emp_name = rec.get("name") or rec.get("emp_name") or rec.get("full_name") or ""

        if emp_id:
            sid = str(emp_id)
            valid_ids.append(sid)
            if emp_name:
                id_to_name[sid] = str(emp_name)

    suggestions = suggest_ids(q, valid_ids, limit=limit)

    return JSONResponse({
        "suggestions": [
            {"id": sid, "name": id_to_name.get(sid, ""), "score": score}
            for sid, score in suggestions
        ]
    })


# ==================================================
# NEW: Submit summary -> review_summary.xlsx
# Columns: ID | Name | Count | Documents
# ==================================================
@app.post("/api/submit-summary")
async def submit_summary(payload: Dict[str, Any]):
    export_name = payload.get("export")
    doc_name = payload.get("doc")
    rows = payload.get("rows", [])

    if not export_name or not doc_name or not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="Invalid payload")

    out_path = EXPORTS_ROOT / "review_summary.xlsx"

    # Create workbook if needed
    if not out_path.exists():
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "summary"
        ws.append(["ID", "Name", "Count", "Documents"])
        wb.save(out_path)

    wb = openpyxl.load_workbook(out_path)
    ws = wb["summary"]

    # Load existing summary by ID
    existing: Dict[str, Dict[str, Any]] = {}
    for r in ws.iter_rows(min_row=2, values_only=False):
        emp_id_cell, name_cell, count_cell, docs_cell = r[0], r[1], r[2], r[3]
        emp_id = str(emp_id_cell.value).strip() if emp_id_cell.value is not None else ""
        if not emp_id:
            continue

        name = str(name_cell.value).strip() if name_cell.value else ""
        count = int(count_cell.value) if count_cell.value not in (None, "") else 0
        docs_raw = str(docs_cell.value).strip() if docs_cell.value else ""
        docs_set = set([d.strip() for d in docs_raw.split(",") if d.strip()])

        existing[emp_id] = {
            "row": emp_id_cell.row,
            "name": name,
            "count": count,
            "docs": docs_set,
        }

    # Aggregate this submission (count occurrences per employee within the doc)
    doc_counts: Dict[str, Dict[str, Any]] = {}
    for rr in rows:
        emp_id = str(rr.get("resolved_id") or "").strip()
        emp_name = str(rr.get("resolved_name") or "").strip()

        # only resolved entries
        if not emp_id or not emp_name:
            continue

        if emp_id not in doc_counts:
            doc_counts[emp_id] = {"name": emp_name, "count": 0}
        doc_counts[emp_id]["count"] += 1

        # keep "better" (longer) name if it appears
        if len(emp_name) > len(doc_counts[emp_id]["name"]):
            doc_counts[emp_id]["name"] = emp_name

    # Write updates
    for emp_id, info in doc_counts.items():
        add_count = int(info["count"])
        new_name = str(info["name"])

        if emp_id in existing:
            row_idx = existing[emp_id]["row"]

            # Count += occurrences in this doc
            old_count = existing[emp_id]["count"]
            ws.cell(row=row_idx, column=3).value = old_count + add_count

            # Name update if empty or "better"
            old_name = existing[emp_id]["name"]
            if (not old_name) or (len(new_name) > len(old_name)):
                ws.cell(row=row_idx, column=2).value = new_name

            # Documents union
            docs_set = existing[emp_id]["docs"]
            docs_set.add(doc_name)
            ws.cell(row=row_idx, column=4).value = ", ".join(sorted(docs_set))

        else:
            ws.append([emp_id, new_name, add_count, doc_name])

    wb.save(out_path)

    return {
        "status": "ok",
        "file": str(out_path),
        "updated_employees": len(doc_counts),
        "document": doc_name,
    }


# ==================================================
# OLD: Upload & process ONE PDF (optional)
# ==================================================
@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    file_path = UPLOAD_DIR / file.filename
    file_path.parent.mkdir(exist_ok=True)

    import shutil
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    extracted_data = extract_fields_from_pdf(str(file_path))
    return {"filename": file.filename, "extracted_data": extracted_data}


# ==================================================
# OLD: Process ALL PDFs in local upload folder (optional)
# ==================================================
@app.post("/process-batch")
def process_batch():
    pdfs = list(UPLOAD_DIR.glob("*.pdf")) + list(UPLOAD_DIR.glob("*.PDF"))
    if not pdfs:
        raise HTTPException(status_code=400, detail="No PDFs found in upload folder")
    return process_pdf_batch(UPLOAD_DIR)
