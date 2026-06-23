from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from apps.documents.models import AnalysisJob, DocumentRow, MonthBatch
from apps.documents.services.matcher import match_row
from apps.documents.services.ocr_service import OCRService
from apps.documents.services.table_detector import detect_table_rows
from apps.employees.models import Department, Employee


PDF_PATH = r"C:/projects/PDF_Report_Analyzer/input_pdfs/HP Team B (SA100857-SA100740-SA101569-SA101485-SA916834-SA929400-SA100805-SA100299) (06.01.2026).pdf"


class Command(BaseCommand):
    help = "End-to-end OCR pipeline smoke test (Azure OCR → table detect → match → DocumentRow)."

    def handle(self, *args, **options):
        pdf_path = Path(PDF_PATH)
        if not pdf_path.exists():
            raise CommandError(f"PDF not found: {pdf_path}")

        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username="test_ocr",
            defaults={"email": "test_ocr@example.com"},
        )
        if hasattr(user, "set_unusable_password"):
            user.set_unusable_password()
            user.save(update_fields=["password"])

        dept, _ = Department.objects.get_or_create(
            code="TEST",
            defaults={"name": "Test Department"},
        )

        # Seed a few employees/contractors so matcher produces candidates.
        # (Real dev flow uses `import_employees`, but this keeps the command self-contained.)
        ids = re.findall(r"SA(\d{6})", pdf_path.name)
        for i, emp_id in enumerate(sorted(set(ids))):
            emp_type = "employee" if emp_id.startswith("1") else "contractor"
            Employee.objects.get_or_create(
                employee_id=emp_id,
                defaults={
                    "full_name": f"Seeded Person {i + 1} ({emp_id})",
                    "department": dept,
                    "email": "",
                    "type": emp_type,
                    "is_active": True,
                    "last_synced": None,
                },
            )

        month_date = date(2026, 1, 1)
        batch, _ = MonthBatch.objects.get_or_create(
            department=dept,
            month_label="01-2026",
            defaults={"month_date": month_date, "created_by": user},
        )
        if batch.month_date != month_date:
            batch.month_date = month_date
            batch.save(update_fields=["month_date"])

        job = AnalysisJob(
            batch=batch,
            original_filename=pdf_path.name,
            status=AnalysisJob.Status.QUEUED,
            uploaded_by=user,
        )

        with open(pdf_path, "rb") as f:
            job.file.save(pdf_path.name, File(f), save=False)

        job.save()

        self.stdout.write(f"Created job: {job.id}")
        self.stdout.write(f"File stored at: {job.file.path}")
        self.stdout.write("Running OCR pipeline synchronously...")

        job.status = AnalysisJob.Status.PROCESSING
        job.error_message = ""
        job.save(update_fields=["status", "error_message", "updated_at"])

        try:
            ocr = OCRService()
            azure_result = ocr.analyze_page(job.file.path)

            # Dump raw Azure OCR output for debugging (words + polygons, etc.)
            out_dir = Path("test_output")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "azure_raw.json"
            out_path.write_text(
                json.dumps(azure_result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.stdout.write(f"Wrote Azure OCR raw JSON to: {out_path.resolve()}")

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
                    p = Path(settings.MEDIA_ROOT) / name_rel
                    if p.is_file():
                        content = p.read_bytes()
                        p.unlink(missing_ok=True)
                        dr.name_crop.save(
                            Path(name_rel).name,
                            ContentFile(content),
                            save=False,
                        )

                id_rel = row.get("id_crop_rel")
                if id_rel:
                    p = Path(settings.MEDIA_ROOT) / id_rel
                    if p.is_file():
                        content = p.read_bytes()
                        p.unlink(missing_ok=True)
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

        job.refresh_from_db()
        self.stdout.write(f"Job status: {job.status}")
        if job.status == AnalysisJob.Status.ERROR:
            self.stdout.write(self.style.ERROR(f"error_message: {job.error_message}"))
            raise CommandError("OCR pipeline failed (see error_message above).")

        rows = DocumentRow.objects.filter(job=job).order_by("row_index")
        if not rows.exists():
            self.stdout.write(self.style.WARNING("No DocumentRow records created."))
            return

        for r in rows:
            self.stdout.write("")
            self.stdout.write(f"row_index={r.row_index}")
            self.stdout.write(f"  ocr_name_raw={r.ocr_name_raw!r}")
            self.stdout.write(f"  ocr_id_raw={r.ocr_id_raw!r}")
            self.stdout.write(f"  ocr_id_clean={r.ocr_id_clean!r}")
            self.stdout.write(f"  confidence={r.confidence:.2f}")
            self.stdout.write(f"  match_method={r.match_method!r}")
            if r.name_crop:
                np = Path(r.name_crop.path)
                self.stdout.write(
                    f"  name_crop: {r.name_crop.name} ({np.stat().st_size} bytes on disk)"
                )
            else:
                self.stdout.write("  name_crop: (none)")
            if r.id_crop:
                ip = Path(r.id_crop.path)
                self.stdout.write(
                    f"  id_crop: {r.id_crop.name} ({ip.stat().st_size} bytes on disk)"
                )
            else:
                self.stdout.write("  id_crop: (none)")

            top = (r.top_candidates or [])[:3]
            if not top:
                self.stdout.write("  top_candidates: []")
            else:
                self.stdout.write("  top_candidates (top 3):")
                for c in top:
                    emp_id = c.get("employee_id")
                    name = c.get("full_name")
                    total = c.get("total_score")
                    ns = c.get("name_score")
                    ids = c.get("id_score")
                    self.stdout.write(
                        f"    - {emp_id} — {name} (total={total}, name={ns}, id={ids})"
                    )

