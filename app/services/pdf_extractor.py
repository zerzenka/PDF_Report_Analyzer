import pdfplumber
import numpy as np
from typing import Dict

from app.config.template_v1 import PDF_TEMPLATE_V1
from app.ocr_easyocr import read_id_from_crop


# 👇 Define which fields are handwritten (digits-only)
HANDWRITTEN_FIELDS = {
    "employee_ID",
}


def extract_fields_from_pdf(pdf_path: str) -> Dict[str, str]:
    results = {}

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[PDF_TEMPLATE_V1["page"]]

        for field_name, bbox in PDF_TEMPLATE_V1["fields"].items():
            cropped = page.crop(bbox)

            # -------- HANDWRITTEN FIELD --------
            if field_name in HANDWRITTEN_FIELDS:
                # Render cropped PDF region to image
                pil_img = cropped.to_image(resolution=300).original

                # TEMPORARY DEBUG: save cropped image to inspect
                pil_img.save("debug_employee_ID.png")

                img = np.array(pil_img)  # RGB numpy array

                value = read_id_from_crop(img)
                results[field_name] = value if value else None

            # -------- PRINTED FIELD --------
            else:
                text = cropped.extract_text()
                results[field_name] = text.strip() if text else None

    return results