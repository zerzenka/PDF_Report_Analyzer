from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
