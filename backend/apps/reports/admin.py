from django.contrib import admin

from apps.reports.models import ExtractedField, Report


class ExtractedFieldInline(admin.TabularInline):
    model = ExtractedField
    extra = 0


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("job", "period", "created_at")
    inlines = [ExtractedFieldInline]


@admin.register(ExtractedField)
class ExtractedFieldAdmin(admin.ModelAdmin):
    list_display = ("report", "label", "value", "confidence")
