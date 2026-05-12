"""
URL configuration — wire app urls here when APIs are implemented.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.authentication.urls")),
    path("api/batches/", include("apps.documents.urls_batches")),
    path("api/documents/", include("apps.documents.urls")),
    path("api/employees/", include("apps.employees.urls")),
    path("api/reports/", include("apps.reports.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
