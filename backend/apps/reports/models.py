import uuid

from django.db import models


class Report(models.Model):
    """Structured extraction output for one completed analysis job."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.OneToOneField(
        "documents.AnalysisJob",
        on_delete=models.CASCADE,
        related_name="report",
    )
    period = models.CharField(max_length=50)
    raw_ocr_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Report for {self.job.original_filename}"


class ExtractedField(models.Model):
    """Individual labeled field extracted from the OCR pipeline."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="fields",
    )
    label = models.CharField(max_length=100)
    value = models.CharField(max_length=255)
    confidence = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["label"]

    def __str__(self) -> str:
        return f"{self.label}: {self.value}"
