from app.services.ocr_extractor import extract_numbers_from_box

pdf_path = r"C:\Users\sa101685\PDF_Report_Analyzer\uploaded_pdfs\HP_Template.pdf"  # <-- change this
bbox = (850, 200, 1030, 420)                     # starting guess

result = extract_numbers_from_box(pdf_path, bbox)
print("Extracted IDs:", result)