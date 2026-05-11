from __future__ import annotations

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import ListCreateAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import AnalysisJob, DocumentRow, HPRecord, MonthBatch
from apps.documents.permissions import is_admin_user
from apps.documents.serializers import (
    AnalysisJobDetailSerializer,
    AnalysisJobListSerializer,
    DocumentRowAddSerializer,
    DocumentRowResolveSerializer,
    DocumentRowSerializer,
    MonthBatchSerializer,
    annotate_batch_queryset,
)
from apps.documents.tasks import process_pdf_task


def _focal_department(user):
    profile = getattr(user, "userprofile", None)
    return profile.department if profile else None


def _assert_job_department_access(user, job: AnalysisJob) -> None:
    if is_admin_user(user):
        return
    dept = _focal_department(user)
    if dept is None or job.batch.department_id != dept.id:
        raise PermissionDenied("You do not have access to this document.")


def _assert_batch_department_access(user, batch: MonthBatch) -> None:
    if is_admin_user(user):
        return
    dept = _focal_department(user)
    if dept is None or batch.department_id != dept.id:
        raise PermissionDenied("You do not have access to this batch.")


class MonthBatchListCreateView(ListCreateAPIView):
    """GET/POST /api/batches/"""

    permission_classes = [IsAuthenticated]
    serializer_class = MonthBatchSerializer

    def get_queryset(self):
        qs = annotate_batch_queryset(
            MonthBatch.objects.all().select_related("department", "created_by")
        )
        if is_admin_user(self.request.user):
            return qs.order_by("-month_date", "-created_at")
        dept = _focal_department(self.request.user)
        if dept is None:
            return MonthBatch.objects.none()
        return qs.filter(department=dept).order_by("-month_date", "-created_at")


