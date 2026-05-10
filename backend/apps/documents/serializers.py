from rest_framework import serializers

from apps.documents.models import AnalysisJob


class AnalysisJobListSerializer(serializers.ModelSerializer):
    """Shape for GET /api/documents/."""

    filename = serializers.CharField(source="original_filename", read_only=True)
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = AnalysisJob
        fields = ("id", "filename", "status", "employee_name", "created_at")

    def get_employee_name(self, obj: AnalysisJob) -> str | None:
        if obj.employee_id is None:
            return None
        return obj.employee.full_name
