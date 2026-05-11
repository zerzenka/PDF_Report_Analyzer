from celery import shared_task
from django.core.files import File

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

        detected = detect_table_rows(azure_result, job.file.path, job_id=str(job.id))

        # Replace any prior rows (re-run flow)
        DocumentRow.objects.filter(job=job).delete()

        for idx, row in enumerate(detected):
            ocr_name_raw = str(row.get("ocr_name_raw") or "").strip()
            ocr_id_raw = str(row.get("ocr_id_raw") or "").strip()

            m = match_row(ocr_name_raw, ocr_id_raw)

            dr = DocumentRow(
                job=job,
                row_index=idx,
                ocr_name_raw=ocr_name_raw,
                ocr_id_raw=ocr_id_raw,
                ocr_id_clean=str(m.get("clean_id") or ""),
                top_candidates=m.get("top_candidates") or [],
                confidence=float(m.get("confidence") or 0.0),
                match_method=str(m.get("match_method") or ""),
                status=str(m.get("recommended_status") or DocumentRow.Status.NEEDS_REVIEW),
            )

            # Attach crop images produced by the detector (relative to MEDIA_ROOT)
            name_rel = row.get("name_crop_path")
            id_rel = row.get("id_crop_path")
            if name_rel:
                with open(job.file.storage.path(name_rel), "rb") as f:
                    dr.name_crop.save(name_rel.split("/")[-1], File(f), save=False)
            if id_rel:
                with open(job.file.storage.path(id_rel), "rb") as f:
                    dr.id_crop.save(id_rel.split("/")[-1], File(f), save=False)

            dr.save()

        job.status = AnalysisJob.Status.NEEDS_REVIEW
        job.save(update_fields=["status", "updated_at"])
    except Exception as e:
        job.status = AnalysisJob.Status.ERROR
        job.error_message = str(e)
        job.save(update_fields=["status", "error_message", "updated_at"])
