import pdfplumber
import numpy as np
import cv2
from typing import Dict, List, Tuple

from app.config.template_ops_a3 import TEMPLATE_OPS_A3
from app.ocr_easyocr import read_ids_from_crop, read_name_from_crop, get_reader
from app.services.employee_db import EmployeeDB
from app.services.identity_resolver import resolve_identity


DEBUG_GEOMETRY = True
DEBUG_PRINT_GEOMETRY = True  # prints computed boxes once per page

DB = EmployeeDB("employees.xlsx")


# ==================================================
# Trim all sides (for names)
# ==================================================

def trim_whitespace(img, threshold=210):

    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    mask = gray < threshold
    coords = np.column_stack(np.where(mask))

    if coords.size == 0:
        return img

    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0) + 1

    return img[y0:y1, x0:x1]


# ==================================================
# Trim LEFT side only (for ID column with signature)
# ==================================================

def trim_left_only(img, threshold=210):

    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    mask = gray < threshold
    cols = np.where(mask.any(axis=0))[0]

    if cols.size == 0:
        return img

    x0 = cols.min()
    return img[:, x0:]


# ==================================================
# OCR anchor finder
# ==================================================

def find_ops_anchors_image(page):

    full_img = page.to_image(resolution=180).original

    if DEBUG_GEOMETRY:
        full_img.save("debug_full_for_anchors.png")

    img_np = np.array(full_img)

    img_h, img_w = img_np.shape[:2]

    scale_x = page.width / img_w
    scale_y = page.height / img_h

    reader = get_reader()
    results = reader.readtext(img_np, detail=1)

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

        # -----------------------------------
        # Render page once
        # -----------------------------------

        fast_img = page.to_image(resolution=180).original
        fast_np = np.array(fast_img)

        if DEBUG_GEOMETRY:
            fast_img.save(f"debug_{pdf_name}_full_page_fast.png")

        img_h, img_w = fast_np.shape[:2]

        scale_x = img_w / PAGE_W
        scale_y = img_h / PAGE_H

        # -----------------------------------
        # Anchors
        # -----------------------------------

        name_anchor, id_anchor = find_ops_anchors_image(page)

        # -----------------------------------
        # Columns (PDF-space)
        # -----------------------------------

        name_x0 = name_anchor["x1"] + cfg["pad_x"]
        name_x1 = id_anchor["x0"] - cfg["pad_x"]

        # IMPORTANT: use cfg["id_shift_left"] directly so it definitely applies
        id_shift_left = cfg["id_shift_left"]
        id_width = cfg["id_width"]

        id_x0 = id_anchor["x1"] + cfg["pad_x"] - id_shift_left
        id_x1 = id_x0 + id_width

        # Clamp
        name_x0 = max(0, name_x0)
        name_x1 = min(PAGE_W, name_x1)
        id_x0   = max(0, id_x0)
        id_x1   = min(PAGE_W, id_x1)

        if name_x1 <= name_x0 or id_x1 <= id_x0:
            raise ValueError(
                f"Invalid columns: NAME({name_x0},{name_x1}) ID({id_x0},{id_x1})"
            )

        # -----------------------------------
        # Columns (IMAGE-space)  ✅ precompute once (fix drift)
        # -----------------------------------

        nx0 = int(round(name_x0 * scale_x))
        nx1 = int(round(name_x1 * scale_x))

        ix0 = int(round(id_x0 * scale_x))
        ix1 = int(round(id_x1 * scale_x))

        if DEBUG_PRINT_GEOMETRY:
            print(f"[{pdf_name}] id_shift_left={id_shift_left} id_width={id_width}")
            print(f"[{pdf_name}] ID PDF:  x0={id_x0:.2f} x1={id_x1:.2f}")
            print(f"[{pdf_name}] ID IMG:  x0={ix0} x1={ix1}")
            print(f"[{pdf_name}] NAME IMG:x0={nx0} x1={nx1}")

        # -----------------------------------
        # Rows
        # -----------------------------------

        table_top = name_anchor["bottom"] + cfg["table_top_offset"]

        row_height = cfg["row_height"]
        row_gap = cfg["row_gap"]
        rows = cfg["rows"]

        extracted_rows: List[Dict] = []

        for i in range(rows):

            step = row_height + row_gap

            y0 = table_top + i * step
            y1 = y0 + row_height

            if y1 <= 0 or y0 >= PAGE_H:
                continue

            y0 = max(0, y0)
            y1 = min(PAGE_H, y1)

            # Y in image coords (only this changes per row)
            iy0 = int(round(y0 * scale_y))
            iy1 = int(round(y1 * scale_y))

            # crops (fast)
            id_crop_img = fast_np[iy0:iy1, ix0:ix1]
            name_crop_img = fast_np[iy0:iy1, nx0:nx1]

            if id_crop_img.size == 0 or name_crop_img.size == 0:
                continue

            # -----------------------------------
            # Resize
            # -----------------------------------

            crop_scale = 0.6

            id_crop_img = cv2.resize(
                id_crop_img, None, fx=crop_scale, fy=crop_scale,
                interpolation=cv2.INTER_AREA
            )

            name_crop_img = cv2.resize(
                name_crop_img, None, fx=crop_scale, fy=crop_scale,
                interpolation=cv2.INTER_AREA
            )

            # -----------------------------------
            # Trim correctly
            # -----------------------------------

            id_crop_img = trim_left_only(id_crop_img)       # ID: only trim left
            name_crop_img = trim_whitespace(name_crop_img)  # NAME: full trim

            if DEBUG_GEOMETRY:
                cv2.imwrite(f"debug_{pdf_name}_row_{i}_id_fast.png", id_crop_img)
                cv2.imwrite(f"debug_{pdf_name}_row_{i}_name_fast.png", name_crop_img)

            # -----------------------------------
            # OCR
            # -----------------------------------

            id_candidates = read_ids_from_crop(id_crop_img, row_index=i)
            name_clean = read_name_from_crop(name_crop_img, row_index=i)

            extracted_rows.append({
                "row": i,
                "id_candidates": id_candidates,
                "ocr_name_clean": name_clean,
            })

    # ==================================================
    # Resolve identities
    # ==================================================

    department = "CASTHOUSE"
    dept_records = DB.get_records_for_department(department)

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

    # ==================================================
    # Unique list
    # ==================================================

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