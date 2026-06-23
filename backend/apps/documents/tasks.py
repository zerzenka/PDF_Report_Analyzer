from __future__ import annotations

import logging
import uuid
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from rest_framework import serializers

from apps.documents.models import AnalysisJob, DocumentRow, MonthBatch
from apps.documents.serializers import parse_month_label
from apps.documents.services.matcher import match_row
from apps.documents.services.ocr_service import OCRService
from apps.documents.services.table_detector import detect_table_rows
from apps.employees.models import Department

logger = logging.getLogger(__name__)


def _watch_folder_system_user():
    User = get_user_model()
    return User.objects.filter(is_superuser=True).order_by("pk").first() or User.objects.order_by(
        "pk"
    ).first()


@shared_task
def sync_employees_from_source_db() -> None:
    """Placeholder for weekly employee/contractor sync from source SQL databases."""
    return


@shared_task
def scan_watch_folder() -> None:
    """
    Scan ``WATCH_ROOT/<DepartmentName>/<MM-YYYY>/*.pdf`` and enqueue new analysis jobs.

    One bad file must not stop the rest of the scan (handled per file).
    """
    raw_root = getattr(settings, "WATCH_ROOT", "") or ""
    watch_root = Path(raw_root).expanduser()
    if not watch_root.is_dir():
        logger.warning("scan_watch_folder: WATCH_ROOT is not a directory: %s", watch_root)
        return

    user = _watch_folder_system_user()
    if user is None:
        logger.error(
            "scan_watch_folder: no Django user found; need a user for MonthBatch.created_by "
            "and AnalysisJob.uploaded_by.",
        )
        return

    try:
        for dept_entry in sorted(watch_root.iterdir(), key=lambda p: p.name.lower()):
            if not dept_entry.is_dir():
                continue
            folder_name = dept_entry.name
            try:
                department = Department.objects.get(name__iexact=folder_name)
            except Department.DoesNotExist:
                logger.warning(
                    "scan_watch_folder: no Department matching folder name %r — skipping",
                    folder_name,
                )
                continue
            except Exception:
                logger.exception(
                    "scan_watch_folder: error resolving department for folder %r",
                    folder_name,
                )
                continue

            for month_entry in sorted(dept_entry.iterdir(), key=lambda p: p.name):
                if not month_entry.is_dir():
                    continue
                month_folder_name = month_entry.name
                try:
                    month_date = parse_month_label(month_folder_name)
                except serializers.ValidationError:
                    logger.warning(
                        "scan_watch_folder: invalid month folder %r under %r — skipping",
                        month_folder_name,
                        folder_name,
                    )
                    continue

                month_label = month_folder_name.strip()
                pdf_paths = [
                    p
                    for p in sorted(month_entry.iterdir(), key=lambda x: x.name.lower())
                    if p.is_file() and p.suffix.lower() == ".pdf"
                ]
                if not pdf_paths:
                    continue

                try:
                    batch, _ = MonthBatch.objects.get_or_create(
                        department=department,
                        month_label=month_label,
                        defaults={"month_date": month_date, "created_by": user},
                    )
                except Exception:
                    logger.exception(
                        "scan_watch_folder: failed to get/create MonthBatch for %s/%s",
                        folder_name,
                        month_folder_name,
                    )
                    continue

                for pdf_path in pdf_paths:
                    try:
                        _ingest_watch_pdf(pdf_path, batch, department, user, month_label)
                    except Exception:
                        logger.exception(
                            "scan_watch_folder: error processing file %s",
                            pdf_path,
                        )
    except Exception:
        logger.exception("scan_watch_folder: unexpected error while scanning %s", watch_root)


def _ingest_watch_pdf(
    pdf_path: Path,
    batch: MonthBatch,
    department: Department,
    user,
    month_label: str,
) -> None:
    original_filename = pdf_path.name
    if AnalysisJob.objects.filter(
        batch=batch,
        original_filename=original_filename,
        deleted=False,
    ).exists():
        return

    dest_name = f"{uuid.uuid4().hex}_{original_filename}"
    data = pdf_path.read_bytes()

    job = AnalysisJob(
        batch=batch,
        uploaded_by=user,
        original_filename=original_filename,
        status=AnalysisJob.Status.QUEUED,
    )
    job.file.save(dest_name, ContentFile(data), save=True)
    logger.info(
        "Found new file: %s in %s/%s",
        original_filename,
        department.name,
        month_label,
    )
    process_pdf_task.delay(str(job.id))


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

            if not ocr_name_raw and not ocr_id_raw:
                continue

            m = match_row(ocr_name_raw, ocr_id_raw)

            dr = DocumentRow(
                job=job,
                row_index=int(row.get("row_index", idx)),
                is_task_leader=bool(row.get("is_task_leader", False)),
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
