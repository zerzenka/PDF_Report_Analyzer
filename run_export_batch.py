import os

from app.services.export_batch import build_export_package

SHARED_ROOT = r"I:\60 - Services\30 - BI\010 - Shared\HP_app"

INPUT_DIR = os.getenv("HP_INPUT_DIR", SHARED_ROOT + r"\incoming_pdfs")
EXPORTS_ROOT = os.getenv("HP_EXPORTS_ROOT", SHARED_ROOT + r"\exports")
EMPLOYEES_XLSX = os.getenv("HP_EMPLOYEES_XLSX", SHARED_ROOT + r"\employees.xlsx")  # optional

if __name__ == "__main__":
    summary = build_export_package(
        input_dir=INPUT_DIR,
        exports_root=EXPORTS_ROOT,
        employees_xlsx_path=EMPLOYEES_XLSX,
    )
    print(summary)