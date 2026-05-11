from __future__ import annotations

import re
from datetime import date

from django.db.models import Count, Q
from rest_framework import serializers

from apps.documents.models import AnalysisJob, DocumentRow, MonthBatch
from apps.documents.permissions import is_admin_user
from apps.employees.models import Department, Employee


def parse_month_label(label: str) -> date:
    m = re.fullmatch(r"(\d{2})-(\d{4})", (label or "").strip())
    if not m:
        raise serializers.ValidationError(
            'month_label must be "MM-YYYY", e.g. "05-2026".'
        )
    mm, yyyy = int(m.group(1)), int(m.group(2))
    if not 1 <= mm <= 12:
        raise serializers.ValidationError("Invalid month in month_label.")
    return date(yyyy, mm, 1)


class MonthBatchSerializer(serializers.ModelSerializer):
    """List + create MonthBatch."""

    document_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = MonthBatch
        fields = (
            "id",
            "month_label",
            "month_date",
            "department",
            "created_by",
            "created_at",
            "document_count",
        )
        read_only_fields = ("id", "month_date", "department", "created_by", "created_at")

    def validate_month_label(self, value: str) -> str:
        parse_month_label(value)  # validate format
        return value.strip()

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        label = validated_data["month_label"]
        month_date = parse_month_label(label)

        if not is_admin_user(user) and self.initial_data.get("department_id") is not None:
            raise serializers.ValidationError(
                {"department_id": "Only administrators may set department_id."}
            )

        profile = getattr(user, "userprofile", None)
        dept = profile.department if profile else None
        extra_dept_id = self.initial_data.get("department_id")
        if dept is None and extra_dept_id is not None and is_admin_user(user):
            dept = Department.objects.filter(pk=extra_dept_id).first()
            if dept is None:
                raise serializers.ValidationError(
                    {"department_id": "Invalid department id."}
                )
        if dept is None:
            raise serializers.ValidationError(
                "Your account has no department. Set a UserProfile.department, "
                "or (admin) pass department_id in the request body."
            )

        if MonthBatch.objects.filter(department=dept, month_label=label).exists():
            raise serializers.ValidationError(
                {"month_label": "A batch for this month already exists for your department."}
            )

        return MonthBatch.objects.create(
            department=dept,
            month_label=label,
            month_date=month_date,
            created_by=user,
        )


class EmployeeMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ("id", "employee_id", "full_name", "type")


class DocumentRowSerializer(serializers.ModelSerializer):
    resolved_employee = EmployeeMiniSerializer(read_only=True)

    class Meta:
        model = DocumentRow
        fields = (
            "id",
            "row_index",
            "ocr_name_raw",
            "ocr_id_raw",
            "ocr_id_clean",
            "name_crop",
            "id_crop",
            "top_candidates",
            "confidence",
            "match_method",
            "status",
            "resolved_employee",
            "resolved_manually",
            "added_manually",
            "resolved_at",
        )


class AnalysisJobListSerializer(serializers.ModelSerializer):
    filename = serializers.CharField(source="original_filename", read_only=True)
    batch_id = serializers.IntegerField(read_only=True)
    month_label = serializers.CharField(source="batch.month_label", read_only=True)
    rows_total = serializers.SerializerMethodField()
    rows_resolved = serializers.SerializerMethodField()

    class Meta:
        model = AnalysisJob
        fields = (
            "id",
            "filename",
            "status",
            "batch_id",
            "month_label",
            "page_count",
            "created_at",
            "updated_at",
            "rows_total",
            "rows_resolved",
        )

    def get_rows_total(self, obj: AnalysisJob) -> int:
        return obj.rows.count()

    def get_rows_resolved(self, obj: AnalysisJob) -> int:
        return obj.rows.filter(status=DocumentRow.Status.RESOLVED).count()


class AnalysisJobDetailSerializer(serializers.ModelSerializer):
    filename = serializers.CharField(source="original_filename", read_only=True)
    rows = DocumentRowSerializer(many=True, read_only=True)
    batch_id = serializers.IntegerField(read_only=True)
    month_label = serializers.CharField(source="batch.month_label", read_only=True)
    department_id = serializers.IntegerField(
        source="batch.department_id", read_only=True
    )

    class Meta:
        model = AnalysisJob
        fields = (
            "id",
            "filename",
            "status",
            "batch_id",
            "month_label",
            "department_id",
            "page_count",
            "error_message",
            "file",
            "created_at",
            "updated_at",
            "resolved_at",
            "deleted",
            "rows",
        )


class DocumentRowResolveSerializer(serializers.Serializer):
    resolved_employee = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        required=True,
    )


class DocumentRowAddSerializer(serializers.Serializer):
    ocr_name_raw = serializers.CharField(required=False, allow_blank=True, default="")
    ocr_id_raw = serializers.CharField(required=False, allow_blank=True, default="")
    ocr_id_clean = serializers.CharField(required=False, allow_blank=True, default="")


def annotate_batch_queryset(qs):
    return qs.annotate(
        document_count=Count(
            "documents",
            filter=Q(documents__deleted=False),
            distinct=True,
        )
    )
