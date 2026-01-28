import pdfplumber
import numpy as np
from typing import Dict, List, Tuple, Optional

from app.config.template_v1 import PDF_TEMPLATE_V1
from app.ocr_easyocr import read_ids_from_crop, read_name_from_crop

from app.services.employee_db import EmployeeDB
from app.services.identity_resolver import resolve_identity


# --------------------------------------------------
# Toggle geometry tuning
# --------------------------------------------------
DEBUG_GEOMETRY = False


# --------------------------------------------------
# Load Excel DB ONCE
# --------------------------------------------------
DB = EmployeeDB("employees.xlsx")


def extract_fields_from_pdf(pdf_path: str) -> Dict:
    """
    Extract employee IDs AND names from a single PDF using template_v1.
    Uses number OCR + name OCR + Excel recovery.
    """

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[PDF_TEMPLATE_V1["page"]]

        # 🔍 Full page debug
        page.to_image(resolution=200).save("debug_full_page.png")

        # ---- ID column config ----
        id_cfg = PDF_TEMPLATE_V1["employee_id_column"]
        x0_id, top, x1_id, bottom = id_cfg["bbox"]
        rows = id_cfg["rows"]

        # ---- Name column config ----
        name_cfg = PDF_TEMPLATE_V1["employee_name_column"]
        x0_nm, top2, x1_nm, bottom2 = name_cfg["bbox"]

        # --------------------------------------------------
        # Geometry debug mode
        # --------------------------------------------------
        if DEBUG_GEOMETRY:
            cropped_id = page.crop((x0_id, top, x1_id, bottom))
            cropped_nm = page.crop((x0_nm, top, x1_nm, bottom))

            cropped_id.to_image(resolution=300).save("debug_bbox_id.png")
            cropped_nm.to_image(resolution=300).save("debug_bbox_name.png")

            return {
                "debug": "geometry",
                "id_bbox": [x0_id, top, x1_id, bottom],
                "name_bbox": [x0_nm, top, x1_nm, bottom],
            }

        # --------------------------------------------------
        # Slice columns into rows
        # --------------------------------------------------
        row_height = (bottom - top) / rows

        extracted_rows: List[Dict] = []

        for i in range(rows):
            y0 = top + i * row_height
            y1 = y0 + row_height

            # --------------------
            # Crop ID cell
            # --------------------
            cropped_id = page.crop((x0_id, y0, x1_id, y1))
            pil_id = cropped_id.to_image(resolution=300).original
            pil_id.save(f"debug_row_{i}_id.png")

            id_rgb = np.array(pil_id)

            id_candidates = read_ids_from_crop(id_rgb, row_index=i)

            # --------------------
            # Crop Name cell
            # --------------------
            cropped_nm = page.crop((x0_nm, y0, x1_nm, y1))
            pil_nm = cropped_nm.to_image(resolution=300).original
            pil_nm.save(f"debug_row_{i}_name.png")

            nm_rgb = np.array(pil_nm)

            name_clean = read_name_from_crop(nm_rgb, row_index=i)

            extracted_rows.append({
                "row": i,
                "id_candidates": id_candidates,
                "ocr_name_clean": name_clean,
            })

    # --------------------------------------------------
    # Department (manual for now)
    # --------------------------------------------------
    department = "CASTHOUSE"

    dept_records = DB.get_records_for_department(department)

    # --------------------------------------------------
    # Resolve each row (number + name logic)
    # --------------------------------------------------
    resolved_rows: List[Dict] = []

    for row in extracted_rows:
        result = resolve_identity(
            number_candidates=row["id_candidates"],
            ocr_name_clean=row["ocr_name_clean"],
            dept_records=dept_records
        )

        resolved_rows.append({
            **row,
            "resolved_id": result["resolved_id"],
            "confidence": result["confidence"],
            "method": result["method"],
            "top_candidates": result["top_candidates"],
        })

    # --------------------------------------------------
    # Final unique IDs for this report
    # --------------------------------------------------
    seen = set()
    final_ids: List[Tuple[str, float]] = []

    for r in resolved_rows:
        emp_id = r["resolved_id"]

        if emp_id is None:
            continue

        if emp_id not in seen:
            seen.add(emp_id)
            final_ids.append((emp_id, r["confidence"]))

    return {
        "rows": resolved_rows,
        "final_employee_ids": final_ids
    }
