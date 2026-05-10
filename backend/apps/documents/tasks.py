import time

from celery import shared_task

from apps.documents.models import AnalysisJob


@shared_task
def process_pdf_task(job_id: str) -> None:
    """
    Async PDF pipeline stub: queued → processing → (wait) → done.

    Replace with real OCR + extraction when Azure DI is wired.
    """
    try:
        job = AnalysisJob.objects.get(pk=job_id)
    except AnalysisJob.DoesNotExist:
        return

    job.status = AnalysisJob.Status.PROCESSING
    job.save()

    time.sleep(3)

    job.refresh_from_db()
    job.status = AnalysisJob.Status.DONE
    job.save()
