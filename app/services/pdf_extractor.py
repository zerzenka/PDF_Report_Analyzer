import pdfplumber
from typing import Dict
from app.config.template_v1 import PDF_TEMPLATE_V1


def extract_fields_from_pdf(pdf_path: str) -> Dict[str, str]:
    results = {}

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[PDF_TEMPLATE_V1["page"]]

        for field_name, bbox in PDF_TEMPLATE_V1["fields"].items():
            cropped = page.crop(bbox)
            text = cropped.extract_text()

            results[field_name] = text.strip() if text else None

    return results