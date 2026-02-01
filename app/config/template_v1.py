# app/config/template_v1.py
# Coordinates are in PDF points: (x0, top, x1, bottom)

PDF_TEMPLATE_V1 = {
    "page": 0,  # page 2 (0-based)

    "employee_id_column": {
        "bbox": (933, 453, 1004, 575),  # adjust later if needed
        "rows": 7
    },
    "employee_name_column": {
        "bbox": (750, 443, 890, 555),
        "rows": 7
    }
}