import pdfplumber
import numpy as np
from typing import Dict, List, Tuple

from app.config.template_ops_a3 import TEMPLATE_OPS_A3
from app.ocr_easyocr import read_ids_from_crop, read_name_from_crop, get_reader
from app.services.employee_db import EmployeeDB
from app.services.identity_resolver import resolve_identity


DEBUG_GEOMETRY = True

DB = EmployeeDB("employees.xlsx")


# ==================================================
# OCR anchor finder (full page + scaling)
# ==================================================
def find_ops_anchors_image(page):

    full_img = page.to_image(resolution=300).original

    if DEBUG_GEOMETRY:
        full_img.save("debug_full_for_anchors.png")

    img_w, img_h = full_img.size
    scale_x = page.width / img_w
    scale_y = page.height / img_h

    reader = get_reader()
    results = reader.readtext(np.array(full_img), detail=1)

    name_candidates = []
    id_candidates = []

    for (bbox, text, conf) in results:

        txt = text.strip().upper()

        x0 = min(p[0] for p in bbox) * scale_x
        x1 = max(p[0] for p in bbox) * scale_x
        y0 = min(p[1] for p in bbox) * scale_y
        y1 = max(p[1] for p in bbox) * scale_y

        anchor = {
            "x0": x0,
            "x1": x1,
            "top": y0,
            "bottom": y1,
            "text": txt
        }

        if "NAME" in txt:
            name_candidates.append(anchor)

        if "SA" in txt and "ID" in txt:
            id_candidates.append(anchor)

    if not name_candidates or not id_candidates:
        raise ValueError("Could not detect NAME / SA ID anchors")

    # pick LOWER (table header)
    PAGE_H = page.height

    def is_middle(a):
        return PAGE_H * 0.3 < a["top"] < PAGE_H * 0.7

    name_anchor = next(a for a in name_candidates if is_middle(a))
    id_anchor   = next(a for a in id_candidates if is_middle(a))


    return name_anchor, id_anchor


# ==================================================
# Main extractor
# ==================================================
def extract_fields_from_pdf(pdf_path: str) -> Dict:

    cfg = TEMPLATE_OPS_A3

    with pdfplumber.open(pdf_path) as pdf:

        page = pdf.pages[cfg["page"]]
        pdf_name = pdf_path.split("\\")[-1].replace(".pdf", "")

        PAGE_W = page.width
        PAGE_H = page.height

        if DEBUG_GEOMETRY:
            page.to_image(resolution=200).save(
                f"debug_{pdf_name}_full_page.png"
            )

        # -----------------------------
        # Find anchors
        # -----------------------------
        name_anchor, id_anchor = find_ops_anchors_image(page)

        # -----------------------------
        # Handwriting columns
        # -----------------------------

        # NAME values are right of printed NAME up to SA ID
        name_x0 = name_anchor["x1"] + cfg["pad_x"]
        name_x1 = id_anchor["x0"] - cfg["pad_x"]

        # SA ID values are right of printed SA ID
        id_x0 = id_anchor["x1"] + cfg["pad_x"]
        id_x1 = min(PAGE_W, id_x0 + 220)

        # safety clamp
        name_x0 = max(0, name_x0)
        name_x1 = min(PAGE_W, name_x1)
        id_x0   = max(0, id_x0)
        id_x1   = min(PAGE_W, id_x1)

        if name_x1 <= name_x0 or id_x1 <= id_x0:
            raise ValueError(
                f"Invalid columns: "
                f"NAME({name_x0},{name_x1}) ID({id_x0},{id_x1})"
            )

        # -----------------------------
        # Vertical table layout
        # -----------------------------

        # start directly under header row
        table_top = name_anchor["bottom"] + cfg["table_top_offset"]

        row_height = cfg["row_height"]
        rows = cfg["rows"]

        extracted_rows: List[Dict] = []

        # -----------------------------
        # Loop rows
        # -----------------------------
        for i in range(rows):

            y0 = table_top + i * row_height
            y1 = y0 + row_height

            y0 = max(0, y0)
            y1 = min(PAGE_H, y1)

            if y1 <= y0:
                continue

            # ---- SA ID ----
            id_crop = page.crop((id_x0, y0, id_x1, y1))
            id_img = id_crop.to_image(resolution=300).original

            if DEBUG_GEOMETRY:
                id_img.save(f"debug_{pdf_name}_row_{i}_id.png")

            id_candidates = read_ids_from_crop(
                np.array(id_img),
                row_index=i
            )

            # ---- NAME ----
            name_crop = page.crop((name_x0, y0, name_x1, y1))
            name_img = name_crop.to_image(resolution=300).original

            if DEBUG_GEOMETRY:
                name_img.save(f"debug_{pdf_name}_row_{i}_name.png")

            name_clean = read_name_from_crop(
                np.array(name_img),
                row_index=i
            )

            extracted_rows.append({
                "row": i,
                "id_candidates": id_candidates,
                "ocr_name_clean": name_clean,
            })

    # -----------------------------
    # Department
    # -----------------------------
    department = "CASTHOUSE"
    dept_records = DB.get_records_for_department(department)

    # -----------------------------
    # Resolve identity
    # -----------------------------
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

    # -----------------------------
    # Unique employees
    # -----------------------------
    seen = set()
    final_ids: List[Tuple[str, float]] = []

    for r in resolved_rows:
        if r["resolved_id"] and r["resolved_id"] not in seen:
            seen.add(r["resolved_id"])
            final_ids.append((r["resolved_id"], r["confidence"]))

    return {
        "rows": resolved_rows,
        "final_employee_ids": final_ids
    }