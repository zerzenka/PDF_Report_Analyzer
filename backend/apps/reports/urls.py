from django.urls import path

from apps.reports.views import MonthlyReportExportView, MonthlyReportTrendView, MonthlyReportView

urlpatterns = [
    path("monthly/", MonthlyReportView.as_view(), name="reports-monthly"),
    path("monthly/export/", MonthlyReportExportView.as_view(), name="reports-monthly-export"),
    path("monthly/trend/", MonthlyReportTrendView.as_view(), name="reports-monthly-trend"),
]
