from django.contrib import admin

from apps.documents.models import AnalysisJob


@admin.register(AnalysisJob)
class AnalysisJobAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "status", "uploaded_by", "created_at")
    list_filter = ("status",)
    readonly_fields = ("id", "created_at", "updated_at")
