from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from openpyxl import load_workbook

from apps.employees.models import Department, Employee


def _department_code(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]", "", (name or "").strip())[:20].upper() or "DEPT"
    code = base
    i = 1
    while Department.objects.filter(code=code).exists():
        suffix = str(i)
        code = (base[: max(1, 20 - len(suffix))] + suffix)[:20]
        i += 1
    return code


def _cell_int(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s:
        return None
    return int(float(s))


class Command(BaseCommand):
    help = "Import employees from Excel (EmployeeID, EmployeeName, Department)."

    def add_arguments(self, parser):
        default_path = Path(settings.BASE_DIR).parent / "employees.xlsx"
        parser.add_argument(
            "--file",
            type=str,
            default=str(default_path),
            help=f"Path to Excel file (default: {default_path})",
        )

    def handle(self, *args, **options):
        path = Path(options["file"]).resolve()
        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb.active
            rows = ws.iter_rows(min_row=1, values_only=True)
            header = next(rows, None)
            if not header or len(header) < 3:
                raise CommandError("Expected header row with at least 3 columns.")

            h0, h1, h2 = (str(c or "").strip() for c in header[:3])
            if h0.lower() != "employeeid" or h1.lower() != "employeename" or h2.lower() != "department":
                raise CommandError(
                    f"Unexpected headers: {header[:3]!r}. "
                    "Expected: EmployeeID, EmployeeName, Department"
                )

            created = 0
            updated = 0
            depts_created = 0

            for row in rows:
                if not row or all(c is None or str(c).strip() == "" for c in row[:3]):
                    continue
                emp_id_raw = row[0]
                name = str(row[1] or "").strip()
                dept_name = str(row[2] or "").strip()
                if not name or not dept_name:
                    continue

                eid = _cell_int(emp_id_raw)
                if eid is None:
                    continue
                emp_id_str = str(eid).zfill(6)

                dept, dept_was_created = Department.objects.get_or_create(
                    name=dept_name,
                    defaults={"code": _department_code(dept_name)},
                )
                if dept_was_created:
                    depts_created += 1

                obj, was_created = Employee.objects.update_or_create(
                    employee_id=emp_id_str,
                    defaults={
                        "full_name": name,
                        "department": dept,
                        "type": "employee",
                        "is_active": True,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
        finally:
            wb.close()

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: {created} created, {updated} updated, "
                f"{depts_created} departments created."
            )
        )
