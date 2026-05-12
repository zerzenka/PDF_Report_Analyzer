from django.urls import path

from apps.employees.views import DepartmentListView, EmployeeSearchView

urlpatterns = [
    path("search/", EmployeeSearchView.as_view(), name="employee-search"),
    path("departments/", DepartmentListView.as_view(), name="department-list"),
]
