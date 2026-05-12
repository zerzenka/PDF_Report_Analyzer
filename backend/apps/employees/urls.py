from django.urls import path

from apps.employees.views import EmployeeSearchView

urlpatterns = [
    path("search/", EmployeeSearchView.as_view(), name="employee-search"),
]
