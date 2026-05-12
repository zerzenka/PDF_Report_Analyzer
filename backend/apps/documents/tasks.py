from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile

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

        detected = detect_table_rows(
            azure_result,
            pdf_path=job.file.path,
            job_id=str(job.id),
        )

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

            name_rel = row.get("name_crop_rel")
            if name_rel:
                path = Path(settings.MEDIA_ROOT) / name_rel
                if path.is_file():
                    content = path.read_bytes()
                    path.unlink(missing_ok=True)
                    dr.name_crop.save(
                        Path(name_rel).name,
                        ContentFile(content),
                        save=False,
                    )

            id_rel = row.get("id_crop_rel")
            if id_rel:
                path = Path(settings.MEDIA_ROOT) / id_rel
                if path.is_file():
                    content = path.read_bytes()
                    path.unlink(missing_ok=True)
                    dr.id_crop.save(
                        Path(id_rel).name,
                        ContentFile(content),
                        save=False,
                    )

            dr.save()

        job.status = AnalysisJob.Status.NEEDS_REVIEW
        job.save(update_fields=["status", "updated_at"])
    except Exception as e:
        job.status = AnalysisJob.Status.ERROR
        job.error_message = str(e)
        job.save(update_fields=["status", "error_message", "updated_at"])
