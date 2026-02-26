from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from app.services.pdf_extractor import extract_fields_from_pdf


def _safe_doc_name(filename: str) -> str:
    # folder-safe name from PDF filename
    base = Path(filename).stem
    base = "".join(c for c in base if c.isalnum() or c in ("_", "-", " "))
    base = base.strip().replace(" ", "_")
    return base or "doc"


def process_pdf_batch(
    input_dir: Path,
    exports_root: Path,
) -> Dict[str, Any]:
    """
    Reads PDFs from input_dir and writes an export batch under exports_root:
      exports_root/export_YYYY-MM-DD_HHMMSS/
        manifest.json
        batch_results.xlsx
        docs/<doc_name>/
          results.json
          (crops created by pdf_extractor should be saved into this folder)
    """

    input_dir = Path(input_dir)
    exports_root = Path(exports_root)

    if not input_dir.exists():
        raise FileNotFoundError(f"input_dir not found: {input_dir}")

    exports_root.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(list(input_dir.glob("*.pdf")) + list(input_dir.glob("*.PDF")))
    if not pdf_files:
        return {
            "status": "empty",
            "message": f"No PDFs found in {str(input_dir)}",
            "total_pdfs": 0,
            "export_dir": None,
        }

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    export_dir = exports_root / f"export_{stamp}"
    docs_root = export_dir / "docs"
    docs_root.mkdir(parents=True, exist_ok=True)

    batch_results: List[Dict[str, Any]] = []
    excel_rows: List[Dict[str, Any]] = []

    for pdf_path in pdf_files:
        doc_name = _safe_doc_name(pdf_path.name)
        doc_dir = docs_root / doc_name
        doc_dir.mkdir(parents=True, exist_ok=True)

        # IMPORTANT:
        # Your extract_fields_from_pdf must write crops somewhere.
        # We want crops to end up in doc_dir so /static/... can serve them.
        #
        # If your extractor already saves crops relative to doc_dir (recommended),
        # it will work immediately.
        #
        # If not, we’ll adjust pdf_extractor next.
        extracted = extract_fields_from_pdf(str(pdf_path), out_dir=str(doc_dir))

        # write per-doc results.json
        results_path = doc_dir / "results.json"
        results_path.write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")

        batch_results.append({
            "doc_name": doc_name,
            "pdf_filename": pdf_path.name,
            "results_json": str(results_path),
        })

        # rows for excel
        rows = extracted.get("rows", []) if isinstance(extracted, dict) else []
        for r in rows:
            excel_rows.append({
                "document": doc_name,
                "pdf_filename": pdf_path.name,
                "row": r.get("row"),
                "resolved_id": r.get("resolved_id"),
                "resolved_name": r.get("resolved_name"),
                "ocr_name": r.get("ocr_name_clean"),
                "confidence": r.get("confidence"),
                "method": r.get("method"),
            })

    # manifest.json (for UI batch/doc listing)
    manifest = {
        "created_at": stamp,
        "input_dir": str(input_dir),
        "export_dir": str(export_dir),
        "documents": [b["doc_name"] for b in batch_results],
        "items": batch_results,
    }
    (export_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # optional excel summary inside export folder
    df = pd.DataFrame(excel_rows)
    excel_path = export_dir / "batch_results.xlsx"
    df.to_excel(excel_path, index=False)

    return {
        "status": "ok",
        "total_pdfs": len(pdf_files),
        "total_rows": len(excel_rows),
        "export_dir": str(export_dir),
        "manifest": str(export_dir / "manifest.json"),
        "excel_report": str(excel_path),
        "documents": manifest["documents"],
    }

