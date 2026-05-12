from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.permissions import is_admin_user
from apps.employees.models import Department
from apps.employees.models import Employee


class EmployeeSearchView(APIView):
    """GET /api/employees/search/?q=<digits> — max 8 matches on employee_id contains."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        raw = request.query_params.get("q") or ""
        q = "".join(c for c in raw if c.isdigit())
        if not q:
            return Response([])

        qs = (
            Employee.objects.filter(is_active=True, employee_id__icontains=q)
            .order_by("employee_id")[:8]
        )
        data = [
            {"id": e.id, "employee_id": e.employee_id, "full_name": e.full_name}
            for e in qs
        ]
        return Response(data)


class DepartmentListView(APIView):
    """GET /api/employees/departments/ — admin: all; focal: own department only."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if is_admin_user(request.user):
            qs = Department.objects.all().order_by("name")
        else:
            profile = getattr(request.user, "userprofile", None)
            dept = getattr(profile, "department", None)
            qs = Department.objects.filter(pk=dept.pk) if dept else Department.objects.none()
        data = [{"id": d.id, "code": d.code, "name": d.name} for d in qs]
        return Response(data)
