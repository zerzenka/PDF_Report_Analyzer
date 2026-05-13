import uuid

from django.conf import settings
from django.db import models


class MonthBatch(models.Model):
    department = models.ForeignKey("employees.Department", on_delete=models.CASCADE)
    month_label = models.CharField(max_length=7)  # e.g. "05-2026"
    month_date = models.DateField()  # first day: 2026-05-01
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("department", "month_label")
        ordering = ["-month_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.department} {self.month_label}"


class AnalysisJob(models.Model):
    """Tracks each uploaded PDF through its lifecycle."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        NEEDS_REVIEW = "needs_review", "Needs Review"
        RESOLVED = "resolved", "Resolved"
        ERROR = "error", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        MonthBatch,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file = models.FileField(upload_to="uploads/")
    original_filename = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    page_count = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    deleted = models.BooleanField(default=False)  # soft delete
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.status})"


class DocumentRow(models.Model):
    class Status(models.TextChoices):
        AUTO_RESOLVED = "auto_resolved", "Auto Resolved"
        NEEDS_REVIEW = "needs_review", "Needs Review"
        RESOLVED = "resolved", "Resolved"

    job = models.ForeignKey(AnalysisJob, on_delete=models.CASCADE, related_name="rows")
    row_index = models.IntegerField()

    # OCR raw output
    ocr_name_raw = models.CharField(max_length=255, blank=True)
    ocr_id_raw = models.CharField(max_length=50, blank=True)
    ocr_id_clean = models.CharField(max_length=10, blank=True)  # stripped of SA prefix

    # Crop images
    name_crop = models.ImageField(upload_to="crops/", null=True)
    id_crop = models.ImageField(upload_to="crops/", null=True)

    # Matching
    top_candidates = models.JSONField(default=list)  # top 5 with scores
    confidence = models.FloatField(default=0.0)
    match_method = models.CharField(max_length=50, blank=True)

    # Resolution
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEEDS_REVIEW,
    )
    resolved_employee = models.ForeignKey(
        "employees.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    resolved_manually = models.BooleanField(default=False)
    added_manually = models.BooleanField(default=False)  # added outside table
    unresolvable = models.BooleanField(default=False)  # blank row / excluded from HP counts
    resolved_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["job_id", "row_index"]

    def __str__(self) -> str:
        return f"{self.job_id} row {self.row_index}"


class HPRecord(models.Model):
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="hp_records",
    )
    document_row = models.OneToOneField(DocumentRow, on_delete=models.CASCADE)
    job = models.ForeignKey(AnalysisJob, on_delete=models.CASCADE)
    department = models.ForeignKey("employees.Department", on_delete=models.CASCADE)
    month_batch = models.ForeignKey(MonthBatch, on_delete=models.CASCADE)
    month_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["employee", "month_date"]),
            models.Index(fields=["department", "month_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee.employee_id} {self.month_date}"