class DocumentUploadView(APIView):
    """
    POST multipart/form-data with ``batch_id`` (MonthBatch pk) and one or more PDFs.

    Use ``files`` or ``file`` keys for uploads.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        batch_id = request.POST.get("batch_id") or request.data.get("batch_id")
        if not batch_id:
            return Response(
                {"detail": "batch_id is required (MonthBatch primary key)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            batch = MonthBatch.objects.get(pk=int(batch_id))
        except (ValueError, MonthBatch.DoesNotExist):
            return Response(
                {"detail": "Invalid batch_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            _assert_batch_department_access(request.user, batch)
        except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)

        uploads = request.FILES.getlist("files")
        if not uploads:
            uploads = request.FILES.getlist("file")

        if not uploads:
            return Response(
                {"detail": "No PDF files provided. Use `files` or `file`."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        errors = []

        for f in uploads:
            name = getattr(f, "name", "") or ""
            if not name.lower().endswith(".pdf"):
                errors.append({"filename": name, "detail": "Not a PDF."})
                continue

            job = AnalysisJob.objects.create(
                batch=batch,
                uploaded_by=request.user,
                original_filename=name,
                file=f,
                status=AnalysisJob.Status.QUEUED,
            )
            process_pdf_task.delay(str(job.id))
            created.append(
                {
                    "id": str(job.id),
                    "filename": job.original_filename,
                    "status": job.status,
                }
            )

        if not created:
            return Response(
                {"jobs": [], "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"jobs": created, "errors": errors},
            status=status.HTTP_201_CREATED,
        )


class DocumentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        qs = (
            AnalysisJob.objects.filter(deleted=False)
            .select_related("batch", "batch__department", "uploaded_by")
            .prefetch_related("rows", "rows__resolved_employee")
        )
        if is_admin_user(self.request.user):
            qs = qs.order_by("-created_at")
        else:
            dept = _focal_department(self.request.user)
            if dept is None:
                return AnalysisJob.objects.none()
            qs = qs.filter(batch__department=dept).order_by("-created_at")

        batch_id = self.request.query_params.get("batch")
        if batch_id is not None and self.action == "list":
            try:
                bid = int(batch_id)
            except (TypeError, ValueError):
                return AnalysisJob.objects.none()
            batch = MonthBatch.objects.filter(pk=bid).first()
            if batch is None:
                return AnalysisJob.objects.none()
            try:
                _assert_batch_department_access(self.request.user, batch)
            except PermissionDenied:
                return AnalysisJob.objects.none()
            qs = qs.filter(batch_id=bid)

        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return AnalysisJobDetailSerializer
        return AnalysisJobListSerializer

    def get_object(self):
        job = super().get_object()
        _assert_job_department_access(self.request.user, job)
        return job

    def destroy(self, request, *args, **kwargs):
        job = self.get_object()
        job.deleted = True
        job.save(update_fields=["deleted", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="rerun")
    def rerun(self, request, pk=None):
        """Re-queue a failed document for OCR/processing."""
        job = self.get_object()
        if job.status != AnalysisJob.Status.ERROR:
            return Response(
                {"detail": "Only documents in error state can be re-run."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        job.status = AnalysisJob.Status.QUEUED
        job.error_message = ""
        job.save(update_fields=["status", "error_message", "updated_at"])
        process_pdf_task.delay(str(job.id))
        return Response(AnalysisJobDetailSerializer(job).data)

    @action(
        detail=True,
        methods=["patch"],
        url_path=r"rows/(?P<row_id>[0-9]+)/resolve",
    )
    def resolve_row(self, request, pk=None, row_id=None):
        job = self.get_object()
        try:
            row = DocumentRow.objects.get(pk=row_id, job=job)
        except DocumentRow.DoesNotExist:
            raise NotFound("Row not found.")

        ser = DocumentRowResolveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        emp = ser.validated_data["resolved_employee"]

        row.resolved_employee = emp
        row.status = DocumentRow.Status.RESOLVED
        row.resolved_manually = True
        row.resolved_at = timezone.now()
        row.save(
            update_fields=[
                "resolved_employee",
                "status",
                "resolved_manually",
                "resolved_at",
            ]
        )
        return Response(DocumentRowSerializer(row).data)

    @action(detail=True, methods=["post"], url_path="rows/add")
    def add_row(self, request, pk=None):
        job = self.get_object()
        ser = DocumentRowAddSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        agg = job.rows.aggregate(m=Max("row_index"))
        next_idx = (agg["m"] if agg["m"] is not None else -1) + 1

        row = DocumentRow.objects.create(
            job=job,
            row_index=next_idx,
            ocr_name_raw=data.get("ocr_name_raw", ""),
            ocr_id_raw=data.get("ocr_id_raw", ""),
            ocr_id_clean=data.get("ocr_id_clean", ""),
            added_manually=True,
            status=DocumentRow.Status.NEEDS_REVIEW,
        )
        return Response(DocumentRowSerializer(row).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        job = self.get_object()
        if job.status == AnalysisJob.Status.RESOLVED:
            return Response(
                {"detail": "Document is already resolved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows = list(job.rows.all())
        if not rows:
            return Response(
                {"detail": "No rows to submit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for row in rows:
            if row.status != DocumentRow.Status.RESOLVED or row.resolved_employee_id is None:
                return Response(
                    {
                        "detail": "All rows must be resolved with a selected employee before submit.",
                        "row_id": row.id,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        dept = job.batch.department
        month_date = job.batch.month_date

        with transaction.atomic():
            for row in rows:
                HPRecord.objects.get_or_create(
                    document_row=row,
                    defaults={
                        "employee": row.resolved_employee,
                        "job": job,
                        "department": dept,
                        "month_batch": job.batch,
                        "month_date": month_date,
                    },
                )
            job.status = AnalysisJob.Status.RESOLVED
            job.resolved_at = timezone.now()
            job.save(update_fields=["status", "resolved_at", "updated_at"])

        job.refresh_from_db()
        return Response(AnalysisJobDetailSerializer(job).data)
