from pathlib import Path
from typing import List, Dict
import pandas as pd

from app.services.pdf_extractor import extract_fields_from_pdf


def process_pdf_batch(upload_dir: Path) -> Dict:

    pdf_files = list(upload_dir.glob("*.pdf")) + list(upload_dir.glob("*.PDF"))

    batch_results = []

    for pdf_path in pdf_files:
        extracted = extract_fields_from_pdf(str(pdf_path))

        batch_results.append({
            "filename": pdf_path.name,
            "data": extracted
        })

    # --------------------------
    # Optional Excel summary
    # --------------------------
    rows = []

    for item in batch_results:
        filename = item["filename"]

        for r in item["data"]["rows"]:
            rows.append({
                "filename": filename,
                "row": r["row"],
                "resolved_id": r["resolved_id"],
                "ocr_name": r["ocr_name_clean"],
                "confidence": r["confidence"],
                "method": r["method"]
            })

    df = pd.DataFrame(rows)

    excel_path = upload_dir / "batch_results.xlsx"
    df.to_excel(excel_path, index=False)

    return {
        "total_pdfs": len(pdf_files),
        "total_rows": len(rows),
        "excel_report": str(excel_path.name),
        "batch_results": batch_results
    }

