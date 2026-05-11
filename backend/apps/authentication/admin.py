from django.contrib import admin

from apps.authentication.models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "department")
    list_filter = ("department",)
    raw_id_fields = ("user", "department")
