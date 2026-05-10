from django.contrib import admin

from apps.employees.models import Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "full_name", "department", "is_active")
    search_fields = ("employee_id", "full_name", "email")
