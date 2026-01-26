import pdfplumber
import numpy as np
from typing import Dict, List, Tuple, Optional

from app.config.template_v1 import PDF_TEMPLATE_V1
from app.ocr_easyocr import read_ids_from_crop

from app.services.employee_db import EmployeeDB
from app.services.db_resolver import resolve_with_db


# --------------------------------------------------
# Toggle geometry tuning
# --------------------------------------------------
DEBUG_GEOMETRY = False


# --------------------------------------------------
# Load Excel DB ONCE
# --------------------------------------------------
DB = EmployeeDB("employees.xlsx")   # <-- path to your Excel file


def extract_fields_from_pdf(pdf_path: str) -> Dict:
    """
    Extract employee IDs from a single PDF using template_v1.
    """

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[PDF_TEMPLATE_V1["page"]]

        # 🔍 Full page debug (keep)
        page.to_image(resolution=200).save("debug_full_page.png")

        col_cfg = PDF_TEMPLATE_V1["employee_id_column"]
        x0, top, x1, bottom = col_cfg["bbox"]
        rows = col_cfg["rows"]

        # --------------------------------------------------
        # Geometry debug mode
        # --------------------------------------------------
        if DEBUG_GEOMETRY:
            cropped = page.crop((x0, top, x1, bottom))
            pil_img = cropped.to_image(resolution=300).original
            pil_img.save("debug_bbox_full.png")

            return {
                "debug": "geometry",
                "bbox": [x0, top, x1, bottom]
            }

        # --------------------------------------------------
        # Slice column into rows
        # --------------------------------------------------
        row_height = (bottom - top) / rows

        all_candidates: List[List[str]] = []

        for i in range(rows):
            y0 = top + i * row_height
            y1 = y0 + row_height

            cropped = page.crop((x0, y0, x1, y1))
            pil_img = cropped.to_image(resolution=300).original

            # 🔍 per-row debug image (keep)
            pil_img.save(f"debug_row_{i}.png")

            crop_rgb = np.array(pil_img)

            raw_candidates = read_ids_from_crop(crop_rgb)

            all_candidates.append(raw_candidates)

    # --------------------------------------------------
    # Department (manual for now — later auto detect)
    # --------------------------------------------------
    department = "CASTHOUSE"

    valid_ids = DB.get_ids_for_department(department)

    # --------------------------------------------------
    # Resolve each row using Excel DB
    # --------------------------------------------------
    resolved: List[Optional[Tuple[str, float]]] = []

    for row_candidates in all_candidates:
        match = resolve_with_db(row_candidates, valid_ids)
        resolved.append(match)

    # --------------------------------------------------
    # Final unique IDs for this report
    # (one person appears once per report)
    # --------------------------------------------------
    seen = set()
    final_ids: List[Tuple[str, float]] = []

    for item in resolved:
        if item is None:
            continue

        emp_id, conf = item

        if emp_id not in seen:
            seen.add(emp_id)
            final_ids.append((emp_id, conf))

    return {
        "employee_id_candidates_by_row": all_candidates,
        "resolved_employee_ids": resolved,
        "final_employee_ids": final_ids
    }