from app.services.pdf_extractor import extract_fields_from_pdf
from fastapi import FastAPI, UploadFile, File, HTTPException
from pathlib import Path
import shutil

app = FastAPI(title="PDF Report Analyzer")

UPLOAD_DIR = Path("uploaded_pdfs")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    file_path = UPLOAD_DIR / file.filename

    # 1️⃣ Save the uploaded PDF
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2️⃣ Extract data from the saved PDF
    extracted_data = extract_fields_from_pdf(str(file_path))

    # 3️⃣ Return extracted data instead of just file info
    return {
        "filename": file.filename,
        "extracted_data": extracted_data
    }