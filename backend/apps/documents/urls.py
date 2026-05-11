from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.documents.views import DocumentUploadView, DocumentViewSet

router = DefaultRouter()
router.register(r"", DocumentViewSet, basename="document")

urlpatterns = [
    path("upload/", DocumentUploadView.as_view(), name="document-upload"),
]
urlpatterns += router.urls
