from django.urls import path

from apps.documents.views import AnalysisJobListView, DocumentUploadView

urlpatterns = [
    path("", AnalysisJobListView.as_view(), name="document-list"),
    path("upload/", DocumentUploadView.as_view(), name="document-upload"),
]
