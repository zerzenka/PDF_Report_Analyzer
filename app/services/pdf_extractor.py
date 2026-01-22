import pdfplumber
import numpy as np
from typing import Dict, List

from app.config.template_v1 import PDF_TEMPLATE_V1
from app.ocr_easyocr import read_ids_from_crop


# --------------------------------------------------
# Toggle this while tuning geometry
# --------------------------------------------------
DEBUG_GEOMETRY = False   # 🔁 set to False after bbox is correct


def extract_fields_from_pdf(pdf_path: str) -> Dict[str, List[List[str]]]:
    """
    Extract employee ID candidates from the PDF using template_v1.
    """

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[PDF_TEMPLATE_V1["page"]]

        # --------------------------------------------------
        # FULL PAGE DEBUG (once)
        # --------------------------------------------------
        page.to_image(resolution=200).save("debug_full_page.png")

        col_cfg = PDF_TEMPLATE_V1["employee_id_column"]
        x0, top, x1, bottom = col_cfg["bbox"]
        rows = col_cfg["rows"]

        # --------------------------------------------------
        # DEBUG MODE: show FULL bbox only
        # --------------------------------------------------
        if DEBUG_GEOMETRY:
            cropped = page.crop((x0, top, x1, bottom))
            pil_img = cropped.to_image(resolution=300).original
            pil_img.save("debug_bbox_full.png")

            # Return early – no OCR, no rows
            return {
                "debug": "geometry",
                "bbox": [x0, top, x1, bottom]
            }

        # --------------------------------------------------
        # NORMAL MODE: slice into rows
        # --------------------------------------------------
        row_height = (bottom - top) / rows

        all_candidates: List[List[str]] = []

        for i in range(rows):
            y0 = top + i * row_height
            y1 = y0 + row_height

            cropped = page.crop((x0, y0, x1, y1))
            pil_img = cropped.to_image(resolution=300).original

            # 🔍 per-row debug image (VERY IMPORTANT)
            pil_img.save(f"debug_row_{i}.png")

            crop_rgb = np.array(pil_img)
            candidates = read_ids_from_crop(crop_rgb, row_index=i)
            all_candidates.append(candidates)

    return {
        "employee_id_candidates_by_row": all_candidates
    }
