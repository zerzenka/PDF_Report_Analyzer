import base64
from pathlib import Path
import pdfplumber
import numpy as np
import cv2
from typing import Dict, List, Tuple, Optional

from app.config.template_ops_a3 import TEMPLATE_OPS_A3
from app.ocr_easyocr import read_ids_from_crops, read_names_from_crops, get_reader
from app.services.employee_db import EmployeeDB
from app.services.identity_resolver import resolve_identity


DEBUG_GEOMETRY = False
DEBUG_PRINT_GEOMETRY = False  # prints computed boxes once per page

# If True, embed base64 crops into JSON response (slower + bigger JSON)
# For the "export package" architecture, set this False.
EMBED_DATA_URLS_DEFAULT = False

DB = EmployeeDB("employees.xlsx")


# ==================================================
# Helpers: encode crops for UI (optional)
# ==================================================
def img_to_data_url(img: np.ndarray) -> str:
    """
    Encode a numpy image (BGR or grayscale) into a PNG data URL.
    Allows frontend to show crops without saving files.
    """
    if img is None or img.size == 0:
        return ""

    if img.dtype != np.uint8:
        img = img.astype(np.uint8)

    ok, buf = cv2.imencode(".png", img)
    if not ok:
        return ""

    b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def _ensure_dir(p: Optional[str]) -> Optional[Path]:
    if not p:
        return None
    out = Path(p)
    out.mkdir(parents=True, exist_ok=True)
    return out


# ==================================================
# Trim all sides (for names)
# ==================================================
def trim_whitespace(img: np.ndarray, threshold: int = 210) -> np.ndarray:
    if img is None or img.size == 0:
        return img

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
def trim_left_only(img: np.ndarray, threshold: int = 210) -> np.ndarray:
    if img is None or img.size == 0:
        return img

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
def find_ops_anchors_image(img_np: np.ndarray, page_w: float, page_h: float):
    """
    Find NAME / SA ID anchors using OCR on the already-rendered page image.
    Returns anchors in PDF coordinate space.
    """
    img_h, img_w = img_np.shape[:2]

    scale_x = page_w / img_w
    scale_y = page_h / img_h

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
            "text": txt,
            "conf": conf,
        }

        if "NAME" in txt:
            name_candidates.append(anchor)

        if "SA" in txt and "ID" in txt:
            id_candidates.append(anchor)

    if not name_candidates or not id_candidates:
        raise ValueError("Could not detect NAME / SA ID anchors")

    PAGE_H = page_h

    def is_middle(a):
        return PAGE_H * 0.3 < a["top"] < PAGE_H * 0.7

    # Pick anchors in the middle region (table header area)
    name_anchor = next(a for a in name_candidates if is_middle(a))
    id_anchor = next(a for a in id_candidates if is_middle(a))

    return name_anchor, id_anchor


# ==================================================
# Main extractor
# ==================================================
def extract_fields_from_pdf(
    pdf_path: str,
    out_dir: str | None = None,
    embed_data_urls: bool = EMBED_DATA_URLS_DEFAULT,
) -> Dict:
    """
    If out_dir is provided:
      - saves row crops as PNGs into out_dir
      - writes id_crop_path / name_crop_path (relative filenames) into rows

    If embed_data_urls is True:
      - embeds base64 data urls into rows (big JSON; OK for single-PDF local UI)
    """

    cfg = TEMPLATE_OPS_A3
    out_path = _ensure_dir(out_dir)

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[cfg["page"]]
        pdf_name = Path(pdf_path).stem

        PAGE_W = page.width
        PAGE_H = page.height

        # -----------------------------------
        # Render page once (FAST)
        # -----------------------------------
        fast_img = page.to_image(resolution=180).original
        fast_np = np.array(fast_img)

        if DEBUG_GEOMETRY:
            fast_img.save(f"debug_{pdf_name}_full_page_fast.png")

        img_h, img_w = fast_np.shape[:2]
        sx = img_w / PAGE_W
        sy = img_h / PAGE_H

        # -----------------------------------
        # Anchors
        # -----------------------------------
        name_anchor, id_anchor = find_ops_anchors_image(fast_np, PAGE_W, PAGE_H)

        # -----------------------------------
        # Columns (PDF-space)
        # -----------------------------------
        name_x0 = name_anchor["x1"] + cfg["pad_x"]
        name_x1 = id_anchor["x0"] - cfg["pad_x"]

        id_shift_left = cfg.get("id_shift_left", 0)
        id_width = cfg["id_width"]

        id_x0 = id_anchor["x1"] + cfg["pad_x"] - id_shift_left
        id_x1 = id_x0 + id_width

        # Clamp
        name_x0 = max(0, name_x0)
        name_x1 = min(PAGE_W, name_x1)
        id_x0 = max(0, id_x0)
        id_x1 = min(PAGE_W, id_x1)

        if name_x1 <= name_x0 or id_x1 <= id_x0:
            raise ValueError(
                f"Invalid columns: NAME({name_x0},{name_x1}) ID({id_x0},{id_x1})"
            )

        # -----------------------------------
        # Columns (IMAGE-space) precompute once (fix drift)
        # -----------------------------------
        nx0 = int(round(name_x0 * sx))
        nx1 = int(round(name_x1 * sx))
        ix0 = int(round(id_x0 * sx))
        ix1 = int(round(id_x1 * sx))

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

        crop_scale_name = cfg.get("crop_scale_name", 0.6)
        crop_scale_id = cfg.get("crop_scale_id", 0.6)

        extracted_rows: List[Dict] = []
        id_crops: List[np.ndarray] = []
        name_crops: List[np.ndarray] = []
        row_indices: List[int] = []

        for i in range(rows):
            step = row_height + row_gap

            y0 = table_top + i * step
            y1 = y0 + row_height

            if y1 <= 0 or y0 >= PAGE_H:
                continue

            y0 = max(0, y0)
            y1 = min(PAGE_H, y1)

            iy0 = int(round(y0 * sy))
            iy1 = int(round(y1 * sy))

            # crops (fast)
            id_crop_img = fast_np[iy0:iy1, ix0:ix1]
            name_crop_img = fast_np[iy0:iy1, nx0:nx1]

            if id_crop_img.size == 0 or name_crop_img.size == 0:
                continue

            # Resize (optional)
            if crop_scale_id != 1.0:
                id_crop_img = cv2.resize(
                    id_crop_img,
                    None,
                    fx=crop_scale_id,
                    fy=crop_scale_id,
                    interpolation=cv2.INTER_AREA,
                )

            if crop_scale_name != 1.0:
                name_crop_img = cv2.resize(
                    name_crop_img,
                    None,
                    fx=crop_scale_name,
                    fy=crop_scale_name,
                    interpolation=cv2.INTER_AREA,
                )

            # Trim
            id_crop_trim = trim_left_only(id_crop_img)
            name_crop_trim = trim_whitespace(name_crop_img)

            if DEBUG_GEOMETRY:
                cv2.imwrite(f"debug_{pdf_name}_row_{i}_id_fast.png", id_crop_trim)
                cv2.imwrite(f"debug_{pdf_name}_row_{i}_name_fast.png", name_crop_trim)

            # Save crops for export package
            id_crop_path = None
            name_crop_path = None

            if out_path is not None:
                id_crop_path = f"row_{i}_id.png"
                name_crop_path = f"row_{i}_name.png"
                cv2.imwrite(str(out_path / id_crop_path), id_crop_trim)
                cv2.imwrite(str(out_path / name_crop_path), name_crop_trim)

            extracted_rows.append(
                {
                    "row": i,
                    "id_candidates": [],  # filled after batched OCR
                    "ocr_name_clean": "",  # filled after batched OCR
                    "id_crop_path": id_crop_path,
                    "name_crop_path": name_crop_path,
                    **(
                        {
                            "id_crop_data_url": img_to_data_url(id_crop_trim),
                            "name_crop_data_url": img_to_data_url(name_crop_trim),
                        }
                        if embed_data_urls
                        else {}
                    ),
                }
            )

            id_crops.append(id_crop_trim)
            name_crops.append(name_crop_trim)
            row_indices.append(i)

        # -----------------------------------
        # OCR (batched)
        # -----------------------------------
        if id_crops:
            ids_per_row = read_ids_from_crops(id_crops)
            names_per_row = read_names_from_crops(name_crops)

            for k, row_idx in enumerate(row_indices):
                # extracted_rows is built in same order as row_indices
                extracted_rows[k]["id_candidates"] = ids_per_row[k]
                extracted_rows[k]["ocr_name_clean"] = names_per_row[k]

    # ==================================================
    # Resolve identities
    # ==================================================
    department = "CASTHOUSE"
    dept_records = DB.get_records_for_department(department)

    # Build lookup id->name (works for tuple OR dict)
    id_to_name: Dict[str, str] = {}

    for rec in dept_records:
        if isinstance(rec, tuple):
            emp_id = rec[0]
            emp_name = rec[1] if len(rec) > 1 else None
        else:
            emp_id = rec.get("emp_id")
            emp_name = rec.get("name")

        if emp_id:
            id_to_name[str(emp_id)] = emp_name or ""

    resolved_rows: List[Dict] = []

    for row in extracted_rows:
        result = resolve_identity(
            number_candidates=row["id_candidates"],
            ocr_name_clean=row["ocr_name_clean"],
            dept_records=dept_records,
        )

        resolved_id = result.get("resolved_id")
        resolved_name = id_to_name.get(str(resolved_id), "") if resolved_id else ""

        resolved_rows.append({
            **row,
            "resolved_id": resolved_id,
            "resolved_name": resolved_name,
            "confidence": result.get("confidence", 0),
            "method": result.get("method", ""),
            "top_candidates": result.get("top_candidates", []),
        })

    # ==================================================
    # Unique list
    # ==================================================
    seen = set()
    final_ids: List[Tuple[str, float]] = []

    for r in resolved_rows:
        rid = r.get("resolved_id")
        if rid and rid not in seen:
            seen.add(rid)
            final_ids.append((rid, float(r.get("confidence", 0))))

    return {
        "rows": resolved_rows,
        "final_employee_ids": final_ids,
    }