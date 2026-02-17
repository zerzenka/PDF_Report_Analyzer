from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from app.services.pdf_extractor import extract_fields_from_pdf


def build_export_package(
    input_dir: str,
    exports_root: str,
    employees_xlsx_path: str | None = None,
) -> Dict:
    """
    Processor-side batch:
      - Reads PDFs from input_dir
      - Creates a timestamped export folder in exports_root
      - For each PDF: creates docs/<pdf_stem>/ (results.json + crop images)
      - Writes manifest.json at export root

    Returns summary dict.
    """

    input_path = Path(input_dir)
    exports_root_path = Path(exports_root)

    if not input_path.exists():
        raise FileNotFoundError(f"Input folder not found: {input_path}")

    exports_root_path.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    export_dir = exports_root_path / f"export_{stamp}"
    docs_dir = export_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Optional: copy employees.xlsx into export for portable UI usage
    if employees_xlsx_path:
        src = Path(employees_xlsx_path)
        if src.exists():
            (export_dir).mkdir(parents=True, exist_ok=True)
            dst = export_dir / src.name
            if dst.resolve() != src.resolve():
                dst.write_bytes(src.read_bytes())

    pdf_files = sorted(list(input_path.glob("*.pdf")) + list(input_path.glob("*.PDF")))

    manifest_docs: List[Dict] = []
    results_summary: List[Dict] = []

    for pdf_path in pdf_files:
        doc_name = pdf_path.stem
        doc_out_dir = docs_dir / doc_name
        doc_out_dir.mkdir(parents=True, exist_ok=True)

        # Run extractor + save crops in doc_out_dir
        extracted = extract_fields_from_pdf(str(pdf_path), out_dir=str(doc_out_dir))

        # Save results.json
        results_path = doc_out_dir / "results.json"
        results_path.write_text(json.dumps(extracted, indent=2), encoding="utf-8")

        manifest_docs.append({
            "doc_name": doc_name,
            "folder": f"docs/{doc_name}",
            "results": f"docs/{doc_name}/results.json",
            "source_pdf": pdf_path.name,
        })

        results_summary.append({
            "doc_name": doc_name,
            "final_count": len(extracted.get("final_employee_ids", [])),
        })

    manifest = {
        "created_at": stamp,
        "input_dir": str(input_path),
        "docs": manifest_docs,
    }

    (export_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "export_dir": str(export_dir),
        "pdf_count": len(pdf_files),
        "docs": results_summary,
    }