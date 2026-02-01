from fastapi import FastAPI, UploadFile, File, HTTPException
from pathlib import Path
import shutil

from app.services.pdf_extractor import extract_fields_from_pdf
from app.services.batch_processor import process_pdf_batch

app = FastAPI(title="PDF Report Analyzer")

# --------------------------------------------------
# Upload folder
# --------------------------------------------------
UPLOAD_DIR = Path("uploaded_pdfs")
UPLOAD_DIR.mkdir(exist_ok=True)


# --------------------------------------------------
# Health check
# --------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "ok"}


# --------------------------------------------------
# Upload & process ONE PDF
# --------------------------------------------------
@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    file_path = UPLOAD_DIR / file.filename

    # Save file
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Process immediately
    extracted_data = extract_fields_from_pdf(str(file_path))

    return {
        "filename": file.filename,
        "extracted_data": extracted_data
    }


# --------------------------------------------------
# Process ALL PDFs in folder (batch)
# --------------------------------------------------
@app.post("/process-batch")
def process_batch():

    pdfs = list(UPLOAD_DIR.glob("*.pdf")) + list(UPLOAD_DIR.glob("*.PDF"))

    if not pdfs:
        raise HTTPException(status_code=400, detail="No PDFs found in upload folder")

    results = process_pdf_batch(UPLOAD_DIR)

    return results

