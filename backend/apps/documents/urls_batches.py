"""Routes mounted at /api/batches/."""

from django.urls import path

from apps.documents.views import MonthBatchListCreateView

urlpatterns = [
    path("", MonthBatchListCreateView.as_view(), name="batch-list-create"),
]
