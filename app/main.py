from fastapi import FastAPI

app = FastAPI(title="PDF Report Analyzer")

@app.get("/health")
def health_check():
    return {"status": "ok"}