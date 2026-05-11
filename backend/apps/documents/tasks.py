from celery import shared_task

from apps.documents.models import AnalysisJob, DocumentRow
from apps.documents.services.matcher import match_row
from apps.documents.services.ocr_service import OCRService
from apps.documents.services.table_detector import detect_table_rows


@shared_task
def process_pdf_task(job_id: str) -> None:
    try:
        job = AnalysisJob.objects.get(pk=job_id)
    except AnalysisJob.DoesNotExist:
        return

    job.status = AnalysisJob.Status.PROCESSING
    job.error_message = ""
    job.save(update_fields=["status", "error_message", "updated_at"])

    try:
        ocr = OCRService()
        azure_result = ocr.analyze_page(job.file.path)

        pages = azure_result.get("pages") or []
        job.page_count = len(pages) or None
        job.save(update_fields=["page_count", "updated_at"])

        detected = detect_table_rows(azure_result)

        # Replace any prior rows (re-run flow)
        DocumentRow.objects.filter(job=job).delete()

        for idx, row in enumerate(detected):
            ocr_name_raw = str(row.get("ocr_name_raw") or "").strip()
            ocr_id_raw = str(row.get("ocr_id_raw") or "").strip()
            ocr_id_clean = str(row.get("ocr_id_clean") or "").strip()

            m = match_row(ocr_name_raw, ocr_id_raw)

            dr = DocumentRow(
                job=job,
                row_index=int(row.get("row_index", idx)),
                ocr_name_raw=ocr_name_raw,
                ocr_id_raw=ocr_id_raw,
                ocr_id_clean=ocr_id_clean or str(m.get("clean_id") or ""),
                top_candidates=m.get("top_candidates") or [],
                confidence=float(m.get("confidence") or 0.0),
                match_method=str(m.get("match_method") or ""),
                status=str(m.get("recommended_status") or DocumentRow.Status.NEEDS_REVIEW),
            )

            dr.save()

        job.status = AnalysisJob.Status.NEEDS_REVIEW
        job.save(update_fields=["status", "updated_at"])
    except Exception as e:
        job.status = AnalysisJob.Status.ERROR
        job.error_message = str(e)
        job.save(update_fields=["status", "error_message", "updated_at"])
