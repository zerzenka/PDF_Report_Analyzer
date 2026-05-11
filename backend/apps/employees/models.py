from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)  # e.g. "Reduction"
    code = models.CharField(max_length=20, unique=True)  # e.g. "RED"

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Employee(models.Model):
    TYPE_CHOICES = [("employee", "Employee"), ("contractor", "Contractor")]

    employee_id = models.CharField(max_length=10, unique=True)  # 6-digit, no prefix
    full_name = models.CharField(max_length=255)
    department = models.ForeignKey(Department, null=True, on_delete=models.SET_NULL)
    email = models.EmailField(blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    is_active = models.BooleanField(default=True)
    last_synced = models.DateTimeField(null=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.employee_id})"
