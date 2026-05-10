from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import AnalysisJob
from apps.documents.serializers import AnalysisJobListSerializer
from apps.documents.tasks import process_pdf_task


class DocumentUploadView(APIView):
    """
    POST multipart/form-data with one or more PDF fields.

    Accepts repeated ``files`` or ``file`` keys (browser / curl compatible).
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploads = request.FILES.getlist("files")
        if not uploads:
            uploads = request.FILES.getlist("file")

        if not uploads:
            return Response(
                {"detail": "No PDF files provided. Use `files` or `file`."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        errors = []

        for f in uploads:
            name = getattr(f, "name", "") or ""
            if not name.lower().endswith(".pdf"):
                errors.append({"filename": name, "detail": "Not a PDF."})
                continue

            job = AnalysisJob.objects.create(
                uploaded_by=request.user,
                original_filename=name,
                file=f,
                status=AnalysisJob.Status.QUEUED,
            )
            process_pdf_task.delay(str(job.id))
            created.append(
                {
                    "id": str(job.id),
                    "filename": job.original_filename,
                    "status": job.status,
                }
            )

        if not created:
            return Response(
                {"jobs": [], "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"jobs": created, "errors": errors},
            status=status.HTTP_201_CREATED,
        )


class AnalysisJobListView(ListAPIView):
    """GET all analysis jobs for the authenticated user."""

    permission_classes = [IsAuthenticated]
    serializer_class = AnalysisJobListSerializer

    def get_queryset(self):
        return (
            AnalysisJob.objects.filter(uploaded_by=self.request.user)
            .select_related("employee")
            .order_by("-created_at")
        )
